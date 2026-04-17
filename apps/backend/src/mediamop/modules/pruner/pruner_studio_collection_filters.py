"""Preview-only studio and collection include lists (exact normalized token match, same caps as genre filters)."""

from __future__ import annotations

import json
from typing import Any, Sequence

from mediamop.modules.pruner.pruner_genre_filters import normalized_genre_filter_tokens


def jellyfin_emby_item_studio_names(item: dict[str, Any]) -> list[str]:
    """Studio display names from Jellyfin/Emby ``Items`` ``Studios`` (``Name`` on each object)."""

    out: list[str] = []
    raw = item.get("Studios")
    if not isinstance(raw, list):
        return out
    for s in raw:
        if isinstance(s, dict):
            n = s.get("Name")
            if n is not None and str(n).strip():
                out.append(str(n).strip())
    return out


def preview_studio_filters_from_db_column(raw: str | None) -> list[str]:
    """Parse ``preview_include_studios_json``; malformed rows fail open (empty list)."""

    if raw is None or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    tokens = [x for x in data if isinstance(x, str)]
    try:
        return normalized_genre_filter_tokens(tokens)
    except ValueError:
        return []


def preview_studio_filters_to_db_column(tokens: Sequence[str] | None) -> str:
    norm = normalized_genre_filter_tokens(list(tokens) if tokens is not None else [])
    return json.dumps(norm, separators=(",", ":"))


def preview_collection_filters_from_db_column(raw: str | None) -> list[str]:
    """Parse ``preview_include_collections_json``; malformed rows fail open."""

    if raw is None or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    tokens = [x for x in data if isinstance(x, str)]
    try:
        return normalized_genre_filter_tokens(tokens)
    except ValueError:
        return []


def preview_collection_filters_to_db_column(tokens: Sequence[str] | None) -> str:
    norm = normalized_genre_filter_tokens(list(tokens) if tokens is not None else [])
    return json.dumps(norm, separators=(",", ":"))
