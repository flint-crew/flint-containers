# calibrate, applysolutions and addmodel.
# Build with: docker buildx bake calibrate
# From a local checkout: docker buildx bake calibrate --set calibrate.contexts.calibrate-src=../calibrate

FROM casacore-build AS build
ARG MARCH
COPY --from=calibrate-src / /src/calibrate
WORKDIR /src/calibrate
# TARGET_CPU sets -march. Commits before flint-crew/calibrate#9 ignore it
# and hard-code -march=native, so refuse to build them.
RUN test -n "${MARCH}" || { echo "MARCH must be set" >&2; exit 1; }
RUN if grep -q 'march=native' CMakeLists.txt; then \
        echo "This calibrate commit hard-codes -march=native; use one with TARGET_CPU" >&2; exit 1; \
    fi
RUN cmake -S . -B /tmp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/calibrate \
        -DTARGET_CPU="${MARCH}" \
        -DCMAKE_CXX_FLAGS="-mtune=generic" \
        -DCASACORE_ROOT_DIR=/opt/casacore \
        -DCMAKE_INSTALL_RPATH=/opt/casacore/lib \
 && cmake --build /tmp/build \
 && cmake --install /tmp/build --strip

# Runs calibrate's own test suite against the installed programs.
# python-casacore is built from source against the image's casacore, as in the
# potato image, so PYTHON_CASACORE can be a commit as well as a release.
FROM build AS test
ARG BUILD_NUMPY
ARG PYTHON_CASACORE
COPY --from=python-casacore-src / /src/python-casacore
# The git context has no .git directory, so setuptools-scm needs the version;
# a commit is given as 0+g<commit>.
RUN version="${PYTHON_CASACORE#v}" \
 && case "${version}" in ""|*[!0-9.]*) version="0+g${PYTHON_CASACORE}" ;; esac \
 && python3 -m venv /tmp/venv \
 && /tmp/venv/bin/pip install --no-cache-dir "numpy==${BUILD_NUMPY}" pytest \
 && SETUPTOOLS_SCM_PRETEND_VERSION="${version}" \
    /tmp/venv/bin/pip install --no-cache-dir \
        --config-settings=cmake.define.CASACORE_ROOT_DIR=/opt/casacore \
        --config-settings=cmake.define.BUILD_TESTING=OFF \
        /src/python-casacore
# The measures data changes whenever it is downloaded again. Copied after the
# python-casacore build so that only the tests run again, not the build.
COPY --from=casacore /opt/measures /opt/measures
RUN CALIBRATE_BIN_DIR=/opt/calibrate/bin /tmp/venv/bin/python -m pytest -q /src/calibrate/tests

FROM casacore AS calibrate
COPY --from=build /opt/calibrate /opt/calibrate
ENV PATH=/opt/calibrate/bin:${PATH}
