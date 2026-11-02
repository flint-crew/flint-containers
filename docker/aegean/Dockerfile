# AegeanTools (aegean, BANE and friends) in /opt/venv.
# Build with: docker buildx bake aegean

FROM build-base AS build
COPY --from=aegean-src / /src/aegean
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir /src/aegean

FROM runtime-base AS aegean
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
