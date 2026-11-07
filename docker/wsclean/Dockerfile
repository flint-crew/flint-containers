# wsclean with IDG and EveryBeam, all installed in /opt/wsclean.
# Build with: docker buildx bake wsclean

FROM casacore-build AS deps
ARG MARCH
ENV CMAKE_PREFIX_PATH=/opt/casacore:/opt/wsclean
# EveryBeam's CMake requires wget, although nothing is downloaded with
# DOWNLOAD_LOBES and BUILD_TESTING off.
RUN apt-get update \
 && apt-get install -y --no-install-recommends wget \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
# All three use PORTABLE/TARGET_CPU; with TARGET_CPU unset they build for -march=native.
RUN test -n "${MARCH}" || { echo "MARCH must be set" >&2; exit 1; }

# IDG and EveryBeam are separate stages so that they build at the same time,
# and each is rebuilt only when its own version (or casacore) changes. Changing
# WSCLEAN rebuilds only wsclean.
FROM deps AS idg
COPY --from=idg-src / /src/idg
RUN cmake -S /src/idg -B /tmp/idg -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/wsclean \
        -DPORTABLE=OFF -DTARGET_CPU="${MARCH}" \
        -DGIT_SUBMODULE=OFF \
        -DBUILD_LIB_CPU=ON \
        -DBUILD_LIB_CUDA=OFF \
        -DBUILD_TESTING=OFF \
 && cmake --build /tmp/idg \
 && cmake --install /tmp/idg --strip \
 && rm -rf /tmp/idg

FROM deps AS everybeam
COPY --from=everybeam-src / /src/everybeam
RUN cmake -S /src/everybeam -B /tmp/everybeam -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/wsclean \
        -DPORTABLE=OFF -DTARGET_CPU="${MARCH}" \
        -DGIT_SUBMODULE=OFF \
        -DCASACORE_ROOT_DIR=/opt/casacore \
        -DBUILD_WITH_PYTHON=OFF \
        -DBUILD_TESTING=OFF \
 && cmake --build /tmp/everybeam \
 && cmake --install /tmp/everybeam --strip \
 && rm -rf /tmp/everybeam

FROM deps AS build
COPY --from=idg /opt/wsclean /opt/wsclean
COPY --from=everybeam /opt/wsclean /opt/wsclean
COPY --from=wsclean-src / /src/wsclean
RUN cmake -S /src/wsclean -B /tmp/wsclean -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/wsclean \
        -DCMAKE_INSTALL_RPATH="/opt/wsclean/lib;/opt/casacore/lib" \
        -DPORTABLE=OFF -DTARGET_CPU="${MARCH}" \
        -DGIT_SUBMODULE=OFF \
        -DCASACORE_ROOT_DIR=/opt/casacore \
        -DBUILD_TESTING=OFF \
 && cmake --build /tmp/wsclean \
 && cmake --install /tmp/wsclean --strip \
 && rm -rf /tmp/wsclean

FROM casacore AS wsclean
COPY --from=build /opt/wsclean /opt/wsclean
RUN echo /opt/wsclean/lib > /etc/ld.so.conf.d/wsclean.conf && ldconfig
# wsclean refuses to run unless OpenBLAS is limited to one thread.
ENV PATH=/opt/wsclean/bin:${PATH} \
    OPENBLAS_NUM_THREADS=1
