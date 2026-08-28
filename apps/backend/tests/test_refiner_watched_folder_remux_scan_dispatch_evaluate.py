"""Unit tests for watched-folder scan evaluation across every connected media manager."""

from __future__ import annotations

from pathlib import Path

from mediamop.modules.refiner.domain import FileAnchorCandidate, RefinerQueueRowView
from mediamop.modules.refiner.manager_queue_signals import AttributedQueueRow
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_evaluate import (
    evaluate_watched_media_file_for_dispatch,
    merge_queue_views_for_watched_file,
    verdict_for_watched_scan_file,
)
from tests.manager_signal_helpers import reported, unreachable


def _row(label: str, view: RefinerQueueRowView) -> AttributedQueueRow:
    return AttributedQueueRow(connection_label=label, view=view)


def test_verdict_proceeds_when_no_queue_rows(tmp_path) -> None:
    d = tmp_path / "root"
    d.mkdir()
    f = d / "Gate Test 2001.mkv"
    f.write_bytes(b"1")
    rows = merge_queue_views_for_watched_file(signals=[reported([])], file_path=f)
    outcome = verdict_for_watched_scan_file(rows, candidate=FileAnchorCandidate(title="Gate Test 2001", year=None))
    assert outcome.verdict == "proceed"
    assert outcome.blocked_reason is None


def test_verdict_proceeds_when_unrelated_queue_row_exists() -> None:
    row = _row(
        "Radarr (Main)",
        RefinerQueueRowView(
            applies_to_file=False,
            is_upstream_active=True,
            is_import_pending=False,
            queue_title="Different Movie",
            queue_year=2001,
        ),
    )
    outcome = verdict_for_watched_scan_file([row], candidate=FileAnchorCandidate(title="Gate Test 2001", year=None))
    assert outcome.verdict == "proceed"


def test_verdict_proceed_when_owned_and_not_blocked() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    rows = merge_queue_views_for_watched_file(
        signals=[
            reported(
                [
                    {
                        "status": "importPending",
                        "outputPath": str(f.resolve()),
                        "movie": {"title": "Gate Test", "year": 2001},
                    },
                ]
            )
        ],
        file_path=f,
    )
    cand = FileAnchorCandidate(title="Gate Test 2001", year=None)
    assert verdict_for_watched_scan_file(rows, candidate=cand).verdict == "proceed"


def test_verdict_wait_upstream_names_the_connection_not_the_vendor() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    rows = merge_queue_views_for_watched_file(
        signals=[
            reported(
                [
                    {
                        "status": "downloading",
                        "outputPath": str(f.resolve()),
                        "movie": {"title": "Gate Test", "year": 2001},
                    },
                ],
                kind="deluno",
                name="Main",
            )
        ],
        file_path=f,
    )
    cand = FileAnchorCandidate(title="Gate Test 2001", year=None)
    outcome = verdict_for_watched_scan_file(rows, candidate=cand)
    assert outcome.verdict == "wait_upstream"
    assert outcome.blocked_reason == "Deluno (Main) is still importing this file, so MediaMop left it alone for now."


def test_explicit_applies_row_owns_without_anchor_match() -> None:
    row = _row(
        "Radarr (Main)",
        RefinerQueueRowView(
            applies_to_file=True,
            is_upstream_active=False,
            is_import_pending=True,
            queue_title=None,
            queue_year=None,
        ),
    )
    outcome = verdict_for_watched_scan_file([row], candidate=FileAnchorCandidate(title="nope", year=None))
    assert outcome.verdict == "proceed"


def test_a_block_from_any_one_of_two_connections_blocks_the_file() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    quiet = reported([], name="1080p", connection_id=1)
    busy = reported(
        [
            {
                "status": "downloading",
                "outputPath": str(f.resolve()),
                "movie": {"title": "Gate Test", "year": 2001},
            },
        ],
        name="4K",
        connection_id=2,
    )
    outcome = evaluate_watched_media_file_for_dispatch(signals=[quiet, busy], file_path=f)
    assert outcome.verdict == "wait_upstream"
    assert outcome.blocked_reason is not None
    assert "Radarr (4K)" in outcome.blocked_reason


def test_unreachable_manager_contributes_no_rows_so_the_scan_degrades_rather_than_blocking() -> None:
    f = Path("/movies/Gate Test 2001.mkv")
    outcome = evaluate_watched_media_file_for_dispatch(signals=[unreachable(name="4K")], file_path=f)
    assert outcome.verdict == "proceed"
    assert outcome.blocked_reason is None
