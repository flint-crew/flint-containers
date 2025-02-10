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
```

or

```bash
# for singularity / apptainer
singularity pull docker://alecthomson/flint-containers:calibrate
singularity pull docker://alecthomson/flint-containers:askapsoft
singularity pull docker://alecthomson/flint-containers:aoflagger
singularity pull docker://alecthomson/flint-containers:wsclean
singularity pull docker://alecthomson/flint-containers:aegean
```
