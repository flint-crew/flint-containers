# Flint Containers

This be yer compass me-hearties. Find yer way about the seas when sailing with [flint](https://github.com/tjgalvin/flint)!

## What is this?

Build scripts for containers to use with the [flint pipeline](https://github.com/tjgalvin/flint).

## Where are the cotainers?

Each container is built and pushed to the Github Container Registry. The containers for each application are published as separated packages under the [flint-crew GitHub page](https://github.com/orgs/flint-crew/packages?repo_name=flint-containers).

We previously published to [DockerHub](https://hub.docker.com/r/alecthomson/flint-containers/tags), these are no longer updated.

Each application is available under its name with a tag attached from the latest release or git hash from this repository. See the [packages](https://github.com/orgs/flint-crew/packages?repo_name=flint-containers) to get the correct name and tag for your usage.

To get a container you can run

```bash
# for docker
docker pull ghcr.io/flint-crew/{application}:{tag}
```

or

```bash
# for singularity / apptainer
singularity pull docker://ghcr.io/flint-crew/{application}:{tag}
```

## Supported containers

- calibrate: André Offringa's calibrate. Modified by Emil Lenc for use with ASKAP.
- [ASKAPsoft](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current): Interferometric applications developed for the ASKAP radio telescope by CSIRO.
- [AOFlagger](https://aoflagger.readthedocs.io/en/latest/): Automatic RFI flagger developed by André Offringa.
- [WSClean](https://wsclean.readthedocs.io/en/latest/): WSClean (w-stacking clean) is a fast generic widefield imager developed by André Offringa.
- [Aegean](https://github.com/PaulHancock/Aegean): AegeanTools source finding package developed by Paul Hancock.
- [PotatoPeel](https://gitlab.com/Sunmish/potato): Peel out that annoying, terrible object developed by Stefan Duchesne.
- [CASA](https://casa.nrao.edu/): The Common Astronomy Software Applications package, developed by NRAO.
