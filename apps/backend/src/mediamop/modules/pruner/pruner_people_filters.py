"""Optional per-scope people-name include filters for Pruner preview candidate collection."""

from __future__ import annotations

import json
from typing import Any, Sequence

from mediamop.modules.pruner.pruner_genre_filters import normalized_genre_filter_tokens

# Same caps and normalization as genre filters (full person name per token; case-insensitive exact match).


def normalized_people_filter_tokens(raw: Sequence[str] | None) -> list[str]:
    """Trim, dedupe case-insensitively, cap count and token length — same rules as genre filters."""

    return normalized_genre_filter_tokens(raw)


def preview_people_filters_from_db_column(raw: str | None) -> list[str]:
    """Parse ``pruner_scope_settings.preview_include_people_json``.

    Malformed legacy rows are treated as empty so preview jobs do not fail hard.
    """

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
        return normalized_people_filter_tokens(tokens)
    except ValueError:
        return []


def preview_people_filters_to_db_column(tokens: Sequence[str] | None) -> str:
    norm = normalized_people_filter_tokens(list(tokens) if tokens is not None else [])
    return json.dumps(norm, separators=(",", ":"))


def plex_leaf_person_tags(meta: dict[str, Any]) -> list[str]:
    """Person-like display strings from Plex leaf ``Role``, ``Writer``, and ``Director`` tag lists (name-only)."""

    out: list[str] = []
    for key in ("Role", "Writer", "Director"):
        raw = meta.get(key)
        if raw is None:
            continue
        if isinstance(raw, list):
            for g in raw:
                if isinstance(g, dict):
                    tag = g.get("tag") or g.get("Tag")
                    if tag is not None and str(tag).strip():
                        out.append(str(tag).strip())
                elif isinstance(g, str) and g.strip():
                    out.append(g.strip())
        elif isinstance(raw, dict):
            tag = raw.get("tag") or raw.get("Tag")
            if tag is not None and str(tag).strip():
                out.append(str(tag).strip())
        elif isinstance(raw, str) and raw.strip():
            out.append(raw.strip())
    return out


def jellyfin_emby_item_people_names(item: dict[str, Any]) -> list[str]:
    """Person display names from Jellyfin/Emby Items ``People`` (any role; name-only matching in this slice)."""

    out: list[str] = []
    raw = item.get("People")
    if not isinstance(raw, list):
        return out
    for p in raw:
        if not isinstance(p, dict):
            continue
        name = p.get("Name")
        if name is not None and str(name).strip():
            out.append(str(name).strip())
    return out


def item_matches_people_include_filter(
    item_people: Sequence[str],
    include_filters: Sequence[str],
) -> bool:
    """True if there is no filter, or any item person name matches any filter (case-insensitive equality)."""

    if not include_filters:
        return True
    fl = {str(x).casefold() for x in include_filters if str(x).strip()}
    if not fl:
        return True
    for n in item_people:
        if str(n).casefold() in fl:
            return True
    return False
