# Versions and build targets for every image.
#
#   docker buildx bake --print      show what would be built
#   docker buildx bake wsclean      build one image and the stages it needs
#   docker buildx bake              build all images
#   docker buildx bake test         run calibrate's own test suite
#
# Any variable can be overridden from the environment, for example
#   MARCH=x86-64-v3 TAG_SUFFIX=-x86-64-v3 docker buildx bake compiled
#
# https://docs.docker.com/build/bake/

# --- Versions -----------------------------------------------------------------

# https://hub.docker.com/_/ubuntu
variable "UBUNTU_IMAGE" {
  default = "ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852"
}

# https://github.com/casacore/casacore
# 3.8 is not used yet; see "casacore version" in README.md.
variable "CASACORE" { default = "v3.7.1" }

# https://github.com/flint-crew/calibrate (no tags, so a commit)
variable "CALIBRATE" { default = "3e5e84a8606b44165e9db382611c6c7fbf397c9b" }

# https://gitlab.com/aroffringa/wsclean
variable "WSCLEAN" { default = "v3.7" }

# https://git.astron.nl/RD/idg (wsclean 3.7 needs >= 0.8.1)
variable "IDG" { default = "1.2.0" }

# https://git.astron.nl/RD/EveryBeam (wsclean 3.7 needs 0.7.4 to 0.8.x)
variable "EVERYBEAM" { default = "v0.8.5" }

# https://gitlab.com/aroffringa/aoflagger
variable "AOFLAGGER" { default = "v3.5.0" }

# https://gitlab.com/Sunmish/potato (no tags, so a commit)
variable "POTATO" { default = "4bb494010ef690318246dc5673127f4f87a7fa82" }

# https://github.com/casacore/python-casacore (used by potato)
variable "PYTHON_CASACORE" { default = "v3.7.1" }

# https://github.com/PaulHancock/Aegean
variable "AEGEAN" { default = "v2.3.4" }

# https://pypi.org/project/casatasks/ (NRAO only publishes wheels)
variable "CASA" { default = "6.7.6.14" }
variable "CASACONFIG" { default = "1.5.2" }

# ASKAPsoft source is not publicly available, so this is CSIRO's image.
# https://hub.docker.com/r/csirocass/askapsoft
variable "ASKAPSOFT_IMAGE" {
  default = "csirocass/askapsoft:1.23.1-mpich@sha256:e96bd830fae4e01e1a41e4a70b3a5aa3d38df8a9a08adaed72e84a1c2804a083"
}

# NumPy used to compile casacore's Python converters
variable "BUILD_NUMPY" { default = "2.5.4" }

# casacore measures data. ASTRON only serves the latest copy; changing
# MEASURES_REFRESH downloads it again. The same applies to CASA's data.
variable "MEASURES_URL" { default = "https://www.astron.nl/iers/WSRT_Measures.ztar" }
variable "MEASURES_REFRESH" { default = "" }
variable "CASA_DATA_REFRESH" { default = "" }

# --- Build settings (set by CI) -------------------------------------------------

# Compiler CPU target for C++ code. Never "native", which would tune for the
# build machine. CI builds the portable targets "x86-64" (amd64) and "armv8-a"
# (arm64, including Apple Silicon), plus "x86-64-v3" and "x86-64-v4".
variable "MARCH" { default = "x86-64" }

# Appended to every tag, e.g. "-x86-64-v3"
variable "TAG_SUFFIX" { default = "" }

# Comma-separated list, e.g. "v2.0.0,latest"
variable "TAGS" { default = "dev" }

variable "REGISTRY" { default = "ghcr.io/flint-crew" }
variable "PLATFORMS" { default = "linux/amd64" }

# Registry build cache; leave empty for local builds
variable "CACHE_REF" { default = "" }
variable "CACHE_PUSH" { default = false }
# Empty: main's cache. Set (e.g. "pr-12") to write a separate cache that is
# read before main's, so a branch never overwrites main's cache.
variable "CACHE_SCOPE" { default = "" }

