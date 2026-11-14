# AegeanTools (aegean, BANE and friends) in /opt/venv.
# Build with: docker buildx bake aegean

FROM build-base AS build
COPY --from=uv /uv /usr/local/bin/uv
# uv must use Ubuntu's Python, which the published image also has, and compile
# the bytecode: Apptainer images are read-only, so it can't be written later.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
COPY --from=aegean-src / /src/aegean
RUN uv venv --python /usr/bin/python3 /opt/venv \
 && uv pip install --python /opt/venv/bin/python /src/aegean

FROM runtime-base AS aegean
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
