#!/bin/bash
docker build --platform linux/amd64 -t alecthomson/flint-containers:calibrate . -f Dockerfile-calibrate --push