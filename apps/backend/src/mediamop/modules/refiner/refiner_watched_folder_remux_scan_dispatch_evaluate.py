"""Combine Radarr + Sonarr queue rows and apply Refiner domain ownership / blocking (no duplicate rules)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    should_block_for_upstream,
)
from mediamop.modules.refiner.radarr_queue_adapter import map_radarr_queue_row_to_refiner_view
from mediamop.modules.refiner.refiner_candidate_gate_queue_fetch import fetch_arr_v3_queue_rows
from mediamop.modules.refiner.sonarr_queue_adapter import map_sonarr_queue_row_to_refiner_view
from mediamop.platform.arr_library import resolve_radarr_http_credentials, resolve_sonarr_http_credentials

Verdict = Literal["proceed", "wait_upstream", "not_held"]


def merge_queue_views_for_watched_file(
    *,
    radarr_rows: Sequence[Mapping[str, Any]],
    sonarr_rows: Sequence[Mapping[str, Any]],
    file_path: Path,
) -> list[RefinerQueueRowView]:
    abs_path = str(file_path.resolve())
    views: list[RefinerQueueRowView] = []
    for row in radarr_rows:
        views.append(
            map_radarr_queue_row_to_refiner_view(row, candidate_path=abs_path, candidate_movie_id=None),
        )
    for row in sonarr_rows:
        views.append(
            map_sonarr_queue_row_to_refiner_view(row, candidate_path=abs_path, candidate_series_id=None),
        )
    return views


def verdict_for_watched_scan_file(views: Sequence[RefinerQueueRowView], *, candidate: FileAnchorCandidate) -> Verdict:
    """Decide whether a watched-folder file can be processed.

    Radarr/Sonarr are safety signals only. Refiner must still process files when
    those apps are not configured, or when the file is not currently in their
    active queue.
    """

    if should_block_for_upstream(views, file_candidate=candidate):
        return "wait_upstream"
    return "proceed"


def fetch_radarr_and_sonarr_queue_rows_for_scan(
    session: Session,
    settings: MediaMopSettings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None, str | None]:
    """Return ``(radarr_rows, sonarr_rows, radarr_error, sonarr_error)``.

    Missing credentials or HTTP failures yield empty rows plus optional operator-facing error text.
    """

    rad_err: str | None = None
    son_err: str | None = None
    rad_rows: list[dict[str, Any]] = []
    son_rows: list[dict[str, Any]] = []

    r_base, r_key = resolve_radarr_http_credentials(session, settings)
    if r_base and r_key:
        try:
            rad_rows = fetch_arr_v3_queue_rows(base_url=r_base, api_key=r_key, app="radarr")
        except RuntimeError as exc:
            rad_err = str(exc)
    else:
        rad_err = "Radarr URL/API key not configured (no queue rows loaded)."

    s_base, s_key = resolve_sonarr_http_credentials(session, settings)
    if s_base and s_key:
        try:
            son_rows = fetch_arr_v3_queue_rows(base_url=s_base, api_key=s_key, app="sonarr")
        except RuntimeError as exc:
            son_err = str(exc)
    else:
        son_err = "Sonarr URL/API key not configured (no queue rows loaded)."

    return rad_rows, son_rows, rad_err, son_err


def evaluate_watched_media_file_for_dispatch(
    *,
    radarr_rows: Sequence[Mapping[str, Any]],
    sonarr_rows: Sequence[Mapping[str, Any]],
    file_path: Path,
) -> Verdict:
    """Ownership + upstream blocking using the same :class:`RefinerQueueRowView` rules as the candidate gate."""

    views = merge_queue_views_for_watched_file(
        radarr_rows=radarr_rows,
        sonarr_rows=sonarr_rows,
        file_path=file_path,
    )
    candidate = FileAnchorCandidate(title=file_path.stem, year=None)
    return verdict_for_watched_scan_file(views, candidate=candidate)


def format_scan_summary_for_activity(summary: dict[str, Any]) -> str:
    """JSON activity detail bounded for SQLite activity rows."""

    raw = json.dumps(summary, separators=(",", ":"), ensure_ascii=True)
    return raw[:10_000]
