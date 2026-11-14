#!/usr/bin/env python3
"""Check that upstream versions work together, then build the images they change.

    tools/try_build.py check WSCLEAN=master EVERYBEAM=v0.9.1
    tools/try_build.py build WSCLEAN=master EVERYBEAM=v0.9.1 --smoke

NAME is a docker-bake.hcl variable and REF a tag, branch or commit. Rules that
upstream build files don't state are in tools/compat.toml.
"""

from __future__ import annotations

import json
import operator
import os
import re
import shlex
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NamedTuple


class Unreachable(Exception):
    """An upstream server could not be reached"""


class Bake(NamedTuple):
    """What this script needs from docker-bake.hcl"""

    root: Path
    """Directory holding docker-bake.hcl"""
    variables: dict[str, str]
    """Default of each variable"""
    urls: dict[str, str]
    """Git URL of each variable that names a source"""
    images: list[str]
    """Published images, from the default group"""


class VersionRange(NamedTuple):
    """Versions of a dependency that a project accepts"""

    low: tuple[int, ...] | None
    """Lowest version accepted"""
    high: tuple[int, ...] | None
    """First version no longer accepted"""

    def accepts(self, version: tuple[int, ...]) -> bool:
        """Whether `version` is in the range"""
        above = not self.low or padded(version) >= padded(self.low)
        below = not self.high or padded(version) < padded(self.high)
        return above and below

    def __str__(self) -> str:
        parts = [f">= {show(self.low)}"] if self.low else []
        parts += [f"< {show(self.high)}"] if self.high else []
        return ", ".join(parts)


@dataclass
class Source:
    """An upstream repository at the ref to build"""

    name: str
    """docker-bake.hcl variable, e.g. WSCLEAN"""
    url: str
    ref: str
    changed: bool
    """Whether `ref` differs from docker-bake.hcl"""
    sha: str | None = None
    kind: str = ""
    """tag, branch or commit"""
    cmake: str | None = None
    """CMakeLists.txt, if the project has one"""
    version: tuple[int, ...] | None = None
    version_from: str = ""
    error: str = ""
    """Why the ref is wrong"""
    unreachable: str = ""
    """Why the ref could not be checked"""

    @property
    def pinned(self) -> str:
        """The ref to build with: branches and short hashes become full commits"""
        return self.sha if self.sha and self.kind != "tag" else self.ref

    @property
    def cxx(self) -> list[int]:
        """C++ standards CMakeLists.txt sets; several if it picks one by condition"""
        text = self.cmake or ""
        found = re.findall(r"set\s*\(\s*CMAKE_CXX_STANDARD\s+(\d+)", text)
        found += re.findall(r"cxx_std_(\d+)", text)
        return sorted({int(standard) for standard in found})


def parse_version(text: str) -> tuple[int, ...] | None:
    """`v3.8.2` as (3, 8, 2), or None if `text` isn't a release name"""
    # Requiring a dot means a commit hash is never taken for a version
    match = re.fullmatch(
        r"v?(\d+(?:\.\d+)+)(?:[-.]?(?:rc|alpha|beta|post|dev)\d*)?", text
    )
    return tuple(int(part) for part in match[1].split(".")) if match else None


def padded(version: tuple[int, ...]) -> tuple[int, ...]:
    """`version` padded to four parts, so that 3.8 equals 3.8.0"""
    return version + (0,) * (4 - len(version))


def show(version: tuple[int, ...] | None) -> str:
    return ".".join(map(str, version)) if version else "?"


def read_bake(root: Path) -> Bake:
    """Variables, sources and images from docker-bake.hcl"""
    text = (root / "docker-bake.hcl").read_text()
    variables = re.findall(r'variable\s+"(\w+)"\s*\{\s*default\s*=\s*"([^"]*)"', text)
    urls = re.findall(r'git\(\s*"([^"]+)"\s*,\s*(\w+)\s*\)', text)
    group = re.search(r'group\s+"default"\s*\{\s*targets\s*=\s*\[([^\]]*)\]', text)
    return Bake(
        root=root,
        variables=dict(variables),
        urls={name: url for url, name in urls},
        images=re.findall(r'"([^"]+)"', group[1]),
    )


def bake_print(bake: Bake, env: dict[str, str]) -> dict[str, dict]:
    """Every bake target as resolved under `env`"""
    result = subprocess.run(
        ["docker", "buildx", "bake", "--print", "default", "test"],
        cwd=bake.root,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"docker buildx bake --print failed:\n{result.stderr}")
    return json.loads(result.stdout)["target"]


