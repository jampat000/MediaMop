"""Refiner module — domain and future product surface.

Pass 1–2: pure ownership/blocking and anchors. Pass 3: thin *arr queue adapters;
no HTTP clients or orchestration here.
"""

from __future__ import annotations

from mediamop.modules.refiner.arr_queue_adapters import (
    map_arr_queue_row_to_refiner_view,
    normalize_storage_path,
)
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

__all__ = [
    "FileAnchorCandidate",
    "map_arr_queue_row_to_refiner_view",
    "normalize_storage_path",
    "RefinerQueueRowView",
    "TitleYearAnchor",
    "extract_title_tokens_and_year",
    "extract_title_year_anchor",
    "file_is_owned_by_queue",
    "normalize_titleish",
    "row_owns_by_title_year_anchor",
    "should_block_for_upstream",
    "strip_packaging_tokens",
    "title_year_anchors_match",
    "tokenize_normalized",
]