variable "GITHUB_SHA" { default = "" }

# --- Helpers --------------------------------------------------------------------

function "tags" {
  params = [name]
  result = [for t in split(",", TAGS) : "${REGISTRY}/${name}:${trimspace(t)}${TAG_SUFFIX}"]
}

function "cache_from" {
  params = [name]
  result = CACHE_REF == "" ? [] : concat(
    CACHE_SCOPE == "" ? [] : ["type=registry,ref=${CACHE_REF}:${name}-${MARCH}-${CACHE_SCOPE}"],
    ["type=registry,ref=${CACHE_REF}:${name}-${MARCH}"],
  )
}

function "cache_to" {
  params = [name]
  result = CACHE_REF != "" && CACHE_PUSH ? ["type=registry,ref=${CACHE_REF}:${name}-${MARCH}${CACHE_SCOPE == "" ? "" : "-${CACHE_SCOPE}"},mode=max,ignore-error=true"] : []
}

function "git" {
  params = [url, ref]
  result = "${url}#${ref}"
}

# --- Groups -----------------------------------------------------------------------

# All published images (amd64)
group "default" {
  targets = ["calibrate", "wsclean", "aoflagger", "potato", "aegean", "casa", "askapsoft"]
}

# Images with compiled code, built once per CPU target
group "compiled" {
  targets = ["calibrate", "wsclean", "aoflagger", "potato"]
}

# Images available for arm64 (casa and askapsoft are amd64-only upstream)
group "arm64" {
  targets = ["calibrate", "wsclean", "aoflagger", "potato", "aegean"]
}

group "test" {
  targets = ["calibrate-test"]
}

# --- Shared stages ---------------------------------------------------------------

target "_common" {
  platforms = split(",", PLATFORMS)
  args = {
    UBUNTU_IMAGE     = UBUNTU_IMAGE
    MARCH            = MARCH
    MEASURES_URL     = MEASURES_URL
    MEASURES_REFRESH = MEASURES_REFRESH
    BUILD_NUMPY      = BUILD_NUMPY
  }
  labels = {
    "org.opencontainers.image.source"   = "https://github.com/flint-crew/flint-containers"
    "org.opencontainers.image.revision" = GITHUB_SHA
    "io.github.flint-crew.ubuntu"       = UBUNTU_IMAGE
  }
}

target "_base" {
  inherits   = ["_common"]
  context    = "docker/base"
  contexts = {
    casacore-src = git("https://github.com/casacore/casacore.git", CASACORE)
  }
}

target "build-base" {
  inherits = ["_base"]
  target   = "build-base"
}

target "runtime-base" {
  inherits   = ["_base"]
  target     = "runtime-base"
  cache-from = cache_from("runtime-base")
  cache-to   = cache_to("runtime-base")
}

target "casacore-build" {
  inherits   = ["_base"]
  target     = "casacore-build"
  cache-from = cache_from("casacore-build")
  cache-to   = cache_to("casacore-build")
}

target "casacore" {
  inherits   = ["_base"]
  target     = "casacore"
  cache-from = cache_from("casacore")
  cache-to   = cache_to("casacore")
}

# Contexts for images built on casacore
target "_on_casacore" {
  inherits = ["_common"]
  contexts = {
    casacore-build = "target:casacore-build"
    casacore       = "target:casacore"
  }
}

# --- Images ---------------------------------------------------------------------

target "calibrate" {
  inherits = ["_on_casacore"]
  context  = "docker/calibrate"
  target   = "calibrate"
  contexts = {
    calibrate-src = git("https://github.com/flint-crew/calibrate.git", CALIBRATE)
  }
  tags       = tags("calibrate")
  cache-from = cache_from("calibrate")
  cache-to   = cache_to("calibrate")
  labels = {
    "io.github.flint-crew.casacore"  = CASACORE
    "io.github.flint-crew.calibrate" = CALIBRATE
    "io.github.flint-crew.march"     = MARCH
  }
}

