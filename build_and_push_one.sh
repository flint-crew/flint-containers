#!/bin/bash

dockerfile=$1

# check if the dockerfile exists
if [ ! -f $dockerfile ]; then
    echo "'$dockerfile' does not exist"
    exit 1
fi

docker build \
    --platform linux/amd64 \
    -t alecthomson/flint-containers:${dockerfile#Dockerfile-} \
    . \
    -f $dockerfile \
    --push