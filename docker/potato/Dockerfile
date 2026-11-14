# potato, on top of the wsclean image it calls.
# python-casacore is built against the image's casacore rather than using the
# PyPI wheel, which bundles its own copy.
# Build with: docker buildx bake potato

FROM casacore-build AS build
ARG MARCH
ARG BUILD_NUMPY
ARG PYTHON_CASACORE
COPY --from=uv /uv /usr/local/bin/uv
# uv must use Ubuntu's Python, which the published image also has, and compile
# the bytecode: Apptainer images are read-only, so it can't be written later.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
COPY --from=python-casacore-src / /src/python-casacore
# The git context has no .git directory, so setuptools-scm needs the version;
# a commit is given as 0+g<commit>.
RUN version="${PYTHON_CASACORE#v}" \
 && case "${version}" in ""|*[!0-9.]*) version="0+g${PYTHON_CASACORE}" ;; esac \
 && uv venv --python /usr/bin/python3 /opt/venv \
 && uv pip install --python /opt/venv/bin/python "numpy==${BUILD_NUMPY}" \
 && SETUPTOOLS_SCM_PRETEND_VERSION="${version}" \
    uv pip install --python /opt/venv/bin/python \
        --config-settings=cmake.define.CASACORE_ROOT_DIR=/opt/casacore \
        --config-settings=cmake.define.BUILD_TESTING=OFF \
        --config-settings=cmake.define.CMAKE_CXX_FLAGS="-march=${MARCH} -mtune=generic" \
        /src/python-casacore
# A separate step, so that changing POTATO doesn't rebuild python-casacore.
COPY --from=potato-src / /src/potato
RUN uv pip install --python /opt/venv/bin/python /src/potato

FROM wsclean AS potato
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
