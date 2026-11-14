# Flint Containers

This be yer compass me-hearties. Find yer way about the seas when sailing with [flint](https://github.com/flint-crew/flint)!

## Get the images

```bash
flint_containers download /path/to/containers --tag {tag}
```

That downloads every image flint needs. For a single image:

```bash
apptainer pull docker://ghcr.io/flint-crew/{image}:{tag}
docker pull ghcr.io/flint-crew/{image}:{tag}
```

Releases are on [GHCR](https://github.com/orgs/flint-crew/packages?repo_name=flint-containers). Old `v1.*` tags still work. [DockerHub](https://hub.docker.com/r/alecthomson/flint-containers/tags) is no longer updated.

## Pick a tag

Use the plain `{tag}` unless you need the speed.

| Tag | Runs on | Speed |
|---|---|---|
| `{tag}` | Any 64-bit x86 or ARM CPU, including Apple Silicon | Baseline |
| `{tag}-x86-64-v3` | x86 with AVX2: most CPUs since about 2015 | Faster |
| `{tag}-x86-64-v4` | x86 with AVX-512, such as Sapphire Rapids and Zen 4 | Fastest |

To find the fastest tag a machine can run:

1. Log in to a compute node, not the login node. They often have different CPUs.
2. Run `/lib64/ld-linux-x86-64.so.2 --help | grep supported`.
3. Use the highest level marked `supported`. On a cluster with mixed nodes, use the oldest node's level.

If step 2 fails (glibc older than 2.33), run `grep -o -w -m1 -e avx512f -e avx2 /proc/cpuinfo | sort -u` instead: `avx512f` means v4, `avx2` means v3.

A tag built for a newer CPU exits at once with `Illegal instruction`.

`latest`, `latest-x86-64-v3` and `latest-x86-64-v4` point to the newest release. aegean, casa and askapsoft have no compiled code, and rclone gains little from a CPU-specific build, so their v3 and v4 tags are the plain image. casa and askapsoft are amd64 only and run under Rosetta on Apple Silicon.

## Images

| Image | Contents | flint uses it for |
|---|---|---|
| `calibrate` | [calibrate](https://github.com/flint-crew/calibrate), André Offringa's calibrate modified by Emil Lenc for ASKAP | `calibrate`, `applysolutions`, `addmodel` |
| `wsclean` | [WSClean](https://wsclean.readthedocs.io/) with [IDG](https://idg.readthedocs.io/) and [EveryBeam](https://everybeam.readthedocs.io/) | `wsclean` |
| `aoflagger` | [AOFlagger](https://aoflagger.readthedocs.io/), without the GUI tools | `aoflagger` |
| `potato` | [PotatoPeel](https://gitlab.com/Sunmish/potato) by Stefan Duchesne, with WSClean and python-casacore | `hot_potato`, `peel_configuration.py` |
| `aegean` | [AegeanTools](https://github.com/PaulHancock/Aegean) by Paul Hancock | `BANE`, `aegean` |
| `casa` | [CASA](https://casa.nrao.edu/) tasks from `casatasks` | `mstransform`, `cvel`, `gaincal`, `applycal` |
| `askapsoft` | [ASKAPsoft](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current) from CSIRO | `linmos` |
| `rclone` | [rclone](https://rclone.org/), a static build | `rclone copy`, to archive products to a folder or an object store |

To see the versions inside an image, run `docker inspect --format '{{json .Config.Labels}}' <image>` or `apptainer inspect <file>.sif`.

- Every image except askapsoft uses one Ubuntu 24.04 base and one casacore build (3.7.1).
- casacore's measures data is in `/opt/measures`. `/opt/measures/SOURCE` records where and when it was downloaded.
- The `casa` command runs `casa -c <code>` with `casatasks`. The GUI, plotms and interactive shell are not included.
- askapsoft is CSIRO's published image, pinned by digest, because its source is not public.
- rclone is compiled with the Go image pinned in `GOLANG_IMAGE`. A new rclone release may need a newer Go: its `go.mod` says which.

### Moving to casacore 3.8

Two upstream releases are needed first. casacore 3.8 no longer makes `string` available without `std::`, and casacore after 3.8.1 needs C++20.

| Tool | Now | Needed for casacore 3.8 |
|---|---|---|
| wsclean | v3.7 | A release containing commit [`5a4dcde`](https://gitlab.com/aroffringa/wsclean/-/commit/5a4dcde) |
| aoflagger | v3.5.0 | A release containing commit [`2c22cfe`](https://gitlab.com/aroffringa/aoflagger/-/commit/2c22cfe) |
| python-casacore | v3.7.1 | v3.8.1 |
| calibrate, IDG, EveryBeam | `3e5e84a`, 1.2.0, v0.8.5 | No change |

`tools/try_build.py check` knows these requirements and reports when a combination will work.

## Try new versions

To build images with versions that are not in `docker-bake.hcl` yet:

1. Open Actions, then **Try versions**, then **Run workflow**.
2. In the box for each tool to change, type a tag, branch or commit. Leave the other boxes empty.
3. Tick **push** to publish the images, then press **Run workflow**.

The compatibility check runs first and takes about 1 minute. If the versions cannot work together, the run stops there and says why. Otherwise it builds only the changed images for amd64 and runs the tests: about 15 to 30 minutes, depending on which images change.

With **push**, the images are at `ghcr.io/flint-crew/<image>:try-<label>`. The run summary lists the `apptainer pull` commands.

From a terminal:

```bash
gh workflow run try.yml -f wsclean=master -f everybeam=v0.9.1    # the same run as the form
tools/try_build.py check WSCLEAN=master EVERYBEAM=v0.9.1          # only the check, about 1 minute
tools/try_build.py build WSCLEAN=master EVERYBEAM=v0.9.1 --smoke  # check, then build locally
```

The check reads each project's `CMakeLists.txt` at the given version. It reports:

- A dependency version outside the range a project accepts, and the newest tag that fits.
- A casacore that needs a newer C++ standard than a project compiles with.
- A fix commit that a project is missing, from the rules in [`tools/compat.toml`](tools/compat.toml).
- python-casacore and casacore with different major.minor versions, as a warning.

The check cannot catch everything. When a build fails for a reason it could have caught, add a rule to `tools/compat.toml`.

To keep versions that work:

1. Put the versions that the check prints into `docker-bake.hcl`.
2. Open a pull request. CI runs the check, then builds every image for every CPU target: about 30 minutes.

## Build

```bash
docker buildx bake wsclean      # one image
docker buildx bake              # every image
docker buildx bake test         # calibrate's own test suite
docker buildx bake --print      # what would be built, with every version and tag
```

Other builds:

```bash
MARCH=x86-64-v3 TAG_SUFFIX=-x86-64-v3 docker buildx bake compiled                 # for one CPU target
docker buildx bake calibrate --set calibrate.contexts.calibrate-src=../calibrate  # from a local checkout
```

## Test

```bash
tests/smoke.sh wsclean ghcr.io/flint-crew/wsclean:{tag}
```

That runs the image the way Apptainer runs it for flint: read-only, non-root, with no home directory. It checks the commands, their versions and the shared libraries.

To run flint's own call sites against Apptainer images:

```bash
pip install "askap-flint[casa]" pytest
pytest tests/flint_compat --container-dir /path/to/containers
```
