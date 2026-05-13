"""Unit tests for merged-queue watched-folder scan evaluation."""

from __future__ import annotations

from pathlib import Path

from mediamop.modules.refiner.domain import FileAnchorCandidate, RefinerQueueRowView
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_evaluate import (
    merge_queue_views_for_watched_file,
    verdict_for_watched_scan_file,
)


def test_verdict_proceeds_when_no_queue_rows(tmp_path) -> None:
    d = tmp_path / "root"
    d.mkdir()
    f = d / "Gate Test 2001.mkv"
    f.write_bytes(b"1")
    v = merge_queue_views_for_watched_file(radarr_rows=[], sonarr_rows=[], file_path=f)
    assert (
        verdict_for_watched_scan_file(v, candidate=FileAnchorCandidate(title="Gate Test 2001", year=None)) == "proceed"
    )


def test_verdict_proceeds_when_unrelated_queue_row_exists() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    row = RefinerQueueRowView(
        applies_to_file=False,
        is_upstream_active=True,
        is_import_pending=False,
        queue_title="Different Movie",
        queue_year=2001,
    )
    assert (
        verdict_for_watched_scan_file([row], candidate=FileAnchorCandidate(title="Gate Test 2001", year=None))
        == "proceed"
    )


def test_verdict_proceed_when_owned_and_not_blocked() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    rad = [
        {
            "status": "importPending",
            "outputPath": str(f.resolve()),
            "movie": {"title": "Gate Test", "year": 2001},
        },
    ]
    views = merge_queue_views_for_watched_file(radarr_rows=rad, sonarr_rows=[], file_path=f)
    cand = FileAnchorCandidate(title="Gate Test 2001", year=None)
    assert verdict_for_watched_scan_file(views, candidate=cand) == "proceed"


def test_verdict_wait_upstream_when_owned_and_active() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    rad = [
        {
            "status": "downloading",
            "outputPath": str(f.resolve()),
            "movie": {"title": "Gate Test", "year": 2001},
        },
    ]
    views = merge_queue_views_for_watched_file(radarr_rows=rad, sonarr_rows=[], file_path=f)
    cand = FileAnchorCandidate(title="Gate Test 2001", year=None)
    assert verdict_for_watched_scan_file(views, candidate=cand) == "wait_upstream"


def test_explicit_applies_row_owns_without_anchor_match() -> None:
    f = Path("/data/oddname.mkv")
    row = RefinerQueueRowView(
        applies_to_file=True,
        is_upstream_active=False,
        is_import_pending=True,
        queue_title=None,
        queue_year=None,
    )
    assert verdict_for_watched_scan_file([row], candidate=FileAnchorCandidate(title="nope", year=None)) == "proceed"
