"""Refiner candidate gate: domain evaluation over real queue-shaped dicts (no HTTP)."""

from __future__ import annotations

from mediamop.modules.refiner.domain import FileAnchorCandidate
from mediamop.modules.refiner.refiner_candidate_gate_evaluate import (
    evaluate_refiner_candidate_gate_from_queue_rows,
)


def test_radarr_wait_upstream_when_path_match_and_downloading() -> None:
    rows = [
        {
            "status": "downloading",
            "outputPath": "D:\\Media\\Film.mkv",
            "movie": {"title": "Solaris", "year": 1972},
        },
    ]
    out = evaluate_refiner_candidate_gate_from_queue_rows(
        target="radarr",
        queue_rows=rows,
        release_title="Solaris 1972",
        release_year=1972,
        output_path=r"D:/media/film.mkv",
        movie_id=None,
        series_id=None,
    )
    assert out.verdict == "wait_upstream"
    assert out.owned is True
    assert out.blocked_upstream is True
    assert out.queue_row_count == 1


def test_radarr_proceed_import_pending_with_suppression() -> None:
    rows = [
        {
            "status": "importPending",
            "outputPath": "/data/complete/movie.mkv",
            "blockingSuppressedForImportWait": True,
            "movie": {"title": "Nashville", "year": 1975},
        },
    ]
    out = evaluate_refiner_candidate_gate_from_queue_rows(
        target="radarr",
        queue_rows=rows,
        release_title="Nashville",
        release_year=1975,
        output_path="/data/complete/movie.mkv",
        movie_id=None,
        series_id=None,
    )
    assert out.verdict == "proceed"
    assert out.owned is True
    assert out.blocked_upstream is False


def test_radarr_not_held_when_queue_empty() -> None:
    out = evaluate_refiner_candidate_gate_from_queue_rows(
        target="radarr",
        queue_rows=[],
        release_title="Anything",
        release_year=None,
        output_path=None,
        movie_id=None,
        series_id=None,
    )
    assert out.verdict == "not_held"
    assert out.owned is False
    assert out.queue_row_count == 0


def test_radarr_not_held_when_anchor_no_match() -> None:
    rows = [
        {
            "status": "completed",
            "movie": {"title": "Other Movie", "year": 1999},
        },
    ]
    cand = FileAnchorCandidate(title="Unrelated Release 2020")
    out = evaluate_refiner_candidate_gate_from_queue_rows(
        target="radarr",
        queue_rows=rows,
        release_title=cand.title,
        release_year=cand.year,
        output_path=None,
        movie_id=None,
        series_id=None,
    )
    assert out.verdict == "not_held"
    assert out.owned is False
