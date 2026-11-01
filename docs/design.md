# Design proposal: pinned, from-source container builds

**Status:** proposal, for discussion in this PR. No code changes yet.

This document proposes how `flint-containers` should build its images going
forward. It is deliberately short. The aim is to agree on the direction here,
then land the work as a series of small PRs (see [Roadmap](#roadmap)).

## Why change anything?

Today each image is built a different way:

| Image | How it's built today | Problem |
|---|---|---|
| wsclean, aoflagger | `kernsuite/base:9` + `docker-apt-install` | Version is whatever KERN ships. Nothing is pinned. |
| potato | KERN wsclean + uv installer piped from the web + `git+…potato.git` | Potato tracks `HEAD`. Its wsclean isn't shared with the wsclean image. |
| aegean | `uv:python3.12-bookworm` + `git+…Aegean.git` | Tracks `HEAD`. Uses a Debian base, unlike everything else. |
| calibrate | ubuntu:24.04 + apt casacore 3.5 + git submodule | Compilers and sources stay in the image, and each `RUN` adds a layer, so the image is large. |
| casa | `redhat/ubi8:latest` + monolithic 6.6.5 tarball | Very large. Uses a floating `:latest` base. Data lives in `$HOME/.casa`, which the HOME bind hides under Apptainer. |
| askapsoft | `FROM csirocass/askapsoft:1.17.6-openmpi4` | Old (1.23.1 is current). Not built from source. |

Consequences:

- **Not reproducible.** Rebuilding the same git commit can silently produce
  different software, because KERN, `HEAD` and `:latest` all move.
- **No single place says what versions are in a release.**
- **Large images.** They use three unrelated base distros, so no layers are
  shared, and the build tools are left inside.
- **Leftovers:** `build_*.sh` still push to the retired Docker Hub repo.

## Goals

1. **Every package is built from source at a pinned version** (a git tag, or a
   commit when upstream has no tags), declared in **one file**.
2. **Small runtime images**, using multi-stage builds so compilers, headers and
   sources never ship.
3. **Shared layers.** All images sit on one base, and every C++ tool shares one
   casacore layer.
4. **Optimised builds.** Images are multi-arch (amd64 and arm64), with
   additional x86-64-v3 and x86-64-v4 tags for newer CPUs.
5. **flint keeps working with no changes** (see [Compatibility](#compatibility-with-flint)).

## Proposed layer tree

```
ubuntu:24.04@sha256:…                      (pinned by digest)
├─ build-base        compilers + -dev packages        (build only, never shipped)
│   └─ casacore-build   /opt/casacore
│       └─ per-app build stages → /opt/<app>
└─ runtime-base      runtime .so files only + python3 + /opt/measures
    ├─ aegean        + /opt/venv (AegeanTools @ tag)
    ├─ casa          + /opt/venv (casatools/casatasks) + casa data + `casa` shim   [amd64]
    └─ casacore      + /opt/casacore
        ├─ calibrate + /opt/calibrate   (calibrate, applysolutions, addmodel)
        ├─ aoflagger + /opt/aoflagger
        ├─ askapsoft + /opt/yandasoft   (linmos)                                    [amd64]
        └─ wsclean   + /opt/wsclean     (IDG + EveryBeam + wsclean)
            └─ potato + /opt/venv       (python-casacore + potato)
```

- Each app installs into its own `/opt/<app>` prefix and is copied into its
  runtime image as **one layer**.
- Apptainer `.sif` files are flattened, so Apptainer users benefit from the
  smaller sizes rather than from the sharing. Layer sharing still speeds up
  `docker pull`, registry storage and CI caching.

## Pinned versions (starting point)

| Component | Version | Source |
|---|---|---|
| Ubuntu | 24.04 (by digest) | Docker Hub |
| casacore | v3.7.1 | github.com/casacore/casacore |
| wsclean | v3.7 | gitlab.com/aroffringa/wsclean |
| IDG, EveryBeam | latest releases compatible with wsclean 3.7 | git.astron.nl |
| aoflagger | v3.5.0 | gitlab.com/aroffringa/aoflagger |
| calibrate | `c1fb4c6` (same commit as the current submodule) | github.com/flint-crew/calibrate |
| AegeanTools | v2.3.4 | github.com/PaulHancock/Aegean |
| potato | `4bb4940` (upstream has no tags) | gitlab.com/Sunmish/potato |
| python-casacore | v3.7.1 | github.com/casacore/python-casacore |
| casatools / casatasks | 6.7.6.14 | PyPI (NRAO wheels) |
| yandasoft (linmos) | 1.23.1 | bitbucket.csiro.au, if publicly reachable (see below) |

Why casacore 3.7.1 rather than 3.8.x: it matches python-casacore 3.7.1 and
CSIRO's own askapsoft 1.23.1 build. Bumping it later is a one-line change.

## Tooling: `docker buildx bake`

The builds are driven by [`docker buildx bake`](https://docs.docker.com/build/bake/),
Docker's built-in tool for building several related images at once. It's part
of `buildx`, which the current GitHub workflow already uses. It reads a
`docker-bake.hcl` file:

```hcl
variable "CASACORE" { default = "v3.7.1" }   # github.com/casacore/casacore
variable "WSCLEAN"  { default = "v3.7" }     # gitlab.com/aroffringa/wsclean

target "wsclean" {
  dockerfile = "docker/wsclean/Dockerfile"
  contexts   = { casacore = "target:casacore" }   # reuse the shared casacore build
  args       = { WSCLEAN = WSCLEAN }
}
```

- **Local build:** `docker buildx bake wsclean` builds casacore first
  automatically.
- **Preview:** `docker buildx bake --print` shows exactly what would be built,
  with which versions and tags.
- **Bumping a version:** edit one line and open a PR. CI builds the image and
  runs the flint compatibility tests.

The alternative was plain Dockerfiles plus a GitHub Actions matrix. That
scatters versions across Dockerfiles and YAML, and needs the build order
managed by hand.

## CPU targets

- C++ code is compiled for an explicit `-march`.
  - The aocommon-based projects (wsclean, aoflagger and the like) are built with
    `-DPORTABLE=OFF -DTARGET_CPU=<march>`.
  - **`TARGET_CPU` is never left empty.** If it were, aocommon's CMake would
    fall back to `-march=native`, which bakes in the CI runner's CPU.
- **Default tag:** multi-arch, with amd64 built for `x86-64-v2` and arm64 for
  `armv8.2-a`. Runs on essentially any current HPC node.
- **Extra tags:** `-x86-64-v3` (AVX2; e.g. AMD Milan/Genoa, Intel Haswell+) and
  `-x86-64-v4` (AVX-512).
- **Python-only images** (aegean, casa) are built once, because their wheels
  pick CPU features at runtime. They get the variant tags as aliases, so every
  tag exists for every image.

## CASA

flint only calls `casa -c <task>(...)` for `mstransform`, `cvel`, `applycal`
and `gaincal`. All four are in the modular `casatasks` package, so the proposal
is:

- Install pinned `casatools` and `casatasks` wheels.
- Add a small `casa` command that accepts `casa -c <code>` the way flint calls
  it. That means re-joining arguments that flint has split on whitespace.
- Store CASA data under `/opt`, found via `CASASITECONFIG` rather than `$HOME`.

This removes the multi-GB monolithic install. NRAO only publishes Linux wheels
for x86_64, so the image is amd64-only (as it effectively is today).

## ASKAPsoft (linmos)

- flint only runs `linmos -c <parset>`.
- yandasoft's GitHub mirror (ATNF/yandasoft) was **archived in January 2026**
  and points to CSIRO Bitbucket.
- yandasoft needs about 9 repositories (lofar-common, lofar-blob, base-askap,
  base-logfilters, base-imagemath, base-scimath, base-askapparallel,
  base-accessors, yandasoft).

The first step is a CI job that checks whether those repositories can be cloned
anonymously:

- **If they can:** build linmos from source on the shared casacore layer.
- **If not:** use CSIRO's image pinned by digest
  (`csirocass/askapsoft:1.23.1-mpich@sha256:…`), and switch to source builds
  when possible. The image name and the flint interface are the same either
  way.

## Compatibility with flint

This is a hard requirement: `flint/containers.py` and every flint task that
runs a container must keep working.

1. **Names unchanged.** Images stay at
   `ghcr.io/flint-crew/{calibrate,wsclean,askapsoft,aoflagger,aegean,potato,casa}`,
   and `.sif` files keep the names `flint-containers_<name>.sif`.
2. **Existing tags are never overwritten.** `v1.0` to `v1.2.2` stay exactly as
   they are, so flint's current default (`tag="v1.0"`) is unaffected.
3. **Every release tags all seven images.**
   - `flint_containers download --tag X` applies one tag to every image, so a
     new release `vX.Y.Z`, and each `vX.Y.Z-<variant>`, exists for all seven.
   - casa and askapsoft are amd64-only, so a full download on an arm64 host
     fails for those two. This will be documented.
4. **Runs under Apptainer the way flint calls it.**
   - flint runs `apptainer exec <sif> <command.split()>`: no shell, the host
     `$HOME` bound in, and a read-only image.
   - So every executable is on `PATH`, and nothing depends on `$HOME` or on
     writing inside the image.
5. **Executables per image:**

   | Image | Executables |
   |---|---|
   | calibrate | `calibrate`, `applysolutions`, `addmodel` |
   | wsclean | `wsclean` |
   | aoflagger | `aoflagger` |
   | aegean | `BANE`, `aegean` |
   | potato | `hot_potato`, `peel_configuration.py`, `wsclean` |
   | casa | `casa -c …` |
   | askapsoft | `linmos` |

6. **Output flint parses stays the same.** These log strings are matched in
   callbacks: wsclean's divergence and I/O-error messages, and BANE's
   "must be strictly ascending or descending".

To keep this true, CI gets a **flint compatibility job**:

- It installs Apptainer and flint, and builds `.sif` files from the new images.
- It runs **flint's own functions** for every container call site against
  flint's example measurement set: flagging, calibrate and applysolutions,
  addmodel, wsclean, BANE and aegean, linmos, the four CASA tasks, and potato.
- It runs on every PR, so a version bump that breaks flint is caught before
  anything is tagged.

## CI and publishing

- **Pull requests:** build and test, then push only to throwaway tags
  `ghcr.io/flint-crew/<app>:pr-<N>`, so reviewers can
  `apptainer pull docker://ghcr.io/flint-crew/<app>:pr-<N>` and try it.
- **Push to `main`:** `edge` tag. **Release:** `vX.Y.Z` (+ variants) and
  upstream-version tags such as `wsclean:3.7`.
- **Runners:** native arm64 GitHub runners (no QEMU emulation), and a registry
  build cache (the current GitHub Actions cache has a 10 GB limit).
- **Provenance:** build-provenance attestation is re-enabled (it's commented
  out today).
- **Labels:** every image carries OCI labels listing its component versions, so
  `apptainer inspect` shows what's inside.

## Roadmap

Each PR stands alone. Nothing existing changes until the final cutover: the
current `Dockerfile-*` files and `docker-publish.yml` keep publishing as today
until then.

| # | PR | Agreed in this PR |
|---|----|-------------------|
| 0 | This design doc | The overall direction |
| 1 | Foundations: `docker-bake.hcl`, shared base + casacore, **calibrate**, smoke tests, flint compatibility job, ASKAPsoft source probe | bake, base layer, casacore version, `/opt` layout, test approach |
| 2 | wsclean (IDG + EveryBeam), aoflagger, potato | C++ tool versions and wsclean features |
| 3 | aegean, casa (modular + `casa` shim) | Dropping the monolithic CASA |
| 4 | askapsoft (source or pinned upstream, depending on the probe) | ASKAPsoft sourcing |
| 5 | arm64, CPU-variant tags, multi-arch manifests, attestation | Which variants to publish |
| 6 | Cutover: new workflow publishes releases; old files removed; README rewrite; release `v2.0.0` | Switching over |
| 7 | *(optional, flint repo)* bump flint's default container tag; add a `--variant` download option | flint adopting the new images |

PRs 2, 3 and 4 are independent once PR 1 is merged.

## Open questions for review

- Is casacore 3.7.1 the right starting point, or go straight to 3.8.x?
- Which CPU variants are worth the CI time? Proposed: `x86-64-v3` and
  `x86-64-v4`, plus the multi-arch default.
- Should the shared bases (`runtime-base`, `casacore`) be published as their
  own images for others to build on?
- Measures data is downloaded at build time (a dated snapshot, recorded in a
  label). Is a monthly scheduled rebuild to refresh it wanted?
