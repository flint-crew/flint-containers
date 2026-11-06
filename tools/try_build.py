#!/usr/bin/env python3
"""Try new upstream versions: check that they fit together, then build them.

Most failed version bumps can be seen in the upstream build files before
anything is compiled: a dependency outside the range a project accepts, or a
casacore whose headers need a newer C++ standard than a project compiles with.
This script reads those files at the versions you give and reports problems
in about a minute, instead of half an hour into a CI build.

    tools/try_build.py check WSCLEAN=master EVERYBEAM=v0.9.1
    tools/try_build.py build WSCLEAN=master EVERYBEAM=v0.9.1 --smoke

NAME is any variable in docker-bake.hcl. A ref can be a tag, a branch or a
commit. Branches are pinned to their current commit, so the build and the
image labels record exactly what was built.

`build` builds only the images the new versions change (and calibrate's test
suite if calibrate is one of them), loads them into Docker, and with --smoke
runs tests/smoke.sh on each.

Rules that can't be read from upstream files are in tools/compat.toml.
Needs Python 3.11+, git, and docker buildx.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAKE_FILE = ROOT / "docker-bake.hcl"
RULES_FILE = Path(__file__).resolve().parent / "compat.toml"
MIRROR_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "flint-containers" / "git"

# GCC 13 (Ubuntu 24.04) compiles as C++17 unless a project asks for more.
DEFAULT_CXX = 17

# What may appear in a NAME=REF override; it ends up in the environment and
# in image labels, so keep it to characters a git ref or image tag can use.
VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHORT_SHA_RE = re.compile(r"^[0-9a-f]{7,39}$")
# Variables that say where and how CI builds rather than what is built.
NOT_VERSIONS = {"CACHE_REF", "CACHE_PUSH", "CACHE_SCOPE", "GITHUB_SHA", "PLATFORMS", "REGISTRY", "TAGS", "TAG_SUFFIX"}
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
# Release-like names: v3.7, 1.2.0, v3.8.0-rc1. Needs a dot, so commits never match.
VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)+)(?:[-.]?(?:rc|alpha|beta|a|b|post|dev)\.?\d*)?$")

Version = tuple[int, ...]


# --- Versions -----------------------------------------------------------------


def parse_version(text: str | None) -> Version | None:
    """'v3.8.2' -> (3, 8, 2); None if text is not a release-like name."""
    m = VERSION_RE.match(text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def norm(v: Version) -> Version:
    """Pad to four parts so that (3, 8) == (3, 8, 0)."""
    return v + (0,) * (4 - len(v))


def vstr(v: Version | None) -> str:
    return ".".join(map(str, v)) if v else "?"


def compare(a: Version, op: str, b: Version) -> bool:
    a, b = norm(a), norm(b)
    return {">=": a >= b, ">": a > b, "<=": a <= b, "<": a < b, "==": a == b}[op]


@dataclass
class Range:
    """Versions a project accepts for one of its dependencies."""

    low: Version | None = None  # inclusive
    high: Version | None = None
    high_inclusive: bool = False

    def __bool__(self) -> bool:
        return self.low is not None or self.high is not None

    def contains(self, v: Version) -> bool:
        if self.low and compare(v, "<", self.low):
            return False
        if self.high:
            return compare(v, "<=" if self.high_inclusive else "<", self.high)
        return True

    def __str__(self) -> str:
        parts = []
        if self.low:
            parts.append(f">= {vstr(self.low)}")
        if self.high:
            parts.append(f"{'<=' if self.high_inclusive else '<'} {vstr(self.high)}")
        return ", ".join(parts)


# --- docker-bake.hcl -------------------------------------------------------------


def read_bake() -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Variables with their defaults, git URL per source variable, and images."""
    text = BAKE_FILE.read_text()
    variables = {
        m[1]: m[2] for m in re.finditer(r'variable\s+"(\w+)"\s*\{\s*default\s*=\s*"([^"]*)"', text)
    }
    sources = {m[2]: m[1] for m in re.finditer(r'git\(\s*"([^"]+)"\s*,\s*(\w+)\s*\)', text)}
    group = re.search(r'group\s+"default"\s*\{\s*targets\s*=\s*\[([^\]]*)\]', text)
    images = re.findall(r'"([^"]+)"', group[1]) if group else []
    return variables, sources, images


