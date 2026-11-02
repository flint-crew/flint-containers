# aoflagger, without the GUI tools, installed in /opt/aoflagger.
# Build with: docker buildx bake aoflagger

FROM casacore-build AS build
ARG MARCH
COPY --from=aoflagger-src / /src/aoflagger
# With TARGET_CPU unset aoflagger builds for -march=native.
RUN test -n "${MARCH}" || { echo "MARCH must be set" >&2; exit 1; }
RUN cmake -S /src/aoflagger -B /tmp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/aoflagger \
        -DCMAKE_INSTALL_RPATH="/opt/aoflagger/lib;/opt/casacore/lib" \
        -DPORTABLE=OFF -DTARGET_CPU="${MARCH}" \
        -DGIT_SUBMODULE=OFF \
        -DCASACORE_ROOT_DIR=/opt/casacore \
        -DENABLE_GUI=OFF \
 && cmake --build /tmp/build \
 && cmake --install /tmp/build --strip

FROM casacore AS aoflagger
COPY --from=build /opt/aoflagger /opt/aoflagger
RUN echo /opt/aoflagger/lib > /etc/ld.so.conf.d/aoflagger.conf && ldconfig
ENV PATH=/opt/aoflagger/bin:${PATH}
