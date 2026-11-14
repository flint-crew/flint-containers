# rclone, compiled from source, in /opt/rclone. flint uses it to copy archived
# products to a folder or an object store.
# Build with: docker buildx bake rclone

ARG GOLANG_IMAGE

# Go cross-compiles, so the compiler runs on the build machine's own platform
# rather than under emulation.
FROM --platform=${BUILDPLATFORM} ${GOLANG_IMAGE} AS build
ARG RCLONE
ARG TARGETOS
ARG TARGETARCH
COPY --from=rclone-src / /src/rclone
# A static binary, as in rclone's own image. rclone's release builds set
# fs.Version to the tag; without it rclone reports itself as <tag>-DEV.
# The golang image sets GOTOOLCHAIN=local, so a go.mod that needs a newer Go
# fails here rather than downloading one.
RUN mkdir -p /opt/rclone/bin \
 && CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -C /src/rclone -trimpath \
        -ldflags "-s -X github.com/rclone/rclone/fs.Version=${RCLONE}" \
        -o /opt/rclone/bin/rclone

FROM runtime-base AS rclone
COPY --from=build /opt/rclone /opt/rclone
ENV PATH=/opt/rclone/bin:${PATH}