def bake_print(env: dict[str, str]) -> dict[str, dict]:
    """Resolved bake targets (every image, its stages, and the test target)."""
    result = subprocess.run(
        ["docker", "buildx", "bake", "--print", "default", "test"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"docker buildx bake --print failed:\n{result.stderr}")
    return json.loads(result.stdout)["target"]


def affected_targets(overrides: dict[str, str]) -> set[str]:
    """Bake targets whose definition, or any stage they build on, changes."""
    base = {k: v for k, v in os.environ.items() if k not in overrides}
    before, after = bake_print(base), bake_print({**base, **overrides})
    changed = {name for name, target in after.items() if before.get(name) != target}
    # A target also changes when a stage it uses through "target:<name>" does.
    grown = True
    while grown:
        grown = False
        for name, target in after.items():
            uses = {v.removeprefix("target:") for v in target.get("contexts", {}).values() if v.startswith("target:")}
            if name not in changed and uses & changed:
                changed.add(name)
                grown = True
    return changed


# --- git and upstream files -------------------------------------------------------


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=600)


class Unreachable(Exception):
    """An upstream server could not be reached; the check is skipped, not failed."""


def ls_remote(url: str, *patterns: str) -> dict[str, str]:
    """Ref name -> commit. Annotated tags are peeled to the commit they tag."""
    result = git("ls-remote", url, *patterns)
    if result.returncode:
        raise Unreachable(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else url)
    refs: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, name = line.split("\t", 1)
        if name.endswith("^{}"):
            peeled[name[:-3]] = sha
        else:
            refs[name] = sha
    return refs | peeled


_mirror_locks: dict[str, threading.Lock] = {}
_mirror_done: set[str] = set()
_lock = threading.Lock()


