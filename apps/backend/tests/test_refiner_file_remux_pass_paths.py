"""Safe path join for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.modules.refiner.refiner_file_remux_pass_paths import resolve_media_file_under_refiner_root


def test_resolve_rejects_parent_segments(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    f = media / "a.mkv"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match="parent"):
        resolve_media_file_under_refiner_root(media_root=str(media), relative_path="../a.mkv")


def test_resolve_accepts_file_under_root(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    f = media / "sub" / "a.mkv"
    f.parent.mkdir()
    f.write_bytes(b"x")
    got = resolve_media_file_under_refiner_root(media_root=str(media), relative_path="sub/a.mkv")
    assert got == f.resolve()
