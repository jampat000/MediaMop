from pathlib import Path

import pytest

from mediamop.platform.file_lifecycle.mutations import (
    FileLifecycleError,
    safe_copy_to_final,
    safe_finalize_file,
    safe_unlink,
    try_hardlink_to_final,
)


def test_safe_copy_to_final_replaces_only_after_complete(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    final = tmp_path / "out" / "source.mkv"
    source.write_text("new", encoding="utf-8")
    final.parent.mkdir()
    final.write_text("old", encoding="utf-8")

    safe_copy_to_final(source=source, final=final)

    assert final.read_text(encoding="utf-8") == "new"
    assert source.read_text(encoding="utf-8") == "new"
    assert not list(final.parent.glob("*.partial"))


def test_safe_finalize_file_moves_completed_stage_to_final(tmp_path: Path) -> None:
    staged = tmp_path / "work" / "file.partial.mkv"
    final = tmp_path / "out" / "file.mkv"
    staged.parent.mkdir()
    staged.write_text("complete", encoding="utf-8")

    safe_finalize_file(staged=staged, final=final)

    assert final.read_text(encoding="utf-8") == "complete"
    assert not staged.exists()


def test_try_hardlink_to_final_keeps_source_and_replaces_final(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    final = tmp_path / "final.mkv"
    source.write_text("source", encoding="utf-8")
    final.write_text("old", encoding="utf-8")

    assert try_hardlink_to_final(source=source, final=final) is True

    assert source.read_text(encoding="utf-8") == "source"
    assert final.read_text(encoding="utf-8") == "source"


def test_safe_unlink_reports_missing_as_absent(tmp_path: Path) -> None:
    missing = tmp_path / "missing.tmp"
    assert safe_unlink(missing) is False


def test_safe_copy_wraps_errors(tmp_path: Path) -> None:
    with pytest.raises(FileLifecycleError):
        safe_copy_to_final(source=tmp_path / "missing.mkv", final=tmp_path / "out.mkv")
