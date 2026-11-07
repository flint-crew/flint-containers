"""flint's potato call sites: peel_configuration.py and hot_potato."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from casacore.tables import table


def test_potato_config_and_peel(container, ms_example: Path, tmp_path: Path):
    from flint.options import MS
    from flint.peel.potato import (
        PotatoConfigOptions,
        PotatoPeelArguments,
        PotatoPeelOptions,
        create_run_potato_config,
        create_run_potato_peel,
    )

    potato = container("potato")
    ms = MS(path=ms_example, column="DATA")

    config = create_run_potato_config(
        potato_container=potato,
        ms_path=ms,
        potato_config_options=PotatoConfigOptions(
            image_size=512,
            image_channels=1,
            peel_size=256,
            peel_channels=1,
            peel_nmiter=1,
        ),
    )
    assert config.config_path.exists()

    # Peel a made-up source at the phase centre; this only checks the run completes.
    with table(str(ms_example / "FIELD"), ack=False) as tab:
        ra, dec = np.degrees(tab.getcol("PHASE_DIR")[0, 0])
    create_run_potato_peel(
        potato_container=potato,
        ms=ms,
        potato_peel_arguments=PotatoPeelArguments(
            ms=ms_example,
            ras=[ra],
            decs=[dec],
            peel_fovs=[0.1],
            image_fov=1.0,
            n=["test"],
        ),
        potato_peel_options=PotatoPeelOptions(
            c=config.config_path, tmp=tmp_path, minpeelflux=0.0
        ),
    )
