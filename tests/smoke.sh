#!/usr/bin/env bash
# Quick checks that a built image works the way flint runs it.
#
# Usage: tests/smoke.sh <name> <image-ref>
#   e.g. tests/smoke.sh calibrate ghcr.io/flint-crew/calibrate:pr-12
#
# Containers are run the way Apptainer runs them for flint: read-only image,
# an arbitrary non-root user, and a HOME that isn't writable, so nothing
# can depend on writing into the image or on $HOME.
set -euo pipefail

name=${1:?usage: smoke.sh <name> <image-ref>}
image=${2:?usage: smoke.sh <name> <image-ref>}

run() {
    docker run --rm --read-only --tmpfs /tmp \
        --user 54321:54321 -e HOME=/nonexistent \
        "$image" "$@"
}

# Run a command and require that its output contains a pattern.
# Exit codes are ignored: these programs exit non-zero when printing usage.
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

check() {
    local description=$1
    shift
    if run "$@"; then
        echo "ok: $description"
    else
        echo "FAIL: $description"
        exit 1
    fi
}

# --- checks for every image ---------------------------------------------------

check "measures data present" test -s /opt/measures/SOURCE
check "no compilers shipped" sh -c '! command -v cc && ! command -v c++ && ! command -v cmake'

missing=$(run sh -c '
    for f in /opt/*/bin/* /opt/*/lib/*.so*; do
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

# --- per-image checks ---------------------------------------------------------

case "$name" in
    runtime-base)
        expect_output "Python 3" python3 --version
        ;;
    casacore)
        check "casacore libraries installed" sh -c 'ls /opt/casacore/lib/libcasa_ms.so* >/dev/null'
        ;;
    calibrate)
        expect_output "Usage: calibrate" calibrate
        expect_output "Usage: applysolutions" applysolutions
        expect_output "Usage: addmodel" addmodel
        ;;
    *)
        echo "No checks defined for '$name'" >&2
        exit 1
        ;;
esac

echo "All smoke tests passed for $name ($image)"
