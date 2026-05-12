"""Optional per-scope people-name include filters for Pruner preview candidate collection."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from mediamop.modules.pruner.pruner_genre_filters import normalized_genre_filter_tokens

# Same caps and normalization as genre filters (full person name per token; case-insensitive exact match).

PRUNER_PEOPLE_ROLE_CAST = "cast"
PRUNER_PEOPLE_ROLE_DIRECTOR = "director"
PRUNER_PEOPLE_ROLE_WRITER = "writer"
PRUNER_PEOPLE_ROLE_PRODUCER = "producer"
PRUNER_PEOPLE_ROLE_GUEST_STAR = "guest_star"

VALID_PRUNER_PREVIEW_PEOPLE_ROLES: frozenset[str] = frozenset(
    {
        PRUNER_PEOPLE_ROLE_CAST,
        PRUNER_PEOPLE_ROLE_DIRECTOR,
        PRUNER_PEOPLE_ROLE_WRITER,
        PRUNER_PEOPLE_ROLE_PRODUCER,
        PRUNER_PEOPLE_ROLE_GUEST_STAR,
    },
)

PRUNER_PREVIEW_PEOPLE_ROLES_ORDER: tuple[str, ...] = (
    PRUNER_PEOPLE_ROLE_CAST,
    PRUNER_PEOPLE_ROLE_DIRECTOR,
    PRUNER_PEOPLE_ROLE_WRITER,
    PRUNER_PEOPLE_ROLE_PRODUCER,
    PRUNER_PEOPLE_ROLE_GUEST_STAR,
)

DEFAULT_PREVIEW_PEOPLE_ROLES: list[str] = []

_JF_EMBY_TYPE_TO_ROLE: dict[str, str] = {
    "actor": PRUNER_PEOPLE_ROLE_CAST,
    "director": PRUNER_PEOPLE_ROLE_DIRECTOR,
    "writer": PRUNER_PEOPLE_ROLE_WRITER,
    "producer": PRUNER_PEOPLE_ROLE_PRODUCER,
    "gueststar": PRUNER_PEOPLE_ROLE_GUEST_STAR,
}


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


def validate_preview_people_roles_list(tokens: Sequence[object] | None) -> list[str]:
    """Strict role strings; dedupe preserving canonical order; null or all-empty -> []."""

    if tokens is None:
        return []
    if not isinstance(tokens, list):
        msg = "preview_include_people_roles must be a list of strings or null"
        raise ValueError(msg)
    out: list[str] = []
    seen: set[str] = set()
    for x in tokens:
        if x is None:
            continue
        r = str(x).strip().lower()
        if not r:
            continue
        if r not in VALID_PRUNER_PREVIEW_PEOPLE_ROLES:
            msg = f"Invalid people role: {x!r}"
            raise ValueError(msg)
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    if not out:
        return []
    return sorted(out, key=lambda z: PRUNER_PREVIEW_PEOPLE_ROLES_ORDER.index(z))


def preview_people_roles_from_db_column(raw: str | None) -> list[str]:
    """Parse ``preview_include_people_roles_json`` — malformed or empty becomes ``[]``."""

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
        norm = validate_preview_people_roles_list(tokens)
    except ValueError:
        return []
    return norm


def preview_people_roles_to_db_column(tokens: Sequence[str] | None) -> str:
    norm = validate_preview_people_roles_list(list(tokens) if tokens is not None else None)
    return json.dumps(norm, separators=(",", ":"))


def jellyfin_emby_person_role_from_type(type_raw: Any) -> str | None:
    """Map Jellyfin/Emby ``People[].Type`` to wire role token; missing type → cast (legacy rows)."""

    t = str(type_raw or "").strip().casefold()
    if not t:
        return PRUNER_PEOPLE_ROLE_CAST
    return _JF_EMBY_TYPE_TO_ROLE.get(t)


def jellyfin_emby_people_names_for_roles(item: dict[str, Any], roles: Sequence[str]) -> list[str]:
    """Names from ``People`` entries whose ``Type`` maps to one of ``roles``."""

    want = {str(x).strip().lower() for x in roles if str(x).strip()}
    if not want:
        return []
    out: list[str] = []
    raw = item.get("People")
    if not isinstance(raw, list):
        return out
    for p in raw:
        if not isinstance(p, dict):
            continue
        mapped = jellyfin_emby_person_role_from_type(p.get("Type"))
        if mapped is None or mapped not in want:
            continue
        name = p.get("Name")
        if name is not None and str(name).strip():
            out.append(str(name).strip())
    return out


def jellyfin_emby_item_people_names(item: dict[str, Any]) -> list[str]:
    """Person display names from Jellyfin/Emby Items ``People`` (any role; legacy helper / tests)."""

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


def _plex_extract_tag_strings(raw: Any) -> list[str]:
    out: list[str] = []
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


def plex_leaf_person_tags_for_roles(meta: dict[str, Any], roles: Sequence[str]) -> list[str]:
    """Person-like strings from Plex leaf metadata for configured roles only (producer/guest_star ignored on Plex)."""

    want = {str(x).strip().lower() for x in roles if str(x).strip()}
    if not want:
        return []
    out: list[str] = []
    if PRUNER_PEOPLE_ROLE_CAST in want:
        out.extend(_plex_extract_tag_strings(meta.get("Role")))
    if PRUNER_PEOPLE_ROLE_DIRECTOR in want:
        out.extend(_plex_extract_tag_strings(meta.get("Director")))
    if PRUNER_PEOPLE_ROLE_WRITER in want:
        out.extend(_plex_extract_tag_strings(meta.get("Writer")))
    return out


def plex_leaf_person_tags(meta: dict[str, Any]) -> list[str]:
    """Person-like display strings from Plex leaf ``Role``, ``Writer``, and ``Director`` tag lists (name-only)."""

    return plex_leaf_person_tags_for_roles(
        meta,
        (PRUNER_PEOPLE_ROLE_CAST, PRUNER_PEOPLE_ROLE_DIRECTOR, PRUNER_PEOPLE_ROLE_WRITER),
    )


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
    return any(str(n).casefold() in fl for n in item_people)
