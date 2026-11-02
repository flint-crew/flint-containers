"""flint's linmos call site (askapsoft image)."""

from __future__ import annotations

from pathlib import Path


def test_linmos_images(container, packaged_images: list[Path], tmp_path: Path):
    from flint.coadd.linmos import LinmosOptions, linmos_images

    result = linmos_images(
        images=packaged_images,
        linmos_options=LinmosOptions(base_output_name=tmp_path / "linmos_field"),
        container=container("askapsoft"),
    )

    assert result.image_fits.exists()
    assert result.weight_fits.exists()
