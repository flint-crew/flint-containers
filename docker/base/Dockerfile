# Shared base images for every flint container.
#
# Stages (each is a bake target in docker-bake.hcl):
#   build-base      compilers and -dev packages. Build-only, never published.
#   runtime-base    runtime shared libraries, python3 and casacore measures data.
#                   Every published image starts from this.
#   casacore-build  casacore compiled into /opt/casacore (build-only).
#   casacore        runtime-base + /opt/casacore. Base for all C++ tools.
#
# Build with bake rather than calling this file directly:
#   docker buildx bake casacore

ARG UBUNTU_IMAGE

# ---------------------------------------------------------------------------
FROM ${UBUNTU_IMAGE} AS os
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

# ---------------------------------------------------------------------------
FROM os AS build-base
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        bison \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        flex \
        gfortran \
        git \
        ninja-build \
        pkg-config \
        python3 \
        python3-venv \
        libboost-dev \
        libboost-thread-dev \
        libcfitsio-dev \
        libfftw3-dev \
        libgsl-dev \
        libhdf5-dev \
        liblapack-dev \
        libopenblas-dev \
        wcslib-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# casacore measures tables (ephemerides, geodetic, IERS). Downloaded at build
# time because ASTRON only serves the latest snapshot; the URL, checksum and
# download time are recorded in /opt/measures/SOURCE.
# Change MEASURES_REFRESH (CI uses the year-month) to force a fresh download.
FROM build-base AS measures
ARG MEASURES_URL
ARG MEASURES_REFRESH
RUN test -n "${MEASURES_URL}" \
 && mkdir -p /opt/measures \
 && curl -fsSL --retry 5 --retry-all-errors -o /tmp/measures.ztar "${MEASURES_URL}" \
 && tar -xf /tmp/measures.ztar -C /opt/measures \
 && test -d /opt/measures/ephemerides \
 && test -d /opt/measures/geodetic \
 && { echo "url: ${MEASURES_URL}"; \
      echo "sha256: $(sha256sum /tmp/measures.ztar | cut -d' ' -f1)"; \
      echo "downloaded: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; \
      echo "refresh-key: ${MEASURES_REFRESH}"; } > /opt/measures/SOURCE \
 && rm /tmp/measures.ztar

# ---------------------------------------------------------------------------
# Runtime libraries only. This is the union of what the published images
# need, so they all share this layer. Add a library here (not in an app
# image) when a new tool needs one.
FROM os AS runtime-base
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        libboost-thread1.83.0 \
        libcfitsio10t64 \
        libfftw3-double3 \
        libfftw3-single3 \
        libgfortran5 \
        libgomp1 \
        libgsl27 \
        libgslcblas0 \
        libhdf5-103-1t64 \
        libopenblas0-pthread \
        libwcs8 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
COPY --from=measures /opt/measures /opt/measures

# ---------------------------------------------------------------------------
FROM build-base AS casacore-build
ARG MARCH
# casacore source is a bake named context (a pinned git ref); see docker-bake.hcl
COPY --from=casacore-src / /src/casacore
# Never build without an explicit CPU target: an empty MARCH would silently
# produce a build tuned for whichever machine CI happened to run on.
RUN test -n "${MARCH}" || { echo "MARCH must be set" >&2; exit 1; }
RUN cmake -S /src/casacore -B /tmp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/casacore \
        -DCMAKE_C_FLAGS="-march=${MARCH} -mtune=generic" \
        -DCMAKE_CXX_FLAGS="-march=${MARCH} -mtune=generic" \
        -DCMAKE_Fortran_FLAGS="-march=${MARCH} -mtune=generic" \
        -DBUILD_PYTHON=OFF \
        -DBUILD_PYTHON3=OFF \
        -DBUILD_TESTING=OFF \
        -DBUILD_DYSCO=ON \
        -DUSE_OPENMP=ON \
        -DUSE_THREADS=ON \
        -DUSE_HDF5=ON \
        -DUSE_READLINE=OFF \
        -DDATA_DIR=/opt/measures \
 && cmake --build /tmp/build \
 && cmake --install /tmp/build --strip \
 && rm -rf /tmp/build \
 && echo /opt/casacore/lib > /etc/ld.so.conf.d/casacore.conf \
 && ldconfig
ENV PATH=/opt/casacore/bin:${PATH}

# ---------------------------------------------------------------------------
FROM runtime-base AS casacore
COPY --from=casacore-build /opt/casacore /opt/casacore
RUN echo /opt/casacore/lib > /etc/ld.so.conf.d/casacore.conf && ldconfig
ENV PATH=/opt/casacore/bin:${PATH}