def changed_targets(bake: Bake, overrides: dict[str, str]) -> set[str]:
    """Bake targets that `overrides` change, directly or through a stage they use"""
    base = {k: v for k, v in os.environ.items() if k not in overrides}
    before, after = bake_print(bake, base), bake_print(bake, base | overrides)
    changed = {name for name, target in after.items() if before.get(name) != target}
    while True:
        users = {
            name
            for name, target in after.items()
            if any(
                context.removeprefix("target:") in changed
                for context in target.get("contexts", {}).values()
                if context.startswith("target:")
            )
        }
        if users <= changed:
            return changed
        changed |= users


def plan(
    bake: Bake, overrides: dict[str, str], requested: list[str]
) -> tuple[list[str], list[str]]:
    """Images to build, and the bake targets for them"""
    if unknown := sorted(set(requested) - set(bake.images)):
        sys.exit(f"Unknown images {unknown}; images are {bake.images}")
    changed = changed_targets(bake, overrides) if overrides else set()
    images = requested or [image for image in bake.images if image in changed]
    if "calibrate" in images or "calibrate-test" in changed:
        return images, images + ["calibrate-test"]
    return images, images


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run git, never prompting for credentials"""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=os.environ | {"GIT_TERMINAL_PROMPT": "0"},
        capture_output=True,
        text=True,
        timeout=600,
    )


def ls_remote(url: str, *patterns: str) -> dict[str, str]:
    """Commit of each matching ref, with annotated tags peeled to their commit"""
    result = git("ls-remote", url, *patterns)
    if result.returncode:
        raise Unreachable(result.stderr.strip() or url)
    refs = {}
    # Peeled lines (ending ^{}) go last so they replace the tag object
    for line in sorted(result.stdout.splitlines(), key=lambda x: x.endswith("^{}")):
        sha, name = line.split("\t")
        refs[name.removesuffix("^{}")] = sha
    return refs


@cache
def mirror(url: str) -> Path:
    """Local copy of a repository's commits and tags, without its files"""
    path = Path.home() / ".cache" / "flint-containers" / re.sub(r"\W+", "_", url)
    if (path / "HEAD").exists():
        refspec = "+refs/heads/*:refs/heads/*"
        result = git("fetch", "-q", "--force", "--tags", "origin", refspec, cwd=path)
    else:
        result = git("clone", "-q", "--bare", "--filter=tree:0", url, str(path))
    if result.returncode:
        raise Unreachable(result.stderr.strip())
    return path


def fetch_file(repo: str, sha: str, path: str) -> str | None:
    """A file from a GitHub or GitLab repository, or None if it doesn't exist"""
    repo = repo.removesuffix(".git")
    if github := re.fullmatch(r"https://github\.com/(.+)", repo):
        url = f"https://raw.githubusercontent.com/{github[1]}/{sha}/{path}"
    else:
        url = f"{repo}/-/raw/{sha}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "flint-containers"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise Unreachable(f"{url}: HTTP {error.code}") from error
    except OSError as error:
        raise Unreachable(f"{url}: {error}") from error


def resolve(source: Source) -> None:
    """Find the commit that `source.ref` names"""
    ref = source.ref
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        source.sha, source.kind = ref, "commit"
        return
    refs = ls_remote(source.url, ref)
    for name, kind in ((f"refs/tags/{ref}", "tag"), (f"refs/heads/{ref}", "branch")):
        if name in refs:
            source.sha, source.kind = refs[name], kind
            return
    if re.fullmatch(r"[0-9a-f]{7,39}", ref):
        found = git(
            "rev-parse", "-q", "--verify", f"{ref}^{{commit}}", cwd=mirror(source.url)
        )
        if found.returncode == 0:
            source.sha, source.kind = found.stdout.strip(), "commit"
            return
    source.error = f"{ref!r} is not a tag, branch or commit of {source.url}"


def inspect(source: Source, describe: bool) -> None:
    """Find the commit, CMakeLists.txt and version of `source`"""
    try:
        resolve(source)
        if source.sha:
            source.cmake = fetch_file(source.url, source.sha, "CMakeLists.txt")
    except Unreachable as error:
        source.unreachable = str(error)

    declared = re.search(r"project\s*\([^)]*\bVERSION\s+([\d.]+)", source.cmake or "")
    if declared and (version := parse_version(declared[1])):
        source.version, source.version_from = version, "CMakeLists.txt"
    elif version := parse_version(source.ref):
        source.version, source.version_from = version, "tag"
    elif describe and source.sha and not source.unreachable:
        try:
            repo = mirror(source.url)
        except Unreachable as error:
            source.unreachable = str(error)
            return
        tag = git("describe", "--tags", "--abbrev=0", source.sha, cwd=repo).stdout
        if version := parse_version(tag.strip()):
            source.version, source.version_from = version, f"after {tag.strip()}"


