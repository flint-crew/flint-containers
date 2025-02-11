#!/bin/bash
for i in $(ls Dockerfile-*); do
    ./build_and_push_one.sh $i
done
