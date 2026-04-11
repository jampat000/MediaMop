"""Refiner module — MediaMop’s media refinement surface (movies and TV).

Download-queue failed-import cleanup **planning, drives, and *arr execution** live under
``mediamop.modules.fetcher`` (Fetcher product/runtime ownership). Shared classification and
policy toggles live in ``mediamop.modules.arr_failed_import`` (neutral *arr rules).

Refiner owns persisted ``refiner_jobs`` and optional in-process Refiner workers
(``MEDIAMOP_REFINER_WORKER_COUNT``). Durable Fetcher background work uses ``fetcher_jobs`` and
Fetcher workers instead. Composition may inject neutral ports; Refiner does not import Fetcher.

Each future durable ``refiner.*`` job family must carry **its own** operator timing settings and
persisted timing state per ``docs/adr/ADR-0009-suite-wide-timing-isolation.md`` (lane table
ownership remains ``docs/adr/ADR-0007-module-owned-worker-lanes.md``).

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
