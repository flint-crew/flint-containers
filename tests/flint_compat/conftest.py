"""Fixtures for running flint's own container call sites against freshly built images.

Usage:
    pytest tests/flint_compat --container-dir <dir> --expect calibrate[,wsclean,...]

``<dir>`` holds the images converted to Apptainer files with the names flint
expects (``flint-containers_<name>.sif``). Tests for a container listed in
``--expect`` fail if its file is missing. Tests for any other container are
skipped, so the suite can grow image by image.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--container-dir",
        type=Path,
        required=True,
        help="Directory of flint-containers_<name>.sif files to test",
    )
    parser.addoption(
        "--expect",
        default="",
        help="Comma-separated container names that must be present",
    )


@pytest.fixture(scope="session")
def container_dir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.getoption("--container-dir")).absolute()


@pytest.fixture(scope="session")
def expected(request: pytest.FixtureRequest) -> set[str]:
    raw: str = request.config.getoption("--expect")
    return {name.strip() for name in raw.split(",") if name.strip()}


@pytest.fixture(scope="session")
def container(container_dir: Path, expected: set[str]):
    """Return the path of a named container, resolved through flint itself.

    Going through ``flint.containers.get_known_container_path`` also checks
    that the file name matches what flint expects.
    """
    from flint.containers import get_known_container_path

    def _container(name: str) -> Path:
        try:
            return get_known_container_path(container_directory=container_dir, name=name)
        except AssertionError:
            if name in expected:
                pytest.fail(f"Expected container '{name}' is missing from {container_dir}")
            pytest.skip(f"Container '{name}' not built in this run")

    return _container


@pytest.fixture
def ms_example(tmp_path: Path) -> Path:
    """A fresh copy of the small ASKAP measurement set packaged with flint."""
    from flint.utils import get_packaged_resource_path

    ms_zip = get_packaged_resource_path(
        package="flint.data.tests",
        filename="SB39400.RACS_0635-31.beam0.small.ms.zip",
    )
    shutil.unpack_archive(ms_zip, tmp_path)
    ms_path = tmp_path / "SB39400.RACS_0635-31.beam0.small.ms"
    assert ms_path.exists()
    return ms_path


@pytest.fixture
def calibrate_model() -> Path:
    """flint's packaged PKS B1934-638 calibrate sky model."""
    from flint.utils import get_packaged_resource_path

    return get_packaged_resource_path(
        package="flint.data.models", filename="1934-638.calibrate.txt"
    )
