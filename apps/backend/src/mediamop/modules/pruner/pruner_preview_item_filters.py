"""Shared preview-only AND checks for Jellyfin/Emby Items rows (genre, people, year, studio)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mediamop.modules.pruner.pruner_genre_filters import (
    item_matches_genre_include_filter,
    jellyfin_emby_item_genres,
)
from mediamop.modules.pruner.pruner_people_filters import (
    item_matches_people_include_filter,
    jellyfin_emby_item_people_names,
)
from mediamop.modules.pruner.pruner_preview_year_filters import (
    item_matches_preview_year_filter,
    jellyfin_emby_item_production_year_int,
)
from mediamop.modules.pruner.pruner_studio_collection_filters import jellyfin_emby_item_studio_names


def jf_emby_item_passes_preview_filters(
    it: dict[str, Any],
    *,
    preview_include_genres: Sequence[str],
    preview_include_people: Sequence[str],
    preview_year_min: int | None,
    preview_year_max: int | None,
    preview_include_studios: Sequence[str],
) -> bool:
    """AND across active preview-only include filters (missing year fails when year filter active)."""

    if not item_matches_genre_include_filter(jellyfin_emby_item_genres(it), preview_include_genres):
        return False
    if not item_matches_people_include_filter(jellyfin_emby_item_people_names(it), preview_include_people):
        return False
    if not item_matches_preview_year_filter(
        jellyfin_emby_item_production_year_int(it),
        preview_year_min,
        preview_year_max,
    ):
        return False
    if not item_matches_genre_include_filter(jellyfin_emby_item_studio_names(it), preview_include_studios):
        return False
    return True
