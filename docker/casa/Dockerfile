# CASA tasks from NRAO's casatools/casatasks wheels, with a small `casa`
# command that runs `casa -c <code>` the way flint calls it.
# NRAO publishes Linux wheels for x86_64 only, so this image is amd64-only.
# Build with: docker buildx bake casa

FROM build-base AS build
ARG CASA
ARG CASACONFIG
COPY --from=uv /uv /usr/local/bin/uv
# uv must use Ubuntu's Python, which the published image also has, and compile
# the bytecode: Apptainer images are read-only, so it can't be written later.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
# Use the manylinux_2_28 casatools wheel: it bundles its own OpenSSL. The
# manylinux_2_34 wheel needs OpenSSL 3.2 from the system and Ubuntu 24.04 has 3.0.
# --python-platform limits every package to wheels that run on glibc 2.28.
# casatasks imports six without declaring it as a dependency.
RUN uv venv --python /usr/bin/python3 /opt/venv \
 && uv pip install --python /opt/venv/bin/python \
        --python-platform x86_64-manylinux_2_28 --only-binary casatools \
        "casatools==${CASA}" "casatasks==${CASA}" "casaconfig==${CASACONFIG}" six

# CASA's data package. NRAO serves dated versions; the installed version is
# recorded in /opt/casa-data/readme.txt. Changing CASA_DATA_REFRESH fetches again.
FROM build AS casa-data
ARG CASA_DATA_REFRESH
RUN /opt/venv/bin/python -c "import casaconfig; casaconfig.pull_data('/opt/casa-data')" \
 && cat /opt/casa-data/readme.txt

FROM runtime-base AS casa
COPY --from=build /opt/venv /opt/venv
COPY --from=casa-data /opt/casa-data /opt/casa-data
COPY casasiteconfig.py /opt/casa/casasiteconfig.py
COPY --chmod=755 casa /opt/casa/bin/casa
ENV PATH=/opt/casa/bin:/opt/venv/bin:${PATH} \
    CASASITECONFIG=/opt/casa/casasiteconfig.py
