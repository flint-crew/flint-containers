"""flint's CASA call sites: mstransform, cvel, gaincal and applycal via `casa -c`."""

from __future__ import annotations

from pathlib import Path

from casacore.tables import table


def test_create_and_merge_spws(container, ms_example: Path):
    from flint.selfcal.casa import create_spws_in_ms, merge_spws_in_ms

    casa = container("casa")
    create_spws_in_ms(casa_container=casa, ms_path=ms_example, nspw=2)
    with table(str(ms_example / "SPECTRAL_WINDOW"), ack=False) as tab:
        assert tab.nrows() == 2

    merge_spws_in_ms(casa_container=casa, ms_path=ms_example)
    with table(str(ms_example / "SPECTRAL_WINDOW"), ack=False) as tab:
        assert tab.nrows() == 1


def test_gaincal_applycal(container, ms_example: Path):
    from flint.options import MS
    from flint.selfcal.casa import gaincal_applycal_ms

    # gaincal needs a model: use a copy of the data.
    with table(str(ms_example), readonly=False, ack=False) as tab:
        description = tab.getcoldesc("DATA")
        description["name"] = "MODEL_DATA"
        tab.addcols(description)
        tab.putcol("MODEL_DATA", tab.getcol("DATA"))

    cal_ms = gaincal_applycal_ms(
        ms=MS(path=ms_example, column="DATA"),
        casa_container=container("casa"),
    )

    with table(str(cal_ms.path), ack=False) as tab:
        assert "CORRECTED_DATA" in tab.colnames()