target "calibrate-test" {
  inherits = ["calibrate"]
  target   = "test"
  args = {
    PYTHON_CASACORE = PYTHON_CASACORE
  }
  tags     = []
  output   = ["type=cacheonly"]
}

target "wsclean" {
  inherits = ["_on_casacore"]
  context  = "docker/wsclean"
  contexts = {
    wsclean-src   = git("https://gitlab.com/aroffringa/wsclean.git", WSCLEAN)
    idg-src       = git("https://git.astron.nl/RD/idg.git", IDG)
    everybeam-src = git("https://git.astron.nl/RD/EveryBeam.git", EVERYBEAM)
  }
  tags       = tags("wsclean")
  cache-from = cache_from("wsclean")
  cache-to   = cache_to("wsclean")
  labels = {
    "io.github.flint-crew.casacore"  = CASACORE
    "io.github.flint-crew.wsclean"   = WSCLEAN
    "io.github.flint-crew.idg"       = IDG
    "io.github.flint-crew.everybeam" = EVERYBEAM
    "io.github.flint-crew.march"     = MARCH
  }
}

target "aoflagger" {
  inherits = ["_on_casacore"]
  context  = "docker/aoflagger"
  contexts = {
    aoflagger-src = git("https://gitlab.com/aroffringa/aoflagger.git", AOFLAGGER)
  }
  tags       = tags("aoflagger")
  cache-from = cache_from("aoflagger")
  cache-to   = cache_to("aoflagger")
  labels = {
    "io.github.flint-crew.casacore"  = CASACORE
    "io.github.flint-crew.aoflagger" = AOFLAGGER
    "io.github.flint-crew.march"     = MARCH
  }
}

target "potato" {
  inherits = ["_common"]
  context  = "docker/potato"
  contexts = {
    casacore-build      = "target:casacore-build"
    wsclean             = "target:wsclean"
    python-casacore-src = git("https://github.com/casacore/python-casacore.git", PYTHON_CASACORE)
    potato-src          = git("https://gitlab.com/Sunmish/potato.git", POTATO)
  }
  args = {
    PYTHON_CASACORE = PYTHON_CASACORE
  }
  tags       = tags("potato")
  cache-from = cache_from("potato")
  cache-to   = cache_to("potato")
  labels = {
    "io.github.flint-crew.casacore"        = CASACORE
    "io.github.flint-crew.python-casacore" = PYTHON_CASACORE
    "io.github.flint-crew.wsclean"         = WSCLEAN
    "io.github.flint-crew.potato"          = POTATO
    "io.github.flint-crew.march"           = MARCH
  }
}

target "aegean" {
  inherits = ["_common"]
  context  = "docker/aegean"
  contexts = {
    build-base   = "target:build-base"
    runtime-base = "target:runtime-base"
    aegean-src   = git("https://github.com/PaulHancock/Aegean.git", AEGEAN)
  }
  tags       = tags("aegean")
  cache-from = cache_from("aegean")
  cache-to   = cache_to("aegean")
  labels = {
    "io.github.flint-crew.aegean" = AEGEAN
  }
}

target "casa" {
  inherits = ["_common"]
  context  = "docker/casa"
  contexts = {
    build-base   = "target:build-base"
    runtime-base = "target:runtime-base"
  }
  args = {
    CASA              = CASA
    CASACONFIG        = CASACONFIG
    CASA_DATA_REFRESH = CASA_DATA_REFRESH
  }
  tags       = tags("casa")
  cache-from = cache_from("casa")
  cache-to   = cache_to("casa")
  labels = {
    "io.github.flint-crew.casatasks" = CASA
  }
}

target "askapsoft" {
  inherits = ["_common"]
  context  = "docker/askapsoft"
  args = {
    ASKAPSOFT_IMAGE = ASKAPSOFT_IMAGE
  }
  tags = tags("askapsoft")
  labels = {
    "io.github.flint-crew.askapsoft" = ASKAPSOFT_IMAGE
  }
}
