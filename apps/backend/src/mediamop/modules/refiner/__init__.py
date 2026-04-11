"""Refiner module — MediaMop’s media refinement surface (movies and TV).

Download-queue failed-import cleanup **planning, drives, and *arr execution** live under
``mediamop.modules.fetcher`` (Fetcher product/runtime ownership). Shared classification and
policy toggles live in ``mediamop.modules.arr_failed_import`` (neutral *arr rules).

Refiner still runs persisted ``refiner_jobs`` workers and periodic enqueue tasks; composition
injects Fetcher ports without Refiner importing ``mediamop.modules.fetcher``.

Radarr and Sonarr stay in separate Python modules wherever behavior can diverge.
"""

from __future__ import annotations

from mediamop.modules.refiner.arr_queue_plumbing import normalize_storage_path
from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    TitleYearAnchor,
    extract_title_tokens_and_year,
    extract_title_year_anchor,
    file_is_owned_by_queue,
    normalize_titleish,
    row_owns_by_title_year_anchor,
    should_block_for_upstream,
    strip_packaging_tokens,
    title_year_anchors_match,
    tokenize_normalized,
)
from mediamop.modules.refiner.radarr_queue_adapter import map_radarr_queue_row_to_refiner_view
from mediamop.modules.refiner.sonarr_queue_adapter import map_sonarr_queue_row_to_refiner_view

__all__ = [
    "FileAnchorCandidate",
    "RefinerQueueRowView",
    "TitleYearAnchor",
    "extract_title_tokens_and_year",
    "extract_title_year_anchor",
    "file_is_owned_by_queue",
    "map_radarr_queue_row_to_refiner_view",
    "map_sonarr_queue_row_to_refiner_view",
    "normalize_storage_path",
    "normalize_titleish",
    "row_owns_by_title_year_anchor",
    "should_block_for_upstream",
    "strip_packaging_tokens",
    "title_year_anchors_match",
    "tokenize_normalized",
]
