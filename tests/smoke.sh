#!/usr/bin/env bash
# Quick checks that an image works the way flint runs it.
#
# Usage: tests/smoke.sh <name> <image>
#   e.g. tests/smoke.sh wsclean ghcr.io/flint-crew/wsclean:dev
#
# Containers run like Apptainer runs them for flint: read-only image, a
# non-root user, and a HOME that does not exist.
set -euo pipefail

name=${1:?usage: smoke.sh <name> <image>}
image=${2:?usage: smoke.sh <name> <image>}

run() {
    docker run --rm --read-only --tmpfs /tmp -w /tmp \
        --user 54321:54321 -e HOME=/nonexistent \
        "$image" "$@"
}

# Require that a command's output contains a pattern. Exit codes are ignored
# because several of these programs exit non-zero after printing usage.
expect_output() {
    local pattern=$1
    shift
    local out
    out=$(run "$@" 2>&1 || true)
    if ! grep -q -- "$pattern" <<<"$out"; then
        echo "FAIL: '$*' did not print '$pattern'. Output was:"
        head -n 20 <<<"$out"
        exit 1
    fi
    echo "ok: '$*' prints '$pattern'"
}

# major.minor of the version an image was built from, read from its labels
# (e.g. io.github.flint-crew.wsclean=v3.7 gives 3.7). Images built from a
# commit rather than a release give "[0-9]", which matches any version number.
label_version() {
    local value
    value=$(docker image inspect --format "{{ index .Config.Labels \"io.github.flint-crew.$1\" }}" "$image")
    if [[ "$value" =~ ^v?([0-9]+\.[0-9]+) ]]; then
        echo "${BASH_REMATCH[1]//./\\.}"
    else
        echo "[0-9]"
    fi
}

check() {
    local description=$1
    shift
    if run "$@" >/dev/null 2>&1; then
        echo "ok: $description"
    else
        echo "FAIL: $description"
        exit 1
    fi
}

# Checks for the images built here (askapsoft is CSIRO's image).
if [ "$name" != askapsoft ]; then
    check "measures data present" test -s /opt/measures/SOURCE
    check "no compilers shipped" sh -c '! command -v cc && ! command -v c++ && ! command -v cmake'
fi

missing=$(run sh -c '
    for f in /opt/*/bin/* /opt/*/lib/*.so* /opt/venv/lib/python3*/site-packages/casacore/*.so; do
        [ -f "$f" ] || continue
        ldd "$f" 2>/dev/null | grep "not found" | sed "s|^|$f: |"
    done
    true')
if [ -n "$missing" ]; then
    echo "FAIL: missing shared libraries:"
    echo "$missing"
    exit 1
fi
echo "ok: no missing shared libraries"

case "$name" in
    calibrate)
        expect_output "Usage: calibrate" calibrate
        expect_output "Usage: applysolutions" applysolutions
        expect_output "Usage: addmodel" addmodel
        ;;
    wsclean)
        expect_output "WSClean version $(label_version wsclean)" wsclean --version
        expect_output "IDG is available" wsclean --version
        expect_output "EveryBeam is available" wsclean --version
        ;;
    aoflagger)
        expect_output "AOFlagger $(label_version aoflagger)" aoflagger --version
        ;;
    potato)
        expect_output "usage: hot_potato" hot_potato -h
        expect_output "usage: peel_configuration.py" peel_configuration.py -h
        expect_output "WSClean version" wsclean --version
        check "python-casacore imports" python -c "import casacore.tables"
        ;;
    aegean)
        expect_output "$(label_version aegean)" aegean --version
        expect_output "usage: BANE" BANE --help
        ;;
    casa)
        expect_output "$(label_version casatasks)" casa -c "import casatasks; print(casatasks.version_string())"
        expect_output "True True True True" casa --nologger -c \
            "print(callable(mstransform), callable(cvel), callable(gaincal), callable(applycal))"
        ;;
    askapsoft)
        check "linmos on PATH" sh -c 'command -v linmos'
        ;;
    rclone)
        expect_output "$(label_version rclone)" rclone version
        expect_output "go/linking: static" rclone version
        check "CA certificates for HTTPS" test -s /etc/ssl/certs/ca-certificates.crt
        # The copy flint runs, to a folder rather than an object store
        check "rclone copy --checksum --immutable" sh -c '
            mkdir src && echo flint > src/a && echo a > list \
            && rclone copy --files-from-raw list --checksum --immutable src dst \
            && cmp src/a dst/a'
        ;;
    *)
        echo "No checks defined for '$name'" >&2
        exit 1
        ;;
esac

echo "All smoke tests passed for $name ($image)"
