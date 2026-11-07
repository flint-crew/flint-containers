"""flint's BANE and aegean call sites."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits

SIZE = 256


def make_image(template: Path, output: Path) -> Path:
    """Write a noise image with three bright sources, using the template's WCS and beam.

    The images packaged with flint are 10x10 pixels, smaller than BANE's grid.
    """
    header = fits.getheader(template)
    header["NAXIS1"] = header["NAXIS2"] = SIZE
    header["CRPIX1"] = header["CRPIX2"] = SIZE / 2

    rng = np.random.default_rng(42)
    data = rng.normal(scale=1e-3, size=(1, 1, SIZE, SIZE)).astype(np.float32)
    sigma_pix = header["BMAJ"] / abs(header["CDELT2"]) / 2.355
    y, x = np.mgrid[:SIZE, :SIZE]
    for cx, cy in ((64, 64), (128, 160), (200, 90)):
        data[0, 0] += 0.1 * np.exp(
            -((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma_pix**2)
        )

    fits.writeto(output, data, header)
    return output


def test_bane_and_aegean(container, packaged_images: list[Path], tmp_path: Path):
    from flint.source_finding.aegean import run_bane_and_aegean

    image = make_image(packaged_images[0], tmp_path / "test-image.fits")

    outputs = run_bane_and_aegean(
        image=image,
        aegean_container=container("aegean"),
        update_bane_options={"cores": 2, "flint_use_fft": False},
    )

    assert outputs.bkg.exists()
    assert outputs.rms.exists()
    assert outputs.comp.exists()
    components = fits.getdata(outputs.comp)
    assert (components["peak_flux"] > 0.05).sum() == 3
