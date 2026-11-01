# calibrate, applysolutions and addmodel (AO calibrate, modified for ASKAP).
#
# Named contexts supplied by docker-bake.hcl:
#   casacore-build  build stage with casacore in /opt/casacore
#   casacore        runtime image with casacore
#   calibrate-src   calibrate source at the pinned commit (or a local
#                   checkout, e.g. --set calibrate.contexts.calibrate-src=./calibrate)
#
#   docker buildx bake calibrate

FROM casacore-build AS build
ARG MARCH
COPY --from=calibrate-src / /src/calibrate
WORKDIR /src/calibrate
# Upstream hard-codes -march=native, which would tune the binaries for the CI
# runner. Strip it so the CPU target comes only from MARCH, and fail loudly if
# upstream changes the line and the strip stops working.
RUN test -n "${MARCH}" || { echo "MARCH must be set" >&2; exit 1; } \
 && sed -i 's/-march=native//g' CMakeLists.txt \
 && ! grep -q 'march=native' CMakeLists.txt
RUN cmake -S . -B /tmp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/calibrate \
        -DCMAKE_CXX_FLAGS="-march=${MARCH} -mtune=generic" \
        -DCASACORE_ROOT_DIR=/opt/casacore \
        -DCMAKE_INSTALL_RPATH=/opt/casacore/lib \
 && cmake --build /tmp/build \
 && cmake --install /tmp/build --strip

# ---------------------------------------------------------------------------
# Upstream's own test suite (the same command lines flint builds), run against
# the binaries installed above. Not published; CI builds this stage to test.
FROM build AS test
COPY --from=casacore /opt/measures /opt/measures
RUN python3 -m venv /tmp/venv \
 && /tmp/venv/bin/pip install --no-cache-dir "python-casacore>=3.6" "numpy>=2" pytest \
 && CALIBRATE_BIN_DIR=/opt/calibrate/bin /tmp/venv/bin/python -m pytest -q /src/calibrate/tests

# ---------------------------------------------------------------------------
FROM casacore AS calibrate
COPY --from=build /opt/calibrate /opt/calibrate
ENV PATH=/opt/calibrate/bin:${PATH}
