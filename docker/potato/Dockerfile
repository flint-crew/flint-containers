# potato, on top of the wsclean image it calls.
# python-casacore is built against the image's casacore rather than using the
# PyPI wheel, which bundles its own copy.
# Build with: docker buildx bake potato

FROM casacore-build AS build
ARG MARCH
ARG BUILD_NUMPY
ARG PYTHON_CASACORE
COPY --from=python-casacore-src / /src/python-casacore
COPY --from=potato-src / /src/potato
# The git context has no .git directory, so setuptools-scm needs the version;
# a commit is given as 0+g<commit>.
RUN version="${PYTHON_CASACORE#v}" \
 && case "${version}" in ""|*[!0-9.]*) version="0+g${PYTHON_CASACORE}" ;; esac \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir "numpy==${BUILD_NUMPY}" \
 && SETUPTOOLS_SCM_PRETEND_VERSION="${version}" \
    /opt/venv/bin/pip install --no-cache-dir \
        --config-settings=cmake.define.CASACORE_ROOT_DIR=/opt/casacore \
        --config-settings=cmake.define.BUILD_TESTING=OFF \
        --config-settings=cmake.define.CMAKE_CXX_FLAGS="-march=${MARCH} -mtune=generic" \
        /src/python-casacore \
 && /opt/venv/bin/pip install --no-cache-dir /src/potato

FROM wsclean AS potato
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
