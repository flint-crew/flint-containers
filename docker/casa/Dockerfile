# CASA tasks from NRAO's casatools/casatasks wheels, with a small `casa`
# command that runs `casa -c <code>` the way flint calls it.
# NRAO publishes Linux wheels for x86_64 only, so this image is amd64-only.
# Build with: docker buildx bake casa

FROM build-base AS build
ARG CASA
ARG CASACONFIG
# Use the manylinux_2_28 casatools wheel: it bundles its own OpenSSL. The
# manylinux_2_34 wheel needs OpenSSL 3.2 from the system and Ubuntu 24.04 has 3.0.
# casatasks imports six without declaring it as a dependency.
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip download --no-cache-dir --no-deps --only-binary=:all: \
        --platform manylinux_2_28_x86_64 --python-version 3.12 \
        --dest /tmp/wheels "casatools==${CASA}" \
 && /opt/venv/bin/pip install --no-cache-dir \
        /tmp/wheels/casatools-*.whl "casatasks==${CASA}" "casaconfig==${CASACONFIG}" six \
 && rm -rf /tmp/wheels

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
