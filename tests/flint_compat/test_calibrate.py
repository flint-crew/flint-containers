"""flint's calibrate-container call sites, run through flint's own code.

Covers:
- ``calibrate`` via flint.calibrate.aocalibrate.create_calibrate_cmd
- ``applysolutions`` via flint.calibrate.aocalibrate.create_apply_solutions_cmd
- ``addmodel`` via flint.predict.addmodel.add_model, called the way
  flint.prefect.common.ms.add_model_source_list_to_ms calls it
"""

from __future__ import annotations

from pathlib import Path

from casacore.tables import table


def test_calibrate_then_applysolutions(
    container, ms_example: Path, calibrate_model: Path
):
    from flint.calibrate.aocalibrate import (
        create_apply_solutions_cmd,
        create_calibrate_cmd,
        load_aosolutions_file,
    )
    from flint.options import MS

    calibrate_container = container("calibrate")
    ms = MS(path=ms_example, column="DATA")

    calibrate_cmd = create_calibrate_cmd(
        ms=ms, calibrate_model=calibrate_model, container=calibrate_container
    )
    assert calibrate_cmd.solution_path.exists()
    solutions = load_aosolutions_file(calibrate_cmd.solution_path)
    assert solutions.bandpass.size > 0

    apply_cmd = create_apply_solutions_cmd(
        ms=ms,
        solutions_file=calibrate_cmd.solution_path,
        container=calibrate_container,
    )
    assert apply_cmd.ms.column == "CORRECTED_DATA"
    with table(str(ms_example), ack=False) as tab:
        assert "CORRECTED_DATA" in tab.colnames()


def test_addmodel(container, ms_example: Path, calibrate_model: Path):
    from flint.predict.addmodel import AddModelOptions, add_model

    add_model(
        add_model_options=AddModelOptions(
            model_path=calibrate_model,
            ms_path=ms_example,
            mode="c",
            datacolumn="MODEL_DATA",
        ),
        container=container("calibrate"),
        remove_datacolumn=True,
    )
    with table(str(ms_example), ack=False) as tab:
        assert "MODEL_DATA" in tab.colnames()
        assert abs(tab.getcol("MODEL_DATA", nrow=10)).max() > 0
