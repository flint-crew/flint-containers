# calibrate, applysolutions and addmodel.
# Build with: docker buildx bake calibrate
# From a local checkout: docker buildx bake calibrate --set calibrate.contexts.calibrate-src=../calibrate

FROM casacore-build AS build
ARG MARCH
COPY --from=calibrate-src / /src/calibrate
WORKDIR /src/calibrate
# Upstream hard-codes -march=native; remove it so MARCH decides the CPU target.
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

# Runs calibrate's own test suite against the installed programs.
FROM build AS test
COPY --from=casacore /opt/measures /opt/measures
RUN python3 -m venv /tmp/venv \
 && /tmp/venv/bin/pip install --no-cache-dir "python-casacore>=3.6" "numpy>=2" pytest \
 && CALIBRATE_BIN_DIR=/opt/calibrate/bin /tmp/venv/bin/python -m pytest -q /src/calibrate/tests

FROM casacore AS calibrate
COPY --from=build /opt/calibrate /opt/calibrate
ENV PATH=/opt/calibrate/bin:${PATH}
