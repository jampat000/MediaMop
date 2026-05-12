"""Radarr queue row → :class:`RefinerQueueRowView` (movie library only).

Does not read ``series``; applicability uses ``outputPath`` and ``movieId`` only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mediamop.modules.refiner.arr_queue_plumbing import (
    blocking_suppressed_for_import_wait,
    first_int,
    first_str,
    nested_dict,
    path_matches_candidate,
    primary_queue_status,
)
from mediamop.modules.refiner.domain import RefinerQueueRowView

# Per-app set so movie vs TV queue semantics can diverge without cross-coupling.
_RADARR_STATUSES_UPSTREAM_ACTIVE: frozenset[str] = frozenset(
    {
        "downloading",
        "queued",
        "paused",
        "delay",
        "downloadpending",
        "downloadclientunavailable",
        "warning",
    }
)


def _radarr_queue_title_and_year(row: Mapping[str, Any]) -> tuple[str | None, int | None]:
    movie = nested_dict(row, "movie")
    if movie is not None:
        title = first_str(movie, "title", "originalTitle", "original_title")
        year = first_int(movie, "year")
        if title is not None:
            return title, year
    title = first_str(row, "title", "name")
    return title, None


def _radarr_applies_to_file(
    row: Mapping[str, Any],
    *,
    candidate_path: str | None,
    candidate_movie_id: int | None,
) -> bool:
    if path_matches_candidate(row, candidate_path):
        return True
    if candidate_movie_id is not None:
        mid = first_int(row, "movieId", "movie_id")
        if mid is not None and mid == candidate_movie_id:
            return True
    return False


def map_radarr_queue_row_to_refiner_view(
    row: Mapping[str, Any],
    *,
    candidate_path: str | None = None,
    candidate_movie_id: int | None = None,
) -> RefinerQueueRowView:
    """Map one Radarr queue item dict to the Refiner domain row view.

    **applies_to_file** — ``outputPath`` matches ``candidate_path`` and/or ``movieId``
    matches ``candidate_movie_id``.

    **queue_title** / **queue_year** — from nested ``movie`` when present, else
    top-level ``title`` / ``name`` (year only from ``movie``).

    Status / blocking-extension fields match :func:`map_sonarr_queue_row_to_refiner_view`
    in behavior for equivalent queue states (each app carries its own active-status set).
    """
    status = primary_queue_status(row)
    is_import_pending = status == "importpending"
    is_upstream_active = status in _RADARR_STATUSES_UPSTREAM_ACTIVE and not is_import_pending
    title, year = _radarr_queue_title_and_year(row)
    applies = _radarr_applies_to_file(
        row,
        candidate_path=candidate_path,
        candidate_movie_id=candidate_movie_id,
    )
    return RefinerQueueRowView(
        applies_to_file=applies,
        is_upstream_active=is_upstream_active,
        is_import_pending=is_import_pending,
        blocking_suppressed_for_import_wait=blocking_suppressed_for_import_wait(row),
        queue_title=title,
        queue_year=year,
    )
