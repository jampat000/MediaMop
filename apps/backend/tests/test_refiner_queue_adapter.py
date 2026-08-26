"""Media-manager queue rows -> Refiner domain, one mapper driven by a media-scope dialect.

Ported from the former per-vendor adapter tests so the movie and TV behaviour that
Radarr and Sonarr rows relied on is still asserted, plus the neutral keys any other
manager (Deluno, or anything posting the native payload) can use.
"""

from __future__ import annotations

import pytest

from mediamop.modules.refiner import (
    MOVIE_QUEUE_DIALECT,
    TV_QUEUE_DIALECT,
    FileAnchorCandidate,
    file_is_owned_by_queue,
    map_queue_row_to_refiner_view,
    queue_dialect_for_scope,
    should_block_for_upstream,
)

# --- movie scope (the shape Radarr sends) ------------------------------------


def test_movie_active_downloading_row_path_match_owns_and_blocks() -> None:
    row = {
        "status": "downloading",
        "outputPath": "D:\\Media\\Film.mkv",
        "movie": {"title": "Solaris", "year": 1972},
    }
    v = map_queue_row_to_refiner_view(
        row,
        MOVIE_QUEUE_DIALECT,
        candidate_path=r"D:/media/film.mkv",
    )
    assert v.applies_to_file is True
    assert v.is_import_pending is False
    assert v.is_upstream_active is True
    assert v.blocking_suppressed_for_import_wait is False
    assert file_is_owned_by_queue((v,)) is True
    assert should_block_for_upstream((v,)) is True


def test_movie_import_pending_row_owns_by_path_suppression_carried() -> None:
    row = {
        "status": "importPending",
        "outputPath": "/data/complete/movie.mkv",
        "blockingSuppressedForImportWait": True,
        "movie": {"title": "Nashville", "year": 1975},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT, candidate_path="/data/complete/movie.mkv")
    assert v.is_import_pending is True
    assert v.is_upstream_active is False
    assert v.blocking_suppressed_for_import_wait is True
    assert file_is_owned_by_queue((v,)) is True
    assert should_block_for_upstream((v,)) is False


def test_movie_downloading_row_suppressed_does_not_block_but_still_owns() -> None:
    row = {
        "status": "downloading",
        "outputPath": "/srv/queue/x.mkv",
        "blocking_suppressed_for_import_wait": True,
        "movie": {"title": "Stalker", "year": 1979},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT, candidate_path="/srv/queue/x.mkv")
    assert v.is_upstream_active is True
    assert v.blocking_suppressed_for_import_wait is True
    assert file_is_owned_by_queue((v,)) is True
    assert should_block_for_upstream((v,)) is False


def test_movie_completed_row_owns_via_title_year_anchor_only() -> None:
    row = {
        "status": "completed",
        "title": "The.Towering.Inferno.1974.1080p.BluRay.x264",
        "movie": {"title": "The Towering Inferno", "year": 1974},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT, candidate_path=None)
    assert v.applies_to_file is False
    assert v.is_upstream_active is False
    assert v.queue_title == "The Towering Inferno"
    assert v.queue_year == 1974
    cand = FileAnchorCandidate(title="The Towering Inferno 1974 Remux")
    assert file_is_owned_by_queue((v,), file_candidate=cand) is True
    assert should_block_for_upstream((v,), file_candidate=cand) is False


def test_movie_applicability_via_movie_id_without_path() -> None:
    row = {
        "status": "queued",
        "movieId": 42,
        "movie": {"title": "Heat", "year": 1995},
    }
    v = map_queue_row_to_refiner_view(
        row,
        MOVIE_QUEUE_DIALECT,
        candidate_path=None,
        candidate_entity_id=42,
    )
    assert v.applies_to_file is True
    assert v.is_upstream_active is True


def test_movie_title_only_applicability_via_anchor_no_path_or_id() -> None:
    row = {
        "status": "failed",
        "movie": {"title": "The Conversation", "year": 1974},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT)
    assert v.applies_to_file is False
    cand = FileAnchorCandidate(title="The Conversation 1974")
    assert file_is_owned_by_queue((v,), file_candidate=cand) is True
    assert should_block_for_upstream((v,), file_candidate=cand) is False


def test_tracked_download_status_fallback() -> None:
    row = {
        "trackedDownloadStatus": "Downloading",
        "outputPath": "/tmp/z.mkv",
        "movie": {"title": "Z", "year": 2001},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT, candidate_path="/tmp/z.mkv")
    assert v.is_upstream_active is True


def test_movie_dialect_ignores_series_block() -> None:
    """The movie dialect never consults ``series``, so TV keys cannot override it."""
    row = {
        "status": "completed",
        "movie": {"title": "Correct Movie", "year": 2020},
        "series": {"title": "Wrong Series", "year": 1999},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT)
    assert v.queue_title == "Correct Movie"
    assert v.queue_year == 2020


