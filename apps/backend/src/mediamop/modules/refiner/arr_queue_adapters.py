"""Thin mapping from *arr queue API payloads to :class:`RefinerQueueRowView`.

No HTTP, no orchestration: callers fetch JSON elsewhere and pass each row dict here.

Field names follow Radarr/Sonarr v3-style JSON (camelCase). Optional MediaMop-local
extensions (same dict) are read when present so higher layers can attach policy
without mutating upstream objects in memory.
"""

from __future__ import annotations

from typing import Any, Mapping

from mediamop.modules.refiner.domain import RefinerQueueRowView

# Status values (case-insensitive) observed on Radarr/Sonarr queue resources.
_STATUSES_UPSTREAM_ACTIVE: frozenset[str] = frozenset(
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


def normalize_storage_path(path: str) -> str:
    """Normalize paths for equality (case-insensitive, forward slashes)."""
    return path.replace("\\", "/").strip().lower()


def _first_str(row: Mapping[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _first_int(row: Mapping[str, Any], *keys: str) -> int | None:
    for k in keys:
        v = row.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
    return None


def _nested_dict(row: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    v = row.get(key)
    return v if isinstance(v, dict) else None


def _primary_status(row: Mapping[str, Any]) -> str:
    for k in ("status", "trackedDownloadStatus", "trackedDownloadState"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _output_path(row: Mapping[str, Any]) -> str | None:
    return _first_str(row, "outputPath", "output_path")


def _path_applies(row: Mapping[str, Any], candidate_path: str | None) -> bool:
    if candidate_path is None:
        return False
    out = _output_path(row)
    if out is None:
        return False
    return normalize_storage_path(out) == normalize_storage_path(candidate_path)


def _id_applies(row: Mapping[str, Any], *, movie_id: int | None, series_id: int | None) -> bool:
    if movie_id is not None:
        mid = _first_int(row, "movieId", "movie_id")
        if mid is not None and mid == movie_id:
            return True
    if series_id is not None:
        sid = _first_int(row, "seriesId", "series_id")
        if sid is not None and sid == series_id:
            return True
    return False


def _queue_title_and_year(row: Mapping[str, Any]) -> tuple[str | None, int | None]:
    movie = _nested_dict(row, "movie")
    if movie is not None:
        title = _first_str(movie, "title", "originalTitle", "original_title")
        year = _first_int(movie, "year")
        if title is not None:
            return title, year
    series = _nested_dict(row, "series")
    if series is not None:
        title = _first_str(series, "title", "sortTitle", "sort_title")
        year = _first_int(series, "year")
        if title is not None:
            return title, year
    title = _first_str(row, "title", "name")
    return title, None


def _blocking_suppressed(row: Mapping[str, Any]) -> bool:
    for k in (
        "blockingSuppressedForImportWait",
        "blocking_suppressed_for_import_wait",
        "mediamopBlockingSuppressedForImportWait",
    ):
        v = row.get(k)
        if isinstance(v, bool):
            return v
    return False


def map_arr_queue_row_to_refiner_view(
    row: Mapping[str, Any],
    *,
    candidate_path: str | None = None,
    candidate_movie_id: int | None = None,
    candidate_series_id: int | None = None,
) -> RefinerQueueRowView:
    """Map one *arr queue item dict to the Refiner domain row view.

    **applies_to_file** — True when the row is explicitly tied to the candidate:
    - ``outputPath`` (or ``output_path``) equals ``candidate_path`` after
      :func:`normalize_storage_path`, and/or
    - ``movieId`` equals ``candidate_movie_id``, and/or
    - ``seriesId`` equals ``candidate_series_id`` (Sonarr).

    **queue_title** / **queue_year** — from nested ``movie`` or ``series`` when
    present, else top-level ``title`` / ``name`` with year from movie/series only.

    **is_import_pending** — primary ``status`` (or tracked download fields) is
    ``importpending`` (case-insensitive).

    **is_upstream_active** — status is one of the in-flight queue states
    (downloading, queued, paused, delay, etc.); never derived from import-pending
    alone. Import-pending rows are treated as not upstream-active for blocking.

    **blocking_suppressed_for_import_wait** — optional booleans
    ``blockingSuppressedForImportWait`` or ``blocking_suppressed_for_import_wait``
    on the same dict (or ``mediamopBlockingSuppressedForImportWait`` for tests).
    """
    status = _primary_status(row)
    is_import_pending = status == "importpending"
    is_upstream_active = status in _STATUSES_UPSTREAM_ACTIVE and not is_import_pending
    title, year = _queue_title_and_year(row)
    applies = _path_applies(row, candidate_path) or _id_applies(
        row,
        movie_id=candidate_movie_id,
        series_id=candidate_series_id,
    )
    return RefinerQueueRowView(
        applies_to_file=applies,
        is_upstream_active=is_upstream_active,
        is_import_pending=is_import_pending,
        blocking_suppressed_for_import_wait=_blocking_suppressed(row),
        queue_title=title,
        queue_year=year,
    )
