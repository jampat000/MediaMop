"""Refiner — the Weir application: media refinement for movies and TV.

Refiner never talks to a product. It asks the media manager port in
``weir.platform.media_managers`` which managers look after a media scope, and asks all
of them what they are importing and which files they still keep (ADR-0013).

Refiner owns persisted ``refiner_jobs`` and optional in-process Refiner workers
(``WEIR_REFINER_WORKER_COUNT``). Composition may inject neutral ports.

Shipped durable ``refiner.*`` families include queue evaluation, candidate gate, and
``refiner.file.remux_pass.v1`` (ffprobe + remux planning under ``weir.refiner.refiner_remux_*``;
manual-only unless a family adds its own schedule per ADR-0009). Each scheduled family must carry **its own**
operator timing settings and persisted timing state (ADR-0009).
"""

from __future__ import annotations

from weir.refiner.domain import (
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
from weir.refiner.queue_adapter import (
    MOVIE_QUEUE_DIALECT,
    TV_QUEUE_DIALECT,
    QueueDialect,
    map_queue_row_to_refiner_view,
    queue_dialect_for_scope,
)
from weir.refiner.queue_row_plumbing import normalize_storage_path

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
