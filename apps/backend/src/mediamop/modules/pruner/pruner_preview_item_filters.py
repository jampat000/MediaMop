"""Shared preview-only AND checks for Jellyfin/Emby Items rows (genre, people, year, studio)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mediamop.modules.pruner.pruner_genre_filters import (
    item_matches_genre_include_filter,
    jellyfin_emby_item_genres,
)
from mediamop.modules.pruner.pruner_people_filters import (
    DEFAULT_PREVIEW_PEOPLE_ROLES,
    item_matches_people_include_filter,
    jellyfin_emby_people_names_for_roles,
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
    preview_include_people_roles: Sequence[str] | None = None,
    preview_year_min: int | None,
    preview_year_max: int | None,
    preview_include_studios: Sequence[str],
) -> bool:
    """No longer used by any active rule family. Each independent rule calls its own filter helper directly.

    Kept for test compatibility. Historically this ANDed genre, people, year, and studio include filters on
    Jellyfin/Emby ``Items`` rows.
    """

    if not item_matches_genre_include_filter(jellyfin_emby_item_genres(it), preview_include_genres):
        return False
    pf = list(preview_include_people or [])
    if pf:
        roles = list(preview_include_people_roles) if preview_include_people_roles else list(DEFAULT_PREVIEW_PEOPLE_ROLES)
        names = jellyfin_emby_people_names_for_roles(it, roles)
        if not item_matches_people_include_filter(names, pf):
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