# --- tv scope (the shape Sonarr sends) ---------------------------------------


def test_tv_active_paused_row_series_id_owns_and_blocks() -> None:
    row = {
        "status": "paused",
        "seriesId": 9001,
        "series": {"title": "Sample Show", "year": 2020},
    }
    v = map_queue_row_to_refiner_view(row, TV_QUEUE_DIALECT, candidate_entity_id=9001)
    assert v.applies_to_file is True
    assert v.queue_title == "Sample Show"
    assert v.is_upstream_active is True
    assert file_is_owned_by_queue((v,)) is True
    assert should_block_for_upstream((v,)) is True


def test_tv_sparse_missing_series_uses_top_level_title_for_anchor() -> None:
    """No ``series`` object: release title still feeds the anchor."""
    row = {
        "status": "failed",
        "title": "Limited.Series.2024.1080p",
    }
    v = map_queue_row_to_refiner_view(row, TV_QUEUE_DIALECT)
    assert v.applies_to_file is False
    assert v.queue_title == "Limited.Series.2024.1080p"
    assert v.queue_year is None
    cand = FileAnchorCandidate(title="Limited Series 2024")
    assert file_is_owned_by_queue((v,), file_candidate=cand) is True


def test_tv_dialect_ignores_movie_block() -> None:
    """The TV dialect never consults ``movie``, so movie-only payloads cannot drive TV rows."""
    row = {
        "status": "completed",
        "movie": {"title": "Should Ignore", "year": 2001},
        "series": {"title": "Real Series", "year": 2018},
    }
    v = map_queue_row_to_refiner_view(row, TV_QUEUE_DIALECT)
    assert v.queue_title == "Real Series"
    assert v.queue_year == 2018


def test_mixed_scope_mapped_rows_domain_aggregation() -> None:
    """Rows from different managers, each mapped with its scope; domain stays unified."""
    movie_busy = {
        "status": "downloading",
        "outputPath": "C:/q/a.mkv",
        "title": "Alien.1979",
    }
    tv_sparse = {
        "status": "completed",
        "title": "Alien 1979 1080p",
    }
    c_busy = map_queue_row_to_refiner_view(movie_busy, MOVIE_QUEUE_DIALECT, candidate_path="c:/q/a.mkv")
    c_sparse = map_queue_row_to_refiner_view(tv_sparse, TV_QUEUE_DIALECT)
    cand = FileAnchorCandidate(title="Alien 1979")
    rows = (c_busy, c_sparse)
    assert file_is_owned_by_queue(rows, file_candidate=cand) is True
    assert should_block_for_upstream(rows, file_candidate=cand) is True


# --- neutral keys, for managers that are neither Radarr nor Sonarr -----------


def test_neutral_media_block_and_entity_id_drive_a_movie_row() -> None:
    """A manager posting the native shape needs no vendor keys."""
    row = {
        "status": "downloading",
        "entityId": 7,
        "media": {"title": "Prospect", "year": 2018},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT, candidate_entity_id=7)
    assert v.applies_to_file is True
    assert v.queue_title == "Prospect"
    assert v.queue_year == 2018
    assert v.is_upstream_active is True


def test_neutral_media_block_drives_a_tv_row() -> None:
    row = {
        "status": "queued",
        "entity_id": 11,
        "media": {"title": "Slow Horses", "year": 2022},
    }
    v = map_queue_row_to_refiner_view(row, TV_QUEUE_DIALECT, candidate_entity_id=11)
    assert v.applies_to_file is True
    assert v.queue_title == "Slow Horses"


def test_vendor_key_wins_over_neutral_key_when_both_present() -> None:
    """``movie`` is more specific than ``media``; the dialect tries it first."""
    row = {
        "status": "completed",
        "movie": {"title": "Specific", "year": 1999},
        "media": {"title": "Generic", "year": 2000},
    }
    v = map_queue_row_to_refiner_view(row, MOVIE_QUEUE_DIALECT)
    assert v.queue_title == "Specific"
    assert v.queue_year == 1999


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("movie", MOVIE_QUEUE_DIALECT),
        ("movies", MOVIE_QUEUE_DIALECT),
        ("MOVIE", MOVIE_QUEUE_DIALECT),
        ("tv", TV_QUEUE_DIALECT),
        ("series", TV_QUEUE_DIALECT),
        (" TV ", TV_QUEUE_DIALECT),
    ],
)
def test_queue_dialect_for_scope_accepts_common_spellings(scope: str, expected: object) -> None:
    assert queue_dialect_for_scope(scope) is expected


def test_queue_dialect_for_scope_rejects_unknown_scope() -> None:
    with pytest.raises(ValueError, match="Unknown media scope"):
        queue_dialect_for_scope("music")