def mirror(url: str) -> Path:
    """A local bare copy of a repository's commits and tags, without files.

    Fast even for large repositories; used to check which commits contain
    which, and to name the nearest release of a commit. Kept between runs.
    """
    path = MIRROR_DIR / re.sub(r"[^A-Za-z0-9]+", "_", url)
    with _lock:
        lock = _mirror_locks.setdefault(url, threading.Lock())
    with lock:
        if url in _mirror_done:
            return path
        if (path / "HEAD").exists():
            result = git("fetch", "--quiet", "--force", "--tags", "--prune", "origin",
                         "+refs/heads/*:refs/heads/*", cwd=path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            result = git("clone", "--quiet", "--bare", "--filter=tree:0", url, str(path))
        if result.returncode:
            raise Unreachable(result.stderr.strip())
        _mirror_done.add(url)
    return path


def raw_url(repo: str, sha: str, path: str) -> str:
    repo = repo.removesuffix(".git")
    if m := re.match(r"https://github\.com/([^/]+/[^/]+)$", repo):
        return f"https://raw.githubusercontent.com/{m[1]}/{sha}/{path}"
    return f"{repo}/-/raw/{sha}/{path}"  # GitLab: gitlab.com and git.astron.nl


def fetch(url: str) -> str | None:
    """A file's text, or None if the server says it does not exist."""
    request = urllib.request.Request(url, headers={"User-Agent": "flint-containers-try-build"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Unreachable(f"{url}: HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise Unreachable(f"{url}: {e}") from e


# --- What each source is ---------------------------------------------------------


@dataclass
class Source:
    """One upstream repository, at the ref being built."""

    name: str  # docker-bake.hcl variable, e.g. WSCLEAN
    url: str
    ref: str
    overridden: bool
    sha: str | None = None
    kind: str = ""  # "tag", "branch" or "commit"
    cmake: str | None = None  # CMakeLists.txt, if the project has one
    version: Version | None = None
    version_from: str = ""
    error: str = ""  # the ref does not exist
    unreachable: str = ""  # could not ask the server

    @property
    def pinned(self) -> str:
        """The value to build with: branches and short commits become full commits."""
        return self.sha if self.kind != "tag" and self.sha else self.ref

    def cxx(self) -> list[int]:
        """C++ standards the project sets (several when it picks one by condition)."""
        if not self.cmake:
            return []
        found = re.findall(r"set\s*\(\s*CMAKE_CXX_STANDARD\s+(\d+)", self.cmake)
        found += re.findall(r"cxx_std_(\d+)", self.cmake)
        return sorted({int(x) for x in found})


def resolve(src: Source) -> None:
    ref = src.ref
    if SHA_RE.match(ref):
        src.sha, src.kind = ref, "commit"
        return
    refs = ls_remote(src.url, ref)
    for name, kind in ((f"refs/tags/{ref}", "tag"), (f"refs/heads/{ref}", "branch"), (ref, "branch")):
        if name in refs:
            src.sha, src.kind = refs[name], kind
            return
    if SHORT_SHA_RE.match(ref):
        result = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=mirror(src.url))
        if result.returncode == 0:
            src.sha, src.kind = result.stdout.strip(), "commit"
            return
    src.error = f"{ref!r} is not a tag, branch or commit of {src.url}"


def inspect(src: Source, needs_version: bool) -> Source:
    try:
        resolve(src)
        if src.sha:
            src.cmake = fetch(raw_url(src.url, src.sha, "CMakeLists.txt"))
    except Unreachable as e:
        src.unreachable = str(e)

    # The version: from CMakeLists.txt's project(... VERSION x.y.z), else the
    # tag name, else (only where a check needs it) the nearest earlier tag.
    if src.cmake and (m := re.search(r"project\s*\([^)]*\bVERSION\s+(\d+(?:\.\d+)+)", src.cmake)):
        src.version, src.version_from = parse_version(m[1]), "CMakeLists.txt"
    elif v := parse_version(src.ref):
        src.version, src.version_from = v, "tag"
    elif needs_version and src.sha and not src.unreachable:
        try:
            result = git("describe", "--tags", "--abbrev=0", src.sha, cwd=mirror(src.url))
            tag = result.stdout.strip()
            if result.returncode == 0 and (v := parse_version(tag)):
                src.version, src.version_from = v, f"after {tag}"
        except Unreachable as e:
            src.unreachable = str(e)
    return src


def requirement(consumer: Source, package: str, version_var: str) -> Range | None:
    """The versions of `package` that `consumer` accepts, or None if it doesn't use it.

    Reads find_package(<package> <min>) and guards written the usual way:
    if(${<version_var>} VERSION_LESS "x" OR ... VERSION_GREATER_EQUAL "y").
    """
    text = consumer.cmake or ""
    if not re.search(rf"find_package\s*\(\s*{package}\b", text, re.IGNORECASE):
        return None
    r = Range()
    for m in re.finditer(rf"find_package\s*\(\s*{package}\s+(\d+(?:\.\d+)*)", text, re.IGNORECASE):
        v = parse_version(m[1]) or (int(m[1]),)
        r.low = max(r.low, v, key=norm) if r.low else v
    pattern = rf"\$\{{{version_var}\}}\s+(VERSION_LESS|VERSION_GREATER_EQUAL|VERSION_GREATER)\b\s+\"?(\d+(?:\.\d+)*)"
    for op, value in re.findall(pattern, text):
        v = tuple(int(x) for x in value.split("."))
        if op == "VERSION_LESS":
            r.low = max(r.low, v, key=norm) if r.low else v
        elif not r.high or compare(v, "<", r.high):
            r.high, r.high_inclusive = v, op == "VERSION_GREATER"
    return r


# --- Checks -------------------------------------------------------------------


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)


def newest_tag_in(src: Source, wanted: Range) -> str | None:
    try:
        tags = ls_remote(src.url, "--tags")
    except Unreachable:
        return None
    names = {n.removeprefix("refs/tags/") for n in tags}
    good = [(v, n) for n in names if (v := parse_version(n)) and wanted.contains(v)]
    return max(good, key=lambda x: norm(x[0]))[1] if good else None


def contains_commit(src: Source, commit: str) -> tuple[bool | None, str]:
    """Whether src's commit includes `commit`, and a hint for where it is."""
    repo = mirror(src.url)
    full = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", cwd=repo)
    if full.returncode:
        return None, f"commit {commit} not found in {src.url}"
    has = git("merge-base", "--is-ancestor", full.stdout.strip(), src.sha or "", cwd=repo)
    if has.returncode not in (0, 1):
        return None, f"could not compare with {src.ref}"
    tags = git("tag", "--contains", full.stdout.strip(), cwd=repo).stdout.split()
    released = sorted((v, t) for t in tags if (v := parse_version(t)))
    hint = f"first in {released[0][1]}" if released else "not in a release yet; use a commit after it"
    return has.returncode == 0, hint


def run_checks(sources: dict[str, Source], rules: dict) -> Report:
    report = Report()

    for src in sources.values():
        if src.error:
            report.errors.append(f"{src.name}: {src.error}")
        elif src.unreachable:
            report.warnings.append(f"{src.name}: could not read upstream, so it was not checked ({src.unreachable})")

    # Each provided package against every project that uses it.
    for provider_name, spec in rules.get("provides", {}).items():
        provider = sources.get(provider_name)
        if not provider:
            continue
        provider_cxx = min(provider.cxx(), default=DEFAULT_CXX)
        for consumer in sources.values():
            if consumer is provider or not consumer.cmake:
                continue
            wanted = requirement(consumer, spec["package"], spec["version_var"])
            if wanted is None:
                continue
            pair = f"{consumer.name} {consumer.ref} accepts {provider_name}"
            if wanted:
                if not provider.version:
                    report.warnings.append(f"{pair} {wanted}; could not tell the version of {provider_name} {provider.ref}")
                elif wanted.contains(provider.version):
                    report.passed.append(f"{pair} {wanted}; {provider.ref} is {vstr(provider.version)}")
                else:
                    hint = newest_tag_in(provider, wanted)
                    report.errors.append(
                        f"{pair} {wanted}, but {provider.ref} is {vstr(provider.version)}"
                        + (f". Newest tag that fits: {provider_name}={hint}" if hint else "")
                    )
            # The provider's headers are compiled as part of the consumer.
            if provider.cmake and consumer.cmake:
                consumer_cxx = max(consumer.cxx(), default=DEFAULT_CXX)
                what = f"{consumer.name} compiles as C++{consumer_cxx}" + ("" if consumer.cxx() else " (compiler default)")
                if consumer_cxx < provider_cxx:
                    report.errors.append(
                        f"{what}, but {provider_name} {provider.ref} needs C++{provider_cxx}; "
                        f"use a {consumer.name} that sets CMAKE_CXX_STANDARD {provider_cxx}"
                    )
                else:
                    report.passed.append(f"{what}; {provider_name} {provider.ref} needs C++{provider_cxx}")

    for rule in rules.get("needs_commit", []):
        src, cond = sources.get(rule["source"]), re.match(r"^\s*(\w+)\s*(>=|<=|==|>|<)\s*([\d.]+)\s*$", rule["when"])
        if not src or not cond or not src.sha:
            continue
        other = sources.get(cond[1])
        if not other or not other.version or not compare(other.version, cond[2], tuple(int(x) for x in cond[3].split("."))):
            continue
        label = f"{src.name} {src.ref} with {rule['when']} needs commit {rule['commit']} ({rule['why']})"
        try:
            ok, hint = contains_commit(src, rule["commit"])
        except Unreachable as e:
            ok, hint = None, str(e)
        if ok is None:
            report.warnings.append(f"{label}: could not check, {hint}")
        elif ok:
            report.passed.append(f"{label}: included")
        else:
            report.errors.append(f"{label}: not included, {hint}")

    for rule in rules.get("same_minor", []):
        pair = [sources.get(n) for n in rule["sources"]]
        if not all(s and s.version for s in pair):
            continue
        minors = {s.version[:2] for s in pair if s and s.version}
        text = " and ".join(f"{s.name} {vstr(s.version)}" for s in pair if s)
        if len(minors) == 1:
            report.passed.append(f"{text} have the same major.minor")
        else:
            report.warnings.append(f"{text} differ in major.minor: {rule['why']}")

    return report


# --- Output -----------------------------------------------------------------------


def versions_table(sources: dict[str, Source]) -> str:
    rows = [("", "NAME", "REF", "COMMIT", "VERSION", "C++")]
    for s in sources.values():
        version = vstr(s.version) + (f" ({s.version_from})" if s.version_from.startswith("after") else "")
        cxx = "/".join(map(str, s.cxx())) or ("default" if s.cmake else "-")
        rows.append(("*" if s.overridden else "", s.name, s.ref, (s.sha or "?")[:12], version, cxx))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def format_report(sources: dict[str, Source], report: Report, verbose: bool) -> str:
    lines = [versions_table(sources), "(* = changed from docker-bake.hcl)", ""]
    lines += [f"ERROR    {e}" for e in report.errors]
    lines += [f"warning  {w}" for w in report.warnings]
    if verbose:
        lines += [f"ok       {p}" for p in report.passed]
    else:
        lines.append(f"ok       {len(report.passed)} checks passed (--verbose to list them)")
    return "\n".join(lines)


def env_prefix(overrides: dict[str, str]) -> str:
    return " ".join(f"{k}={shlex.quote(v)}" for k, v in overrides.items())


def command_line(overrides: dict[str, str], command: list[str]) -> str:
    return " ".join(filter(None, [env_prefix(overrides), shlex.join(command)]))


# --- Commands -----------------------------------------------------------------------


def parse_overrides(args: list[str], variables: dict[str, str]) -> dict[str, str]:
    overrides = {}
    for arg in args:
        name, sep, value = arg.partition("=")
        if not sep or name not in variables or name in NOT_VERSIONS:
            known = ", ".join(sorted(set(variables) - NOT_VERSIONS))
            sys.exit(f"{arg!r}: expected NAME=REF with NAME one of {known}")
        if not VALUE_RE.match(value):
            sys.exit(f"{arg!r}: {value!r} has characters not allowed in a ref")
        overrides[name] = value
    return overrides


def split_list(text: str | None) -> list[str]:
    return [x for x in re.split(r"[\s,]+", text or "") if x]


def plan(overrides: dict[str, str], requested: str | None, all_images: list[str]) -> tuple[list[str], list[str]]:
    """Images to build, and the bake targets for them (plus calibrate's tests if they change)."""
    images = split_list(requested)
    if unknown := sorted(set(images) - set(all_images)):
        sys.exit(f"Unknown image(s): {', '.join(unknown)}. Images: {', '.join(all_images)}")
    changed: set[str] = set()
    if overrides:
        try:
            changed = affected_targets(overrides)
        except (OSError, RuntimeError) as e:
            if not images:
                sys.exit(f"Could not work out which images change ({e}); pass --images")
    images = images or [i for i in all_images if i in changed]
    tests = "calibrate" in images or "calibrate-test" in changed
    return images, images + (["calibrate-test"] if tests else [])


def check(args: argparse.Namespace) -> tuple[dict[str, str], list[str], list[str], bool]:
    """Check the versions; return pinned overrides, images, bake targets, and success."""
    variables, urls, all_images = read_bake()
    overrides = parse_overrides(args.versions, variables)
    rules = tomllib.loads(RULES_FILE.read_text())
    versioned = set(rules.get("provides", {}))
    for rule in rules.get("same_minor", []):
        versioned |= set(rule["sources"])

    sources = {
        name: Source(name, url, overrides.get(name, variables.get(name, "")), name in overrides)
        for name, url in urls.items()
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda s: inspect(s, s.name in versioned), sources.values()))
    report = run_checks(sources, rules)
    text = format_report(sources, report, args.verbose)
    print(text)

    # Pin branches, and drop overrides that are the default anyway.
    pinned = {n: (sources[n].pinned if n in sources else v) for n, v in overrides.items()}
    pinned = {n: v for n, v in pinned.items() if v != variables.get(n)}

    images, targets = plan(pinned, args.images, all_images)

    print()
    if pinned:
        print(f"Versions to build with: {env_prefix(pinned)}")
    print(f"Images: {' '.join(images) or 'none'}")
    if images:
        print(f"Build with:\n  {command_line(pinned, ['docker', 'buildx', 'bake', *targets])}")

    ok = not report.errors
    if args.summary:
        with open(args.summary, "a") as f:
            status = "Versions look compatible" if ok else "Versions are not compatible"
            f.write(f"### {status}\n\n```\n{text}\n```\n\nImages: {' '.join(images) or 'none'}\n\n")
    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"versions={env_prefix(pinned)}\nimages={' '.join(images)}\n")
    return pinned, images, targets, ok


