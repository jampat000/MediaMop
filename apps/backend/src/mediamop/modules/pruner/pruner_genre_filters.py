"""Optional per-scope genre include filters for Pruner preview candidate collection."""

from __future__ import annotations

import json
from typing import Any, Sequence

PRUNER_PREVIEW_GENRE_FILTER_MAX_TOKENS = 25
PRUNER_PREVIEW_GENRE_FILTER_MAX_TOKEN_LEN = 64


def normalized_genre_filter_tokens(raw: Sequence[str] | None) -> list[str]:
    """Trim, dedupe case-insensitively (first spelling wins), cap count and token length."""

    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        s = str(t).strip()
        if not s:
            continue
        if len(s) > PRUNER_PREVIEW_GENRE_FILTER_MAX_TOKEN_LEN:
            msg = f"each genre filter must be at most {PRUNER_PREVIEW_GENRE_FILTER_MAX_TOKEN_LEN} characters"
            raise ValueError(msg)
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) > PRUNER_PREVIEW_GENRE_FILTER_MAX_TOKENS:
            msg = f"at most {PRUNER_PREVIEW_GENRE_FILTER_MAX_TOKENS} genre filters are allowed"
            raise ValueError(msg)
    return out


def preview_genre_filters_from_db_column(raw: str | None) -> list[str]:
    """Parse stored JSON array from ``pruner_scope_settings.preview_include_genres_json``.

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
        return normalized_genre_filter_tokens(tokens)
    except ValueError:
        return []


def preview_genre_filters_to_db_column(tokens: Sequence[str] | None) -> str:
    norm = normalized_genre_filter_tokens(list(tokens) if tokens is not None else [])
    return json.dumps(norm, separators=(",", ":"))


def jellyfin_emby_item_genres(item: dict[str, Any]) -> list[str]:
    g = item.get("Genres")
    if isinstance(g, list):
        return [str(x).strip() for x in g if isinstance(x, (str, int, float)) and str(x).strip()]
    if isinstance(g, str) and g.strip():
        return [g.strip()]
    return []


def plex_leaf_named_tag_list(meta: dict[str, Any], key: str) -> list[str]:
    """Plex ``Metadata`` tag-shaped list or string for ``key`` (e.g. ``Genre``, ``Studio``, ``Collection``)."""

    out: list[str] = []
    raw = meta.get(key)
    if raw is None:
        return out
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


def plex_leaf_genre_tags(meta: dict[str, Any]) -> list[str]:
    """Genre tags from Plex ``Metadata`` JSON (``Genre`` list of ``{tag: ...}`` or strings)."""

    return plex_leaf_named_tag_list(meta, "Genre")


def plex_leaf_studio_tags(meta: dict[str, Any]) -> list[str]:
    """Studio tags from Plex leaf ``Metadata`` ``Studio`` list (same tag shape as ``Genre``)."""

    return plex_leaf_named_tag_list(meta, "Studio")


def plex_leaf_collection_tags(meta: dict[str, Any]) -> list[str]:
    """Collection tags from Plex leaf ``Metadata`` ``Collection`` list when the server exposes it."""

    return plex_leaf_named_tag_list(meta, "Collection")


def item_matches_genre_include_filter(
    item_genres: Sequence[str],
    include_filters: Sequence[str],
) -> bool:
    """True if there is no filter, or any item genre matches any filter (case-insensitive equality)."""

    if not include_filters:
        return True
    fl = {str(x).casefold() for x in include_filters if str(x).strip()}
    if not fl:
        return True
    for g in item_genres:
        if str(g).casefold() in fl:
            return True
    return False