def numbers(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.strip(".").split("."))


def accepted_range(cmake: str, package: str, version_var: str) -> VersionRange | None:
    """Versions of `package` that a CMakeLists.txt accepts; None if it doesn't use it

    Reads find_package(<package> <min>) and the usual guard,
    if(${<version_var>} VERSION_LESS "x" OR ... VERSION_GREATER_EQUAL "y").
    """
    if not re.search(rf"find_package\s*\(\s*{package}\b", cmake, re.IGNORECASE):
        return None
    lows = re.findall(
        rf"find_package\s*\(\s*{package}\s+([\d.]+)", cmake, re.IGNORECASE
    )
    variable = re.escape(f"${{{version_var}}}")
    lows += re.findall(rf"{variable}\s+VERSION_LESS\s+\"?([\d.]+)", cmake)
    highs = re.findall(rf"{variable}\s+VERSION_GREATER_EQUAL\s+\"?([\d.]+)", cmake)
    return VersionRange(
        low=max(map(numbers, lows), key=padded, default=None),
        high=min(map(numbers, highs), key=padded, default=None),
    )


def newest_tag(url: str, wanted: VersionRange) -> str | None:
    """Newest release tag of `url` within `wanted`"""
    try:
        tags = [name.removeprefix("refs/tags/") for name in ls_remote(url, "--tags")]
    except Unreachable:
        return None
    fits = [(v, tag) for tag in tags if (v := parse_version(tag)) and wanted.accepts(v)]
    return max(fits, key=lambda fit: padded(fit[0]))[1] if fits else None


def version_finding(
    user: Source, provider: Source, wanted: VersionRange
) -> tuple[str, str]:
    """Whether `provider` is a version `user` accepts"""
    accepts = f"{user.name} {user.ref} accepts {provider.name} {wanted}"
    if not provider.version:
        return "warning", f"{accepts}; the version of {provider.ref} is unknown"
    if wanted.accepts(provider.version):
        return "ok", f"{accepts}; {provider.ref} is {show(provider.version)}"
    newest = newest_tag(provider.url, wanted)
    hint = f". Newest that fits: {provider.name}={newest}" if newest else ""
    return "error", f"{accepts}, but {provider.ref} is {show(provider.version)}{hint}"


def check_dependencies(sources: dict[str, Source], package_of: dict) -> list:
    """Each package's version and C++ standard against every project using it"""
    findings = []
    for name, spec in package_of.items():
        provider = sources.get(name)
        if not provider:
            continue
        # GCC 13 (Ubuntu 24.04) compiles as C++17 unless told otherwise
        needs_cxx = min(provider.cxx, default=17)
        for user in sources.values():
            if user is provider or not user.cmake:
                continue
            wanted = accepted_range(user.cmake, spec["package"], spec["version_var"])
            if wanted is None:
                continue

            if wanted.low or wanted.high:
                findings.append(version_finding(user, provider, wanted))

            # The provider's headers are compiled as part of the user
            if provider.cmake:
                cxx = max(user.cxx, default=17)
                compiles = f"{user.name} compiles as C++{cxx}"
                if not user.cxx:
                    compiles += " (compiler default)"
                needs = f"{name} {provider.ref} needs C++{needs_cxx}"
                if cxx < needs_cxx:
                    findings.append(("error", f"{compiles}, but {needs}"))
                else:
                    findings.append(("ok", f"{compiles}; {needs}"))
    return findings


def check_fixes(sources: dict[str, Source], rules: list[dict]) -> list:
    """Whether each project includes the fixes it needs, per tools/compat.toml"""
    comparisons = {
        ">=": operator.ge,
        ">": operator.gt,
        "<=": operator.le,
        "<": operator.lt,
        "==": operator.eq,
    }
    findings = []
    for rule in rules:
        source = sources.get(rule["source"])
        other, op, limit = rule["when"].split()
        other = sources.get(other)
        if not (source and source.sha and other and other.version):
            continue
        if not comparisons[op](padded(other.version), padded(numbers(limit))):
            continue

        needs = f"{source.name} {source.ref} with {rule['when']} needs {rule['commit']}"
        needs += f" ({rule['why']})"
        try:
            repo = mirror(source.url)
        except Unreachable as error:
            findings.append(("warning", f"{needs}: could not check, {error}"))
            continue
        commit = f"{rule['commit']}^{{commit}}"
        fix = git("rev-parse", "-q", "--verify", commit, cwd=repo).stdout.strip()
        has = git("merge-base", "--is-ancestor", fix, source.sha, cwd=repo).returncode
        if not fix or has not in (0, 1):
            findings.append(("warning", f"{needs}: could not check"))
        elif has == 0:
            findings.append(("ok", f"{needs}: included"))
        else:
            tags = git("tag", "--contains", fix, cwd=repo).stdout.split()
            releases = sorted((v, tag) for tag in tags if (v := parse_version(tag)))
            where = f"first in {releases[0][1]}" if releases else "not released yet"
            findings.append(("error", f"{needs}: not included, {where}"))
    return findings


