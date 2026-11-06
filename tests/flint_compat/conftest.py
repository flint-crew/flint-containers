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
            return get_known_container_path(
                container_directory=container_dir, name=name
            )
        except AssertionError:
            if name in expected:
                pytest.fail(
                    f"Expected container '{name}' is missing from {container_dir}"
                )
            pytest.skip(f"Container '{name}' not built in this run")

    return _container


RFI_CHANNELS = slice(100, 104)
"""Channels given strong interference in ms_example, for the aoflagger test"""


@pytest.fixture
def ms_example(tmp_path: Path) -> Path:
    """A small ASKAP measurement set with usable data.

    Starts from the measurement set packaged with flint (36 antennas, 288
    channels, 3 timesteps), whose data are all flagged with zero UVWs. Fills in
    UVWs, a 1 Jy point source at the phase centre plus noise, and strong
    interference in RFI_CHANNELS, and unflags the cross-correlations.
    """
    import numpy as np
    from casacore.tables import table
    from flint.utils import get_packaged_resource_path

    ms_zip = get_packaged_resource_path(
        package="flint.data.tests",
        filename="SB39400.RACS_0635-31.beam0.small.ms.zip",
    )
    shutil.unpack_archive(ms_zip, tmp_path)
    ms_path = tmp_path / "SB39400.RACS_0635-31.beam0.small.ms"

    with table(str(ms_path / "ANTENNA"), ack=False) as tab:
        positions = tab.getcol("POSITION")
    with table(str(ms_path / "FIELD"), ack=False) as tab:
        ra, dec = tab.getcol("PHASE_DIR")[0, 0]

    with table(str(ms_path), readonly=False, ack=False) as tab:
        ant1, ant2 = tab.getcol("ANTENNA1"), tab.getcol("ANTENNA2")
        time = tab.getcol("TIME")
        shape = tab.getcol("DATA").shape

        # Approximate UVWs (no precession or nutation), as in calibrate's tests/msgen.py
        hour_angle = (
            2
            * np.pi
            * (0.7790572732640 + 1.00273781191135448 * (time / 86400 - 51544.5))
            - ra
        )
        lx, ly, lz = (positions[ant2] - positions[ant1]).T
        sin_h, cos_h, sin_d, cos_d = (
            np.sin(hour_angle),
            np.cos(hour_angle),
            np.sin(dec),
            np.cos(dec),
        )
        uvw = np.stack(
            [
                sin_h * lx + cos_h * ly,
                -sin_d * cos_h * lx + sin_d * sin_h * ly + cos_d * lz,
                cos_d * cos_h * lx - cos_d * sin_h * ly + sin_d * lz,
            ],
            axis=1,
        )

        rng = np.random.default_rng(42)
        data = 0.05 * (rng.standard_normal(shape) + 1j * rng.standard_normal(shape))
        data[:, :, 0] += 1.0
        data[:, :, 3] += 1.0
        data[:, RFI_CHANNELS, :] += 1000.0

        autos = ant1 == ant2
        flags = np.zeros(shape, dtype=bool)
        flags[autos] = True

        tab.putcol("UVW", uvw)
        tab.putcol("DATA", data.astype(np.complex64))
        tab.putcol("FLAG", flags)
        tab.putcol("FLAG_ROW", autos)
        tab.putcol("WEIGHT", np.ones(tab.getcol("WEIGHT").shape, dtype=np.float32))
    return ms_path


@pytest.fixture
def calibrate_model() -> Path:
    """flint's packaged PKS B1934-638 calibrate sky model."""
    from flint.utils import get_packaged_resource_path

    return get_packaged_resource_path(
        package="flint.data.models", filename="1934-638.calibrate.txt"
    )


@pytest.fixture
def packaged_images(tmp_path: Path) -> list[Path]:
    """Two small beam images packaged with flint, copied so outputs land in tmp_path."""
    from flint.utils import get_packaged_resource_path

    names = (
        "SB56659.RACS_0940-04.beam17.round3-0000-image.sub.fits",
        "SB56659.RACS_0940-04.beam17.round3-0001-image.sub.fits",
    )
    copies = []
    for name in names:
        source = get_packaged_resource_path(package="flint.data.tests", filename=name)
        copies.append(Path(shutil.copy(source, tmp_path / name)))
    return copies
