# Flint Containers

This be yer compass me-hearties. Find yer way about the seas when sailing with [flint](https://github.com/flint-crew/flint)!

## What is this?

Container images for the tools the [flint pipeline](https://github.com/flint-crew/flint) runs. Each tool is built from source at a pinned version, except ASKAPsoft (see below). The versions are set in [`docker-bake.hcl`](docker-bake.hcl).

## Getting the images

Images are published to the GitHub Container Registry under [flint-crew](https://github.com/orgs/flint-crew/packages?repo_name=flint-containers) when a release is made.

```bash
# Apptainer / Singularity
apptainer pull docker://ghcr.io/flint-crew/{image}:{tag}

# Docker
docker pull ghcr.io/flint-crew/{image}:{tag}
```

flint can download all of them at once:

```bash
flint_containers download /path/to/containers --tag {tag}
```

Older images (tags `v1.*`) were built from the previous Dockerfiles and are still available. We previously published to [DockerHub](https://hub.docker.com/r/alecthomson/flint-containers/tags); those are no longer updated.

### Tags and CPU targets

Each release `{tag}` is published as:

| Tag | Platforms | Compiled for |
|---|---|---|
| `{tag}` | linux/amd64, linux/arm64 | Any 64-bit x86 CPU (`x86-64`), or any 64-bit ARM CPU including Apple Silicon (`armv8-a`) |
| `{tag}-x86-64-v3` | linux/amd64 | x86 CPUs with AVX2: most Intel and AMD CPUs from about 2015 |
| `{tag}-x86-64-v4` | linux/amd64 | x86 CPUs with AVX-512, such as Intel Sapphire Rapids and AMD Zen 4 |

The `-x86-64-v3` and `-x86-64-v4` builds are faster where the CPU supports them, but will not start on a CPU that doesn't. Use the plain `{tag}` if unsure. `latest`, `latest-x86-64-v3` and `latest-x86-64-v4` point to the most recent release.

#### Which tag to use

`apptainer pull` and `docker pull` pick between amd64 and arm64 by themselves. They do not pick between the plain, `-x86-64-v3` and `-x86-64-v4` builds; you choose those by tag.

To see what a machine supports, run this on it:

```bash
/lib64/ld-linux-x86-64.so.2 --help | grep supported
```

Example output on a machine that supports v3 but not v4:

```
  x86-64-v4
  x86-64-v3 (supported, searched)
  x86-64-v2 (supported, searched)
```

Use the highest level marked `supported`. If the command isn't available (glibc older than 2.33), check the CPU flags instead: `avx512f` means v4 works, and `avx2` means v3 works.

```bash
grep -o -w -m1 -e avx512f -e avx2 /proc/cpuinfo | sort -u
```

On a cluster, run the check on a compute node (for example inside an `srun` job), not the login node. They often have different CPUs, and an image built for the login node's CPU may fail on the compute nodes. If a cluster has a mix of node types, use the tag for the oldest ones, or the plain tag.

If an image is used on a CPU it wasn't built for, programs exit straight away with `Illegal instruction`.

aegean, casa and askapsoft have no compiled code of our own, so their `-x86-64-v3`/`-v4` tags are the same image as the plain tag. casa and askapsoft are amd64 only; on Apple Silicon they run under Rosetta.

## Images

| Image | Contents | Used by flint for |
|---|---|---|
| `calibrate` | [calibrate](https://github.com/flint-crew/calibrate): André Offringa's calibrate, modified by Emil Lenc for ASKAP | `calibrate`, `applysolutions`, `addmodel` |
| `wsclean` | [WSClean](https://wsclean.readthedocs.io/) with [IDG](https://idg.readthedocs.io/) and [EveryBeam](https://everybeam.readthedocs.io/) | `wsclean` |
| `aoflagger` | [AOFlagger](https://aoflagger.readthedocs.io/) (no GUI tools) | `aoflagger` |
| `potato` | [PotatoPeel](https://gitlab.com/Sunmish/potato) by Stefan Duchesne, with WSClean and python-casacore | `hot_potato`, `peel_configuration.py` |
| `aegean` | [AegeanTools](https://github.com/PaulHancock/Aegean) by Paul Hancock | `BANE`, `aegean` |
| `casa` | [CASA](https://casa.nrao.edu/) tasks from NRAO's `casatools`/`casatasks` packages | `casa -c mstransform(...)`, `cvel`, `gaincal`, `applycal` |
| `askapsoft` | [ASKAPsoft](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current) from CSIRO | `linmos` |

Notes:

- All images except askapsoft share one Ubuntu 24.04 base, and the C++ tools share one casacore build, so they use the same casacore version.
- casacore's measures data (IERS tables, ephemerides) is in `/opt/measures`. Where and when it was downloaded is recorded in `/opt/measures/SOURCE`.
- The `casa` command in the casa image is a small script that runs `casa -c <code>` using `casatasks`. It replaces the full CASA application, which is several GB. Other CASA features (the GUI, plotms, the interactive shell) are not included.
- The ASKAPsoft source code is not publicly available, so the askapsoft image is CSIRO's published image, pinned by digest.

### casacore version

All images except askapsoft use the same casacore build, version 3.7.1, so every tool reads and writes measurement sets with the same casacore version.

We plan to move to casacore 3.8. The current releases of two of the tools do not build against it, because casacore 3.8 no longer makes `string` available without `std::`. The fixes are in their main branches but not yet released. casacore after 3.8.1 also needs C++20; calibrate picks C++20 by itself for casacore 3.6 and newer.

| Tool | Version used | Builds with casacore 3.7 | Builds with casacore 3.8 | Fix needed for 3.8 |
|---|---|---|---|---|
| wsclean | v3.7 | yes | no | wsclean commit [`5a4dcde`](https://gitlab.com/aroffringa/wsclean/-/commit/5a4dcde) (after v3.7) |
| aoflagger | v3.5.0 | yes | no | aoflagger commit [`2c22cfe`](https://gitlab.com/aroffringa/aoflagger/-/commit/2c22cfe) (after v3.5.0) |
| calibrate | `3e5e84a` | yes | yes | none |
| IDG | 1.2.0 | yes | yes | none |
| EveryBeam | v0.8.5 | yes | yes | none |
| python-casacore | v3.7.1 | yes | use v3.8.1 | none |

TODO: when wsclean and aoflagger have releases that include those commits, update `CASACORE` and `PYTHON_CASACORE` in `docker-bake.hcl` together with the tool versions.

To see the versions inside an image:

```bash
docker inspect --format '{{json .Config.Labels}}' ghcr.io/flint-crew/wsclean:{tag}
apptainer inspect flint-containers_wsclean.sif
```

## Building

Builds use [`docker buildx bake`](https://docs.docker.com/build/bake/), which reads `docker-bake.hcl`.

```bash
# Show what would be built, with every version and tag
docker buildx bake --print

# Build one image and the shared stages it needs
docker buildx bake wsclean

# Build every image
docker buildx bake

# Build the compiled images for a specific CPU
MARCH=x86-64-v3 TAG_SUFFIX=-x86-64-v3 docker buildx bake compiled

# Run calibrate's own test suite
docker buildx bake test
```

To build calibrate from a local checkout instead of the pinned commit:

```bash
docker buildx bake calibrate --set calibrate.contexts.calibrate-src=../calibrate
```

### Trying new versions

`tools/try_build.py` checks whether a set of versions can work together before anything is compiled, then builds only the images they change. Give each version as `NAME=REF`, where `NAME` is a variable in `docker-bake.hcl` and `REF` is a tag, branch or commit:

```bash
# About a minute: is this combination compatible? Which images does it change?
tools/try_build.py check WSCLEAN=master EVERYBEAM=v0.9.1

# Check, then build those images locally and run the smoke tests on them
tools/try_build.py build WSCLEAN=master EVERYBEAM=v0.9.1 --smoke
```

The check reads each project's `CMakeLists.txt` at the given version and reports:

- dependency versions outside the range a project accepts (for example, wsclean's accepted EveryBeam range), with the newest tag that fits
- casacore headers that need a newer C++ standard than a project compiles with (for example, casacore 3.8.2 needs C++20, which python-casacore 3.7.1 doesn't use)
- fixes a project needs under a condition, such as the wsclean and aoflagger commits needed for casacore 3.8, listed in [`tools/compat.toml`](tools/compat.toml)
- python-casacore and casacore versions with a different major.minor (a warning)

Branches are pinned to their current commit, and the output ends with the exact `docker buildx bake` command to run. When a build fails for a reason the check could have caught, add a rule to `tools/compat.toml`. The check is a quick filter: a build can still fail on problems that only show up when compiling.

To try versions in CI without opening a pull request, go to **Actions > Try versions > Run workflow**. It opens a form with a box for each tool (casacore, python-casacore, wsclean, EveryBeam, IDG, aoflagger, calibrate, potato, Aegean, CASA). Type a tag, branch or commit into the ones to change, leave the rest empty to keep the versions pinned in `docker-bake.hcl`, and press **Run workflow**. Tick **push** to publish the results as `ghcr.io/flint-crew/<image>:try-<label>`. The same from the command line:

```bash
gh workflow run try.yml -f wsclean=master -f everybeam=v0.9.1
gh workflow run try.yml -f wsclean=master -f everybeam=v0.9.1 -f push=true -f label=wsclean-master
```

It runs the check first and stops there if the versions don't fit. Otherwise it builds the changed images for amd64 (`x86-64`) only, then runs the smoke tests and flint's container call sites. A try's tags are never `latest` and are not CPU-specific.

### Changing a version

Once a combination works, put the versions printed by `tools/try_build.py check` into `docker-bake.hcl` and open a pull request. CI runs the same check in its lint job, so incompatible versions fail within about a minute, then builds every image for every CPU target and runs the tests below.

### Tests

- `tests/smoke.sh <image> <ref>` runs an image the way Apptainer runs it for flint (read-only, non-root, no home directory). It checks that the expected commands run, that they report the version in the image's labels, and that no shared libraries are missing.
- `tests/flint_compat/` runs flint's own functions for each container call site (flagging, calibration, imaging, source finding, linmos, the CASA tasks and peeling) against Apptainer images, using flint's example measurement set.

```bash
pip install "askap-flint[casa]" pytest
pytest tests/flint_compat --container-dir /path/to/containers
```
