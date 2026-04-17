"""Preview-only year narrowing using explicit provider year fields (no title parsing)."""

from __future__ import annotations

from typing import Any


def jellyfin_emby_item_production_year_int(item: dict[str, Any]) -> int | None:
    """Jellyfin/Emby library ``Items`` row: ``ProductionYear`` when present as an integer."""

    y = item.get("ProductionYear")
    if isinstance(y, bool):
        return None
    if isinstance(y, int):
        return int(y)
    return None


def plex_leaf_release_year_int(meta: dict[str, Any]) -> int | None:
    """Plex ``allLeaves`` leaf ``Metadata``: numeric ``year`` when the server exposes it on that row."""

    y = meta.get("year")
    if isinstance(y, bool):
        return None
    if isinstance(y, int):
        return int(y)
    if isinstance(y, str) and y.strip().isdigit():
        return int(y.strip())
    return None


def item_matches_preview_year_filter(
    year: int | None,
    year_min: int | None,
    year_max: int | None,
) -> bool:
    """Inclusive range on ``year``; inactive when both bounds unset. Missing year never matches an active filter."""

    if year_min is None and year_max is None:
        return True
    if year is None:
        return False
    if year_min is not None and year < year_min:
        return False
    if year_max is not None and year > year_max:
        return False
    return True
