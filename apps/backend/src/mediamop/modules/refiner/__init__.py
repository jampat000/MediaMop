"""Refiner module — MediaMop’s media refinement surface (movies and TV).

Download-queue failed-import cleanup **planning, drives, and *arr execution** use shared rules in
HTTP resolution in ``mediamop.platform.arr_library``.

Refiner owns persisted ``refiner_jobs`` and optional in-process Refiner workers
(``MEDIAMOP_REFINER_WORKER_COUNT``). Composition may inject neutral ports; Refiner stays decoupled
from other product modules at import time.

Shipped durable ``refiner.*`` families include queue evaluation, candidate gate, and
``refiner.file.remux_pass.v1`` (ffprobe + remux planning under ``mediamop.modules.refiner.refiner_remux_*``;
manual-only unless a family adds its own schedule per ADR-0009). Each scheduled family must carry **its own**
operator timing settings and persisted timing state (lane table: ADR-0007).

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
from mediamop.modules.refiner.queue_adapter import (
    MOVIE_QUEUE_DIALECT,
    TV_QUEUE_DIALECT,
    QueueDialect,
    map_queue_row_to_refiner_view,
    queue_dialect_for_scope,
)

__all__ = [
    "FileAnchorCandidate",
    "RefinerQueueRowView",
    "TitleYearAnchor",
    "extract_title_tokens_and_year",
    "extract_title_year_anchor",
    "file_is_owned_by_queue",
    "MOVIE_QUEUE_DIALECT",
    "QueueDialect",
    "TV_QUEUE_DIALECT",
    "map_queue_row_to_refiner_view",
    "queue_dialect_for_scope",
    "normalize_storage_path",
    "normalize_titleish",
    "row_owns_by_title_year_anchor",
    "should_block_for_upstream",
    "strip_packaging_tokens",
    "title_year_anchors_match",
    "tokenize_normalized",
]
