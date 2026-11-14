"""flint's rclone call site, copying archived products to a folder.

A copy to an object store needs a remote and its credentials, so only the
folder destination is tested. flint runs the same rclone command for both.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CalledProcessError

import pytest


def test_rclone_copy_to_a_folder(container, tmp_path: Path):
    from flint import archive

    # Checked first: a flint without rclone_copy doesn't know the rclone
    # container either, and container() would fail on it
    if not hasattr(archive, "rclone_copy"):
        pytest.skip("this flint does not archive with rclone")
    rclone = container("rclone")

    root = tmp_path / "SB60001"
    files = [Path("SB60001.beam0.ms.tar"), Path("images/a field image.fits")]
    for file in files:
        (root / file).parent.mkdir(parents=True, exist_ok=True)
        (root / file).write_text(f"contents of {file}\n")
    destination = tmp_path / "archive" / "SB60001"

    def copy() -> None:
        archive.rclone_copy(
            container=rclone,
            config=None,
            root=root,
            files=files,
            location=str(destination),
        )

    copy()
    for file in files:
        assert (destination / file).read_text() == (root / file).read_text()

    # Files already there and the same are left alone
    copy()

    # One that differs is an error, never overwritten
    (root / files[0]).write_text("changed\n")
    with pytest.raises(CalledProcessError):
        copy()
    assert (destination / files[0]).read_text() == f"contents of {files[0]}\n"
