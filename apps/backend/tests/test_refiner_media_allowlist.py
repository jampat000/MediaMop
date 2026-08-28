"""What Refiner will pick up in a watched folder, and what it says about the rest.

Extension mismatch used to be the only admission decision that produced no counter, no
reason and no activity row: a ``.mov`` beside a film simply never appeared, and nothing
explained why (#348).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.modules.refiner.refiner_remux_rules import (
    is_refiner_media_candidate,
    refiner_media_extensions_sorted,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_ops import (
    iter_watched_folder_media_candidates,
)

# Verified against ffmpeg before being added: ffprobe reads each, and a stream-copy
# remux to MKV succeeds.
_NEWLY_ADMITTED = (".mpe", ".mpeg", ".mpg", ".mov", ".flv", ".wmv", ".avchd")
_ALREADY_ADMITTED = (".mkv", ".mp4", ".m4v", ".webm", ".avi")


@pytest.mark.parametrize("suffix", _NEWLY_ADMITTED + _ALREADY_ADMITTED)
def test_supported_container_is_admitted(tmp_path: Path, suffix: str) -> None:
    f = tmp_path / f"Some Film 2024{suffix}"
    f.write_bytes(b"x")
    assert is_refiner_media_candidate(f) is True
    assert suffix in refiner_media_extensions_sorted()


@pytest.mark.parametrize("suffix", [".h264", ".h265", ".mpv"])
def test_raw_elementary_streams_stay_out(tmp_path: Path, suffix: str) -> None:
    """These remux fine and must still be refused.

    A raw elementary stream carries no audio track, so ``plan_remux`` returns None, the
    pass records a terminal failure, and Pass 4 failure cleanup deletes the source folder
    once the grace period elapses. Admitting them would turn "silently ignored" into
    "your folder is gone".
    """

    f = tmp_path / f"Some Film 2024{suffix}"
    f.write_bytes(b"x")
    assert is_refiner_media_candidate(f) is False
    assert suffix not in refiner_media_extensions_sorted()


@pytest.mark.parametrize("suffix", [".iso", ".exe", ".rar", ".zip"])
def test_genuinely_unsupported_types_stay_out(tmp_path: Path, suffix: str) -> None:
    f = tmp_path / f"Some Film 2024{suffix}"
    f.write_bytes(b"x")
    assert is_refiner_media_candidate(f) is False


def test_a_rejected_file_is_counted_rather_than_dropped_in_silence(tmp_path: Path) -> None:
    for name in ("keep.mkv", "keep.mov", "drop.iso", "drop.h264"):
        (tmp_path / name).write_bytes(b"x")

    result = iter_watched_folder_media_candidates(tmp_path)

    assert sorted(p.name for p in result.files) == ["keep.mkv", "keep.mov"]
    assert result.ignored_unsupported_type == 2
    assert result.ignored_unsupported_extensions == (".h264", ".iso")


def test_subtitles_and_artwork_are_not_counted_as_unsupported_media(tmp_path: Path) -> None:
    """Counting every sidecar would bury the signal this counter exists to give."""

    for name in ("film.mkv", "film.srt", "poster.jpg", "film.nfo", "film.par2", "theme.mp3"):
        (tmp_path / name).write_bytes(b"x")

    result = iter_watched_folder_media_candidates(tmp_path)

    assert [p.name for p in result.files] == ["film.mkv"]
    assert result.ignored_unsupported_type == 0


def test_a_part_file_is_not_reported_as_an_unsupported_type(tmp_path: Path) -> None:
    """A part-file is the same file mid-copy, not a failed attempt at a media file."""

    (tmp_path / "film.mkv.part").write_bytes(b"x")
    (tmp_path / "film.mkv").write_bytes(b"x")

    result = iter_watched_folder_media_candidates(tmp_path)

    assert [p.name for p in result.files] == ["film.mkv"]
    assert result.ignored_unsupported_type == 0


def test_the_effective_allowlist_is_reportable(tmp_path: Path) -> None:
    applied = refiner_media_extensions_sorted()
    assert applied == tuple(sorted(applied))
    assert all(e.startswith(".") and e == e.lower() for e in applied)
    assert len(applied) == 12
