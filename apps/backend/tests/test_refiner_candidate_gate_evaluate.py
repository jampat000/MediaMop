"""Refiner candidate gate: domain evaluation over media-manager port answers (no HTTP)."""

from __future__ import annotations

from mediamop.modules.refiner.refiner_candidate_gate_evaluate import (
    evaluate_refiner_candidate_gate_from_manager_signals,
)
from tests.manager_signal_helpers import no_queue_signal, reported, unreachable


def _evaluate(signals, **kwargs):
    defaults = {
        "media_scope": "movie",
        "release_title": "Anything",
        "release_year": None,
        "output_path": None,
        "entity_id": None,
    }
    defaults.update(kwargs)
    return evaluate_refiner_candidate_gate_from_manager_signals(signals=signals, **defaults)


def test_wait_upstream_when_path_match_and_downloading() -> None:
    rows = [
        {
            "status": "downloading",
            "outputPath": "D:\\Media\\Film.mkv",
            "movie": {"title": "Solaris", "year": 1972},
        },
    ]
    out = _evaluate(
        [reported(rows, name="4K")],
        release_title="Solaris 1972",
        release_year=1972,
        output_path=r"D:/media/film.mkv",
    )
    assert out.verdict == "wait_upstream"
    assert out.owned is True
    assert out.blocked_upstream is True
    assert out.queue_row_count == 1


def test_proceed_import_pending_with_suppression() -> None:
    rows = [
        {
            "status": "importPending",
            "outputPath": "/data/complete/movie.mkv",
            "blockingSuppressedForImportWait": True,
            "movie": {"title": "Nashville", "year": 1975},
        },
    ]
    out = _evaluate(
        [reported(rows)],
        release_title="Nashville",
        release_year=1975,
        output_path="/data/complete/movie.mkv",
    )
    assert out.verdict == "proceed"
    assert out.owned is True
    assert out.blocked_upstream is False


def test_not_held_when_every_manager_reports_an_empty_queue() -> None:
    out = _evaluate([reported([])])
    assert out.verdict == "not_held"
    assert out.owned is False
    assert out.queue_row_count == 0
    assert out.managers_reporting == 1


def test_not_held_when_anchor_no_match() -> None:
    rows = [{"status": "completed", "movie": {"title": "Other Movie", "year": 1999}}]
    out = _evaluate([reported(rows)], release_title="Unrelated Release 2020")
    assert out.verdict == "not_held"
    assert out.owned is False


def test_no_manager_configured_is_not_an_empty_queue() -> None:
    out = _evaluate([])
    assert out.verdict == "no_upstream_signal"
    assert out.managers_consulted == 0
    assert "No media manager is connected for Movies" in out.reasons[0]


def test_manager_with_no_queue_signal_never_reads_as_safe() -> None:
    out = _evaluate([no_queue_signal(name="Main")])
    assert out.verdict == "no_upstream_signal"
    assert out.managers_reporting == 0
    assert out.managers_without_queue_signal == ("Media manager (Main)",)


def test_unreachable_manager_is_reported_not_treated_as_clear() -> None:
    out = _evaluate([unreachable(name="4K", detail="Connection refused.")])
    assert out.verdict == "no_upstream_signal"
    assert out.managers_without_queue_signal == ("Radarr (4K)",)


def test_two_connections_and_only_one_blocks_still_blocks_the_file() -> None:
    quiet = reported([], name="1080p", connection_id=1)
    busy = reported(
        [
            {
                "status": "downloading",
                "outputPath": "/media/movies/Solaris.mkv",
                "movie": {"title": "Solaris", "year": 1972},
            },
        ],
        name="4K",
        connection_id=2,
    )
    out = _evaluate(
        [quiet, busy],
        release_title="Solaris 1972",
        release_year=1972,
        output_path="/media/movies/Solaris.mkv",
    )
    assert out.verdict == "wait_upstream"
    assert out.blocked_by_connection == "Radarr (4K)"
    assert "Radarr (4K) is still importing this file" in out.reasons[0]


def test_partial_answer_still_reports_the_manager_that_stayed_silent() -> None:
    out = _evaluate(
        [reported([], name="1080p", connection_id=1), unreachable(name="4K", connection_id=2)],
        release_title="Solaris 1972",
    )
    assert out.verdict == "not_held"
    assert out.managers_without_queue_signal == ("Radarr (4K)",)
    assert any("could not get an import check from Radarr (4K)" in reason for reason in out.reasons)


def test_a_manager_serving_both_scopes_answers_a_tv_candidate() -> None:
    rows = [
        {
            "status": "downloading",
            "outputPath": "/tv/Show/S01E01.mkv",
            "media": {"title": "Show", "year": 2001},
        },
    ]
    out = _evaluate(
        [reported(rows, scope="tv", kind="deluno", name="Main")],
        media_scope="tv",
        release_title="Show 2001",
        release_year=2001,
        output_path="/tv/Show/S01E01.mkv",
    )
    assert out.verdict == "wait_upstream"
    assert out.blocked_by_connection == "Deluno (Main)"
