# docker-bake.hcl: the single place that says what goes into each image.
#
# Common commands (run from the repository root):
#   docker buildx bake --print        show what would be built: versions, tags, args
#   docker buildx bake calibrate      build one image (and the bases it needs)
#   docker buildx bake                build every published image
#   docker buildx bake test           run the build-time test suites
#
# To bump a package: change its version below and open a PR. CI rebuilds the
# affected images and runs the smoke and flint compatibility tests.
#
# Every variable can be overridden from the environment, e.g.
#   CASACORE=v3.8.2 docker buildx bake casacore
#
# Docs: https://docs.docker.com/build/bake/

# ===========================================================================
# Pinned versions
# ===========================================================================

# Base OS for every image. Pinned by digest so a rebuild is the same OS.
# https://hub.docker.com/_/ubuntu
variable "UBUNTU_IMAGE" {
  default = "ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852"
}

# https://github.com/casacore/casacore
variable "CASACORE" { default = "v3.7.1" }

# https://github.com/flint-crew/calibrate (no release tags yet, so pin a commit)
variable "CALIBRATE" { default = "c1fb4c6d430d6cda1e1c76f363e5f4f449878c24" }

# casacore measures data. ASTRON only serves the latest snapshot, so this is
# downloaded at build time and recorded in /opt/measures/SOURCE in the image.
# Change MEASURES_REFRESH to force a fresh download (CI uses the year-month).
variable "MEASURES_URL" { default = "https://www.astron.nl/iers/WSRT_Measures.ztar" }
variable "MEASURES_REFRESH" { default = "" }

# ===========================================================================
# Build settings (normally set by CI)
# ===========================================================================

# Compiler CPU target (-march / TARGET_CPU) for compiled code. Never "native":
# that tunes the binaries for whichever machine did the build.
variable "MARCH" { default = "x86-64-v2" }

variable "PLATFORMS" { default = "linux/amd64" }

variable "REGISTRY" { default = "ghcr.io/flint-crew" }

# Comma-separated tags to apply to every published image, e.g. "pr-12" or "v2.0.0,latest"
variable "TAGS" { default = "dev" }

# Registry build cache. CI sets CACHE_REF; leave empty locally.
variable "CACHE_REF" { default = "" }
variable "CACHE_PUSH" { default = false }

# Recorded in image labels; CI sets this to the commit being built.
variable "GITHUB_SHA" { default = "" }

# ===========================================================================
# Helpers
# ===========================================================================

function "tags" {
  params = [name]
  result = [for t in split(",", TAGS) : "${REGISTRY}/${name}:${trimspace(t)}"]
}

function "cache_from" {
  params = [name]
  result = CACHE_REF == "" ? [] : ["type=registry,ref=${CACHE_REF}:${name}"]
}

function "cache_to" {
  params = [name]
  result = CACHE_REF != "" && CACHE_PUSH ? ["type=registry,ref=${CACHE_REF}:${name},mode=max,ignore-error=true"] : []
}

function "git" {
  params = [url, ref]
  result = "${url}#${ref}"
}

# ===========================================================================
# Groups
# ===========================================================================

# Everything that gets published
group "default" {
  targets = ["runtime-base", "casacore", "calibrate"]
}

# Build-time test suites (nothing is published)
group "test" {
  targets = ["calibrate-test"]
}

# ===========================================================================
# Targets
# ===========================================================================

# Settings shared by every target
target "_common" {
  platforms = split(",", PLATFORMS)
  args = {
    UBUNTU_IMAGE     = UBUNTU_IMAGE
    MARCH            = MARCH
    MEASURES_URL     = MEASURES_URL
    MEASURES_REFRESH = MEASURES_REFRESH
  }
  labels = {
    "org.opencontainers.image.source"   = "https://github.com/flint-crew/flint-containers"
    "org.opencontainers.image.revision" = GITHUB_SHA
    "io.github.flint-crew.ubuntu.image" = UBUNTU_IMAGE
  }
}

# Base Dockerfile and the casacore source it needs
target "_base" {
  inherits   = ["_common"]
  context    = "docker/base"
  dockerfile = "Dockerfile"
  contexts = {
    casacore-src = git("https://github.com/casacore/casacore.git", CASACORE)
  }
}

# --- shared bases ----------------------------------------------------------

target "runtime-base" {
  inherits    = ["_base"]
  target      = "runtime-base"
  tags        = tags("runtime-base")
  cache-from  = cache_from("runtime-base")
  cache-to    = cache_to("runtime-base")
  description = "Runtime libraries, python3 and casacore measures data shared by every flint image"
}

# Build-only: compilers + casacore. Used as a named context by app images.
target "casacore-build" {
  inherits   = ["_base"]
  target     = "casacore-build"
  cache-from = cache_from("casacore-build")
  cache-to   = cache_to("casacore-build")
}

target "casacore" {
  inherits   = ["_base"]
  target     = "casacore"
  tags       = tags("casacore")
  cache-from = cache_from("casacore")
  cache-to   = cache_to("casacore")
  labels = {
    "io.github.flint-crew.casacore.version" = CASACORE
    "io.github.flint-crew.march"            = MARCH
  }
  description = "casacore ${CASACORE}, the base for flint's C++ tools"
}

# --- calibrate ---------------------------------------------------------------

target "_calibrate" {
  inherits   = ["_common"]
  context    = "docker/calibrate"
  dockerfile = "Dockerfile"
  contexts = {
    casacore-build = "target:casacore-build"
    casacore       = "target:casacore"
    calibrate-src  = git("https://github.com/flint-crew/calibrate.git", CALIBRATE)
  }
}

target "calibrate" {
  inherits   = ["_calibrate"]
  target     = "calibrate"
  tags       = tags("calibrate")
  cache-from = cache_from("calibrate")
  cache-to   = cache_to("calibrate")
  labels = {
    "io.github.flint-crew.casacore.version"  = CASACORE
    "io.github.flint-crew.calibrate.version" = CALIBRATE
    "io.github.flint-crew.march"             = MARCH
  }
  description = "AO calibrate, applysolutions and addmodel"
}

target "calibrate-test" {
  inherits = ["_calibrate"]
  target   = "test"
  output   = ["type=cacheonly"]
}
