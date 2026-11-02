"""flint's wsclean call site, with a small image so it runs quickly."""

from __future__ import annotations

from pathlib import Path

from casacore.tables import table

SMALL_IMAGE = {
    "size": 512,
    "scale": "10asec",
    "niter": 500,
    "nmiter": 2,
    "channels_out": 2,
    "local_rms": False,
    "auto_mask": None,
    "auto_threshold": 3.0,
}


def test_wsclean_imager(container, ms_example: Path, tmp_path: Path):
    from flint.imager.wsclean import wsclean_imager
    from flint.options import MS

    result = wsclean_imager(
        ms=[MS(path=ms_example, column="DATA")],
        wsclean_container=container("wsclean"),
        update_wsclean_options={**SMALL_IMAGE, "temp_dir": str(tmp_path)},
    )

    assert result.image_set is not None
    assert result.image_set.image
    assert all(Path(image).exists() for image in result.image_set.image)
    with table(str(ms_example), ack=False) as tab:
        assert "MODEL_DATA" in tab.colnames()