def check_same_minor(sources: dict[str, Source], rules: list[dict]) -> list:
    """Whether sources that should share a major.minor version do"""
    findings = []
    for rule in rules:
        pair = [sources[name] for name in rule["sources"] if name in sources]
        if len(pair) < 2 or not all(source.version for source in pair):
            continue
        versions = " and ".join(f"{s.name} {show(s.version)}" for s in pair)
        if len({source.version[:2] for source in pair}) == 1:
            findings.append(("ok", f"{versions} share a major.minor"))
        else:
            findings.append(("warning", f"{versions} differ: {rule['why']}"))
    return findings


def versions_table(sources: dict[str, Source]) -> str:
    rows = [("", "NAME", "REF", "COMMIT", "VERSION", "C++")]
    for source in sources.values():
        version = show(source.version)
        if source.version_from.startswith("after"):
            version += f" ({source.version_from})"
        cxx = "/".join(map(str, source.cxx)) or ("default" if source.cmake else "-")
        sha = (source.sha or "?")[:12]
        mark = "*" if source.changed else ""
        rows.append((mark, source.name, source.ref, sha, version, cxx))
    widths = [max(map(len, column)) for column in zip(*rows)]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths)) for row in rows]
    return "\n".join(line.rstrip() for line in lines)


def check(
    bake: Bake, overrides: dict[str, str], verbose: bool
) -> tuple[dict[str, str], str, bool]:
    """Check the versions; give the pinned overrides, a report and whether they fit"""
    rules = tomllib.loads((bake.root / "tools" / "compat.toml").read_text())
    package_of = rules.get("provides", {})
    describe = set(package_of)
    for rule in rules.get("same_minor", []):
        describe |= set(rule["sources"])

    sources = {
        name: Source(
            name, url, overrides.get(name, bake.variables[name]), name in overrides
        )
        for name, url in bake.urls.items()
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda s: inspect(s, s.name in describe), sources.values()))

    findings = [("error", f"{s.name}: {s.error}") for s in sources.values() if s.error]
    findings += [
        ("warning", f"{s.name}: not checked, could not read it ({s.unreachable})")
        for s in sources.values()
        if s.unreachable
    ]
    findings += check_dependencies(sources, package_of)
    findings += check_fixes(sources, rules.get("needs_commit", []))
    findings += check_same_minor(sources, rules.get("same_minor", []))

    lines = [versions_table(sources), "(* = changed from docker-bake.hcl)", ""]
    levels = ["error", "warning", "ok"] if verbose else ["error", "warning"]
    for level in levels:
        lines += [f"{level:<8} {text}" for found, text in findings if found == level]
    if not verbose:
        passed = sum(level == "ok" for level, _ in findings)
        lines.append(f"ok       {passed} checks passed (--verbose lists them)")

    pinned = {
        name: sources[name].pinned if name in sources else value
        for name, value in overrides.items()
    }
    pinned = {k: v for k, v in pinned.items() if v != bake.variables.get(k)}
    ok = not any(level == "error" for level, _ in findings)
    return pinned, "\n".join(lines), ok


def command_line(env: dict[str, str], command: list[str]) -> str:
    assignments = [f"{k}={shlex.quote(v)}" for k, v in env.items()]
    return " ".join(assignments + [shlex.join(command)])


