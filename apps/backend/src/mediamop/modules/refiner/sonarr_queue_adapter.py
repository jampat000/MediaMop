"""Sonarr queue row → :class:`RefinerQueueRowView` (TV library only).

Does not read ``movie``; applicability uses ``outputPath`` and ``seriesId`` only.
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

# Per-app set; duplicated intentionally from Radarr so either side can evolve alone.
_SONARR_STATUSES_UPSTREAM_ACTIVE: frozenset[str] = frozenset(
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


def _sonarr_queue_title_and_year(row: Mapping[str, Any]) -> tuple[str | None, int | None]:
    series = nested_dict(row, "series")
    if series is not None:
        title = first_str(series, "title", "sortTitle", "sort_title")
        year = first_int(series, "year")
        if title is not None:
            return title, year
    title = first_str(row, "title", "name")
    return title, None


def _sonarr_applies_to_file(
    row: Mapping[str, Any],
    *,
    candidate_path: str | None,
    candidate_series_id: int | None,
) -> bool:
    if path_matches_candidate(row, candidate_path):
        return True
    if candidate_series_id is not None:
        sid = first_int(row, "seriesId", "series_id")
        if sid is not None and sid == candidate_series_id:
            return True
    return False


def map_sonarr_queue_row_to_refiner_view(
    row: Mapping[str, Any],
    *,
    candidate_path: str | None = None,
    candidate_series_id: int | None = None,
) -> RefinerQueueRowView:
    """Map one Sonarr queue item dict to the Refiner domain row view.

    **applies_to_file** — ``outputPath`` matches ``candidate_path`` and/or ``seriesId``
    matches ``candidate_series_id``.

    **queue_title** / **queue_year** — from nested ``series`` when present, else
    top-level ``title`` / ``name`` (year only from ``series``).
    """
    status = primary_queue_status(row)
    is_import_pending = status == "importpending"
    is_upstream_active = status in _SONARR_STATUSES_UPSTREAM_ACTIVE and not is_import_pending
    title, year = _sonarr_queue_title_and_year(row)
    applies = _sonarr_applies_to_file(
        row,
        candidate_path=candidate_path,
        candidate_series_id=candidate_series_id,
    )
    return RefinerQueueRowView(
        applies_to_file=applies,
        is_upstream_active=is_upstream_active,
        is_import_pending=is_import_pending,
        blocking_suppressed_for_import_wait=blocking_suppressed_for_import_wait(row),
        queue_title=title,
        queue_year=year,
    )