def build(args: argparse.Namespace) -> int:
    if args.tag and not TAG_RE.match(args.tag):
        sys.exit(f"{args.tag!r} is not a valid image tag")
    if args.no_check:
        variables, _, all_images = read_bake()
        overrides = parse_overrides(args.versions, variables)
        images, targets = plan(overrides, args.images, all_images)
    else:
        overrides, images, targets, ok = check(args)
        if not ok and not args.force:
            print("\nNot building, because of the errors above (--force to build anyway).", file=sys.stderr)
            return 1
    if not images:
        print("Nothing to build: the versions given change no image.")
        return 0

    env = {**os.environ, **overrides}
    if args.tag:
        env["TAGS"] = args.tag
    output = "type=registry" if args.push else "type=docker"
    # Only the images get an output; calibrate-test stays cache-only.
    push_targets = images if args.push else targets
    command = ["docker", "buildx", "bake", *push_targets]
    for image in images:
        command += ["--set", f"{image}.output={output}"]
    shown = overrides | ({"TAGS": args.tag} if args.tag else {})
    print(f"\n$ {command_line(shown, command)}", flush=True)
    if args.dry_run:
        return 0
    if subprocess.run(command, cwd=ROOT, env=env).returncode:
        return 1

    if args.smoke and not args.push:
        variables, _, _ = read_bake()
        registry = env.get("REGISTRY", variables["REGISTRY"])
        tag = split_list(env.get("TAGS", variables["TAGS"]))[0] + env.get("TAG_SUFFIX", "")
        for image in images:
            print(f"\n--- smoke tests: {image}", flush=True)
            if subprocess.run([str(ROOT / "tests" / "smoke.sh"), image, f"{registry}/{image}:{tag}"]).returncode:
                return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("versions", nargs="*", metavar="NAME=REF", help="e.g. WSCLEAN=master EVERYBEAM=v0.9.1")
        p.add_argument("--images", help="images to build (default: every image the versions change)")
        p.add_argument("--verbose", "-v", action="store_true", help="list the checks that passed too")
        p.add_argument("--summary", metavar="FILE", help="append a Markdown report (e.g. $GITHUB_STEP_SUMMARY)")
        p.add_argument("--github-output", metavar="FILE", help="write versions= and images= (e.g. $GITHUB_OUTPUT)")

    common(sub.add_parser("check", help="check that versions fit together, without building"))
    p = sub.add_parser("build", help="check, then build the images the versions change")
    common(p)
    p.add_argument("--tag", help="tag the images with this instead of TAGS from docker-bake.hcl (dev)")
    p.add_argument("--smoke", action="store_true", help="run tests/smoke.sh on each image after building")
    p.add_argument("--push", action="store_true", help="push the images instead of loading them into Docker")
    p.add_argument("--force", action="store_true", help="build even if the check finds errors")
    p.add_argument("--no-check", action="store_true", help="skip the check (e.g. when CI has already run it)")
    p.add_argument("--dry-run", action="store_true", help="print the build command without running it")

    args = parser.parse_args()
    if args.command == "check":
        return 0 if check(args)[3] else 1
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