def build(
    bake: Bake,
    overrides: dict[str, str],
    images: list[str],
    targets: list[str],
    tag: str | None,
    push: bool,
    smoke: bool,
    dry_run: bool,
) -> int:
    """Build `images`, loaded into Docker or pushed, and smoke test them"""
    shown = overrides | ({"TAGS": tag} if tag else {})
    # Pushing sends only the images; calibrate-test has nothing to push
    command = ["docker", "buildx", "bake", *(images if push else targets)]
    for image in images:
        command += ["--set", f"{image}.output=type={'registry' if push else 'docker'}"]
    print(f"\n$ {command_line(shown, command)}", flush=True)
    if dry_run:
        return 0
    env = os.environ | shown
    if subprocess.run(command, cwd=bake.root, env=env).returncode:
        return 1
    if not smoke or push:
        return 0

    registry = env.get("REGISTRY", bake.variables["REGISTRY"])
    image_tag = env.get("TAGS", bake.variables["TAGS"]).split(",")[0].strip()
    image_tag += env.get("TAG_SUFFIX", "")
    for image in images:
        print(f"\n--- smoke tests: {image}", flush=True)
        ref = f"{registry}/{image}:{image_tag}"
        if subprocess.run([bake.root / "tests" / "smoke.sh", image, ref]).returncode:
            return 1
    return 0


def parse_overrides(bake: Bake, args: list[str]) -> dict[str, str]:
    """NAME=REF arguments as a dict, refusing unknown names and odd characters"""
    # These say where and how CI builds, not what is built
    settings = {"CACHE_REF", "CACHE_PUSH", "CACHE_SCOPE", "PLATFORMS", "REVISION"}
    settings |= {"REGISTRY", "TAGS", "TAG_SUFFIX"}
    names = sorted(set(bake.variables) - settings)
    overrides = {}
    for arg in args:
        name, _, value = arg.partition("=")
        if name not in names:
            sys.exit(f"{arg!r}: expected NAME=REF with NAME one of {', '.join(names)}")
        # The value ends up in the environment and image labels
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]*", value):
            sys.exit(f"{arg!r}: {value!r} has characters a ref can't have")
        overrides[name] = value
    return overrides


def get_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="mode", required=True)

    check_parser = subparsers.add_parser(
        "check", help="Check that versions fit together, without building"
    )
    build_parser = subparsers.add_parser(
        "build", help="Check, then build the images the versions change"
    )
    for sub in (check_parser, build_parser):
        sub.add_argument(
            "versions", nargs="*", metavar="NAME=REF", help="e.g. WSCLEAN=master"
        )
        sub.add_argument(
            "--images",
            default="",
            help="Images to build, space separated. Default: those the versions change",
        )
        sub.add_argument(
            "--verbose", "-v", action="store_true", help="List passed checks too"
        )
        sub.add_argument(
            "--summary", type=Path, help="Append a Markdown report to this file"
        )
        sub.add_argument(
            "--github-output", type=Path, help="Write versions= and images= here"
        )

    build_parser.add_argument("--tag", help="Image tag, instead of TAGS (dev)")
    build_parser.add_argument(
        "--smoke", action="store_true", help="Run tests/smoke.sh on each image"
    )
    build_parser.add_argument(
        "--push", action="store_true", help="Push the images instead of loading them"
    )
    build_parser.add_argument(
        "--force", action="store_true", help="Build even if the check fails"
    )
    build_parser.add_argument(
        "--no-check", action="store_true", help="Skip the check (CI ran it already)"
    )
    build_parser.add_argument(
        "--dry-run", action="store_true", help="Print the build command only"
    )
    return parser


def cli() -> int:
    args = get_parser().parse_args()
    bake = read_bake(Path(__file__).resolve().parent.parent)
    overrides = parse_overrides(bake, args.versions)
    if args.mode == "build" and args.tag:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", args.tag):
            sys.exit(f"{args.tag!r} is not a valid image tag")

    ok = True
    if args.mode == "check" or not args.no_check:
        overrides, report, ok = check(bake, overrides, args.verbose)
        print(report)
        if args.summary:
            title = "Versions fit together" if ok else "Versions don't fit together"
            with args.summary.open("a") as file:
                file.write(f"### {title}\n\n```\n{report}\n```\n\n")

    try:
        images, targets = plan(bake, overrides, args.images.split())
    except (OSError, RuntimeError) as error:
        sys.exit(f"Could not work out which images change ({error}); pass --images")
    print(f"\nImages: {' '.join(images) or 'none'}")
    if images:
        bake_command = ["docker", "buildx", "bake", *targets]
        print(f"Build with:\n  {command_line(overrides, bake_command)}")
    if args.github_output:
        with args.github_output.open("a") as file:
            versions = " ".join(f"{k}={v}" for k, v in overrides.items())
            file.write(f"versions={versions}\nimages={' '.join(images)}\n")

    if args.mode == "check":
        return 0 if ok else 1
    if not ok and not args.force:
        print("\nNot building because of the errors above (--force to build anyway)")
        return 1
    if not images:
        return 0
    return build(
        bake,
        overrides,
        images,
        targets,
        tag=args.tag,
        push=args.push,
        smoke=args.smoke,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(cli())
