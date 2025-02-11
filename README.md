# Flint Containers

This be yer compass me-hearties. Find yer way about the seas when sailing with [flint](https://github.com/tjgalvin/flint)!

## What is this?

Build scripts for containers to use with the [flint pipeline](https://github.com/tjgalvin/flint).

## Where are the cotainers?

Each container is built and pushed to [DockerHub](https://hub.docker.com/r/alecthomson/flint-containers/tags). Each application is available under a different tag.

To get them you can run

```bash
# for docker
docker pull alecthomson/flint-containers:calibrate
docker pull alecthomson/flint-containers:askapsoft
docker pull alecthomson/flint-containers:aoflagger
docker pull alecthomson/flint-containers:wsclean
docker pull alecthomson/flint-containers:aegean
docker pull alecthomson/flint-containers:potato
```

or

```bash
# for singularity / apptainer
singularity pull docker://alecthomson/flint-containers:calibrate
singularity pull docker://alecthomson/flint-containers:askapsoft
singularity pull docker://alecthomson/flint-containers:aoflagger
singularity pull docker://alecthomson/flint-containers:wsclean
singularity pull docker://alecthomson/flint-containers:aegean
singularity pull docker://alecthomson/flint-containers:potato
```

## Supported containers

- calibrate: André Offringa's calibrate. Modified by Emil Lenc for use with ASKAP.
- [ASKAPsoft](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current): Interferometric applications developed for the ASKAP radio telescope by CSIRO.
- [AOFlagger](https://aoflagger.readthedocs.io/en/latest/): Automatic RFI flagger developed by André Offringa.
- [WSClean](https://wsclean.readthedocs.io/en/latest/): WSClean (w-stacking clean) is a fast generic widefield imager developed by André Offringa.
- [Aegean](https://github.com/PaulHancock/Aegean): AegeanTools source finding package developed by Paul Hancock.
- [PotatoPeel](https://gitlab.com/Sunmish/potato): Peel out that annoying, terrible object developed by Stefan Duchesne.
