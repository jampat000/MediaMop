"""Safety contract for opt-in rejected-file cleanup."""

from pathlib import Path

from mediamop.modules.refiner.refiner_rejected_file_cleanup import cleanup_rejected_file


def test_rejected_file_cleanup_leaves_file_by_default(tmp_path: Path) -> None:
    watched = tmp_path / "watch"
    watched.mkdir()
    source = watched / "small.mkv"
    source.write_bytes(b"small")

    result = cleanup_rejected_file(watched_root=watched, file_path=source, action="leave")

    assert result.deleted is False
    assert source.exists()
    assert "Leave in place" in result.detail


def test_rejected_file_cleanup_deletes_only_file_and_empty_parents(tmp_path: Path) -> None:
    watched = tmp_path / "watch"
    release = watched / "Release"
    release.mkdir(parents=True)
    rejected = release / "sample.mkv"
    keep = release / "movie.mkv"
    rejected.write_bytes(b"sample")
    keep.write_bytes(b"movie")

    result = cleanup_rejected_file(watched_root=watched, file_path=rejected, action="delete_file")

    assert result.deleted is True
    assert not rejected.exists()
    assert keep.exists()
    assert release.exists()
    assert watched.exists()


def test_rejected_file_cleanup_refuses_path_outside_watched_root(tmp_path: Path) -> None:
    watched = tmp_path / "watch"
    watched.mkdir()
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"outside")

    result = cleanup_rejected_file(watched_root=watched, file_path=outside, action="delete_file")

    assert result.deleted is False
    assert outside.exists()
    assert "safely inside" in result.detail
