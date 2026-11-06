# Shared stages used by every image. Build through docker-bake.hcl, e.g.
#   docker buildx bake casacore
#
#   build-base      compilers and -dev packages (never published)
#   measures        casacore measures data, downloaded at build time
#   runtime-base    runtime libraries, python3 and the measures data
#   casacore-build  build-base + casacore in /opt/casacore (never published)
#   casacore        runtime-base + /opt/casacore

ARG UBUNTU_IMAGE

FROM ${UBUNTU_IMAGE} AS os
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

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
        python3-dev \
        python3-venv \
        pybind11-dev \
        libboost-dev \
        libboost-filesystem-dev \
        libboost-program-options-dev \
        libboost-python-dev \
        libboost-thread-dev \
        libcfitsio-dev \
        libdeflate-dev \
        libfftw3-dev \
        libgsl-dev \
        libhdf5-dev \
        liblapack-dev \
        liblua5.4-dev \
        libopenblas-dev \
        libpng-dev \
        wcslib-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ASTRON only serves the latest snapshot, so record what was downloaded.
# Changing MEASURES_REFRESH forces a new download.
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

# Runtime libraries for every image. Add new ones here rather than in an app
# image so all images keep sharing this layer.
FROM os AS runtime-base
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        libboost-filesystem1.83.0 \
        libboost-program-options1.83.0 \
        libboost-python1.83.0 \
        libboost-thread1.83.0 \
        libcfitsio10t64 \
        libdeflate0 \
        libfftw3-double3 \
        libfftw3-single3 \
        libgfortran5 \
        libgomp1 \
        libgsl27 \
        libgslcblas0 \
        libhdf5-103-1t64 \
        libhdf5-cpp-103-1t64 \
        liblua5.4-0 \
        libopenblas0-pthread \
        libpng16-16t64 \
        libpython3.12t64 \
        libwcs8 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
COPY --from=measures /opt/measures /opt/measures

FROM build-base AS casacore-build
ARG MARCH
ARG BUILD_NUMPY
# An empty MARCH would let projects fall back to -march=native.
RUN test -n "${MARCH}" || { echo "MARCH must be set" >&2; exit 1; }
# casacore's Python converters (needed by python-casacore) are compiled against
# NumPy 2 headers so they work with the NumPy 2 installed in the Python images.
RUN python3 -m venv /opt/build-venv \
 && /opt/build-venv/bin/pip install --no-cache-dir "numpy==${BUILD_NUMPY}"
# Copied after the steps above so that changing CASACORE doesn't redo them.
COPY --from=casacore-src / /src/casacore
RUN cmake -S /src/casacore -B /tmp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/casacore \
        -DCMAKE_C_FLAGS="-march=${MARCH} -mtune=generic" \
        -DCMAKE_CXX_FLAGS="-march=${MARCH} -mtune=generic" \
        -DCMAKE_Fortran_FLAGS="-march=${MARCH} -mtune=generic" \
        -DBUILD_PYTHON=OFF \
        -DBUILD_PYTHON3=ON \
        -DPython3_EXECUTABLE=/opt/build-venv/bin/python \
        -DBUILD_TESTING=OFF \
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

FROM runtime-base AS casacore
COPY --from=casacore-build /opt/casacore /opt/casacore
RUN echo /opt/casacore/lib > /etc/ld.so.conf.d/casacore.conf && ldconfig
ENV PATH=/opt/casacore/bin:${PATH}
