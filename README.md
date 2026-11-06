# Flint Containers

This be yer compass me-hearties. Find yer way about the seas when sailing with [flint](https://github.com/flint-crew/flint)!

Container images for the tools flint runs. Each is built from source at a version pinned in [`docker-bake.hcl`](docker-bake.hcl).

**Jump to:** [Get the images](#get-the-images) · [Pick a tag](#pick-a-tag) · [Images](#images) · [Try new versions](#try-new-versions) · [Build](#build) · [Test](#test)

## Get the images

```bash
flint_containers download /path/to/containers --tag {tag}   # all of them, via flint
apptainer pull docker://ghcr.io/flint-crew/{image}:{tag}    # one, Apptainer
docker pull ghcr.io/flint-crew/{image}:{tag}                # one, Docker
```

- Published to [GHCR](https://github.com/orgs/flint-crew/packages?repo_name=flint-containers) on each release.
- Old `v1.*` tags still work. [DockerHub](https://hub.docker.com/r/alecthomson/flint-containers/tags) is no longer updated.

## Pick a tag

| Tag | Runs on | Speed |
|---|---|---|
| `{tag}` | Any 64-bit x86 or ARM CPU, including Apple Silicon | Baseline |
| `{tag}-x86-64-v3` | x86 with AVX2 (most CPUs since ~2015) | Faster |
| `{tag}-x86-64-v4` | x86 with AVX-512 (e.g. Sapphire Rapids, Zen 4) | Fastest |

**Not sure? Use the plain `{tag}`.** A build too new for the CPU exits with `Illegal instruction`.

To check a machine, run on a **compute node** (not the login node):

```bash
/lib64/ld-linux-x86-64.so.2 --help | grep supported          # use the highest "supported" level
grep -o -w -m1 -e avx512f -e avx2 /proc/cpuinfo | sort -u    # older glibc: avx512f = v4, avx2 = v3
```

- On a mixed cluster, pick the tag for the oldest nodes.
- `latest`, `latest-x86-64-v3` and `latest-x86-64-v4` follow the newest release.
- aegean, casa and askapsoft have no compiled code, so their v3/v4 tags are the plain image.
- casa and askapsoft are amd64 only (Rosetta on Apple Silicon).

## Images

| Image | Contents | flint uses it for |
|---|---|---|
| `calibrate` | [calibrate](https://github.com/flint-crew/calibrate) (Offringa, ASKAP changes by Lenc) | `calibrate`, `applysolutions`, `addmodel` |
| `wsclean` | [WSClean](https://wsclean.readthedocs.io/) + [IDG](https://idg.readthedocs.io/) + [EveryBeam](https://everybeam.readthedocs.io/) | `wsclean` |
| `aoflagger` | [AOFlagger](https://aoflagger.readthedocs.io/), no GUI | `aoflagger` |
| `potato` | [PotatoPeel](https://gitlab.com/Sunmish/potato) (Duchesne) + WSClean + python-casacore | `hot_potato`, `peel_configuration.py` |
| `aegean` | [AegeanTools](https://github.com/PaulHancock/Aegean) (Hancock) | `BANE`, `aegean` |
| `casa` | [CASA](https://casa.nrao.edu/) tasks via `casatasks` | `mstransform`, `cvel`, `gaincal`, `applycal` |
| `askapsoft` | [ASKAPsoft](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current) | `linmos` |

- **One casacore** (3.7.1) and one Ubuntu 24.04 base for everything except askapsoft.
- **Measures data** is in `/opt/measures`; `/opt/measures/SOURCE` says where and when it came from.
- **`casa`** is a small script running `casa -c <code>` with `casatasks`. No GUI, plotms or shell.
- **askapsoft** is CSIRO's published image, pinned by digest (its source isn't public).
- **Versions inside an image:** `docker inspect --format '{{json .Config.Labels}}' <image>` or `apptainer inspect <file>.sif`.

### Moving to casacore 3.8

Blocked on two releases. casacore 3.8 drops `string` without `std::`, and casacore after 3.8.1 needs C++20.

| Tool | Now | Needs for 3.8 |
|---|---|---|
| wsclean | v3.7 | a release with [`5a4dcde`](https://gitlab.com/aroffringa/wsclean/-/commit/5a4dcde) |
| aoflagger | v3.5.0 | a release with [`2c22cfe`](https://gitlab.com/aroffringa/aoflagger/-/commit/2c22cfe) |
| python-casacore | v3.7.1 | v3.8.1 |
| calibrate, IDG, EveryBeam | `3e5e84a`, 1.2.0, v0.8.5 | nothing |

`tools/try_build.py check` knows these rules, so it will say when a combination works.

## Try new versions

**On GitHub:** Actions → **Try versions** → **Run workflow**.

1. Type a tag, branch or commit in the box for each tool to change. Leave the rest empty.
2. Tick **push** to publish as `ghcr.io/flint-crew/<image>:try-<label>`.
3. Press **Run workflow**.

It checks compatibility first (~1 min) and stops if the versions can't work. Then it builds only the changed images (amd64), and runs the smoke and flint tests.

**From a terminal:**

```bash
gh workflow run try.yml -f wsclean=master -f everybeam=v0.9.1                # same thing via gh
tools/try_build.py check WSCLEAN=master EVERYBEAM=v0.9.1                     # just the check
tools/try_build.py build WSCLEAN=master EVERYBEAM=v0.9.1 --smoke             # build locally
```

The check reads each project's `CMakeLists.txt` and flags:

- a dependency outside the range a project accepts (and suggests the newest tag that fits)
- casacore needing a newer C++ standard than a project uses
- missing fix commits listed in [`tools/compat.toml`](tools/compat.toml)
- python-casacore and casacore on different major.minor versions (warning)

It's a quick filter, not a guarantee. **When a build fails for a reason it could have caught, add a rule to `tools/compat.toml`.**

**Happy with it?** Put the printed versions in `docker-bake.hcl` and open a PR. CI reruns the check first, then builds every image for every CPU target.

## Build

```bash
docker buildx bake --print          # what would be built
docker buildx bake wsclean          # one image
docker buildx bake                  # everything
docker buildx bake test             # calibrate's own tests
MARCH=x86-64-v3 TAG_SUFFIX=-x86-64-v3 docker buildx bake compiled             # a CPU target
docker buildx bake calibrate --set calibrate.contexts.calibrate-src=../calibrate   # local calibrate
```

## Test

- **`tests/smoke.sh <image> <ref>`** runs an image the way Apptainer runs it for flint (read-only, non-root, no home). Checks the commands, their versions, and shared libraries.
- **`tests/flint_compat/`** runs flint's own call sites against Apptainer images:

```bash
pip install "askap-flint[casa]" pytest
pytest tests/flint_compat --container-dir /path/to/containers
```
