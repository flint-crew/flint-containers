"""flint's aoflagger call site."""

from __future__ import annotations

from pathlib import Path

from casacore.tables import table

from conftest import RFI_CHANNELS


def test_flag_ms_aoflagger(container, ms_example: Path):
    from flint.flagging import flag_ms_aoflagger
    from flint.options import MS

    flag_ms_aoflagger(ms=MS(path=ms_example, column="DATA"), container=container("aoflagger"))

    with table(str(ms_example), ack=False) as tab:
        cross = tab.getcol("ANTENNA1") != tab.getcol("ANTENNA2")
        flags = tab.getcol("FLAG")[cross]
    assert flags[:, RFI_CHANNELS].mean() > 0.9
