"""Plex **preview-only** candidate collection for ``missing_primary_media_reported`` (no apply, no live removal).

This module is **not** a live-removal or apply path: it only performs read-only HTTP calls to build the candidate list
stored in ``pruner_preview_runs``. Apply uses ``pruner_plex_library_delete`` against frozen ``ratingKey`` values from
that snapshot.

**Provider-specific semantics (Plex):** candidates are **episode** (TV scope) or **movie** (Movies scope) leaf
``Video`` rows where the Plex JSON object has **no non-empty ``thumb``** on that leaf. This is **not** the same
signal as Jellyfin/Emby ``HasPrimaryImage=false`` + primary tag checks; operator copy must not equate them.

Optional **people** filters (preview-only) match **Role**, **Writer**, and **Director** ``tag`` strings on each leaf
metadata object returned by ``allLeaves`` — no richer credit graph in this slice.

Read-only calls: ``GET /library/sections`` and paged ``GET /library/sections/{key}/allLeaves``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES, MEDIA_SCOPE_TV
from mediamop.modules.pruner.pruner_genre_filters import item_matches_genre_include_filter, plex_leaf_genre_tags
from mediamop.modules.pruner.pruner_people_filters import (
    item_matches_people_include_filter,
    plex_leaf_person_tags,
)
from mediamop.modules.pruner.pruner_http import http_get_json, join_base_path


def _plex_headers(auth_token: str) -> dict[str, str]:
    return {"Accept": "application/json", "X-Plex-Token": auth_token}


def _as_list(x: Any) -> list[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _media_container(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict) and isinstance(obj.get("MediaContainer"), dict):
        return obj["MediaContainer"]
    if isinstance(obj, dict):
        return obj
    return {}


def _section_matches_scope(section_type: Any, media_scope: str) -> bool:
    raw = str(section_type).strip().lower()
    if media_scope == MEDIA_SCOPE_MOVIES:
        return raw in ("movie", "1") or section_type == 1
    if media_scope == MEDIA_SCOPE_TV:
        return raw in ("show", "2") or section_type == 2
    return False


def _leaf_type_matches(meta: dict[str, Any], media_scope: str) -> bool:
    t = str(meta.get("type", "")).strip().lower()
    if media_scope == MEDIA_SCOPE_MOVIES:
        return t == "movie"
    if media_scope == MEDIA_SCOPE_TV:
        return t == "episode"
    return False


def _plex_leaf_missing_thumb(meta: dict[str, Any]) -> bool:
    thumb = meta.get("thumb")
    if thumb is None:
        return True
    if isinstance(thumb, str) and not thumb.strip():
        return True
    return False


def _rating_key(meta: dict[str, Any]) -> str:
    rk = meta.get("ratingKey")
    if rk is None:
        return ""
    return str(rk).strip()


def list_plex_missing_thumb_candidates(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_items: int,
    preview_include_genres: Sequence[str] | None = None,
    preview_include_people: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return up to ``max_items`` Plex leaf metadata dicts (``ratingKey`` as ``item_id``) plus ``truncated``.

    ``truncated`` is True when more matching leaves likely exist beyond the returned rows (same cap semantics as
    Jellyfin/Emby preview listers).
    """

    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)
    cap = max(0, int(max_items))
    if cap == 0:
        return [], False

    gf = list(preview_include_genres or [])
    pf = list(preview_include_people or [])

    sections_url = join_base_path(base_url, "library/sections")
    status, data = http_get_json(sections_url, headers=_plex_headers(auth_token))
    if status != 200:
        msg = f"Plex library/sections failed HTTP {status}"
        raise RuntimeError(msg)

    container = _media_container(data)
    directories = _as_list(container.get("Directory"))
    section_keys: list[str] = []
    for d in directories:
        if not isinstance(d, dict):
            continue
        if not _section_matches_scope(d.get("type"), media_scope):
            continue
        key = d.get("key")
        if key is None:
            continue
        section_keys.append(str(key).strip())
        if not section_keys[-1]:
            section_keys.pop()

    out: list[dict[str, Any]] = []
    truncated = False
    any_skipped_thumb_ok_for_genre = False
    page_size = min(200, max(1, cap))
    for sec_idx, sec_key in enumerate(section_keys):
        if len(out) >= cap:
            break
        start = 0
        while len(out) < cap:
            params: dict[str, str] = {
                "X-Plex-Container-Start": str(start),
                "X-Plex-Container-Size": str(page_size),
            }
            leaves_url = join_base_path(base_url, f"library/sections/{sec_key}/allLeaves", params)
            st, page = http_get_json(leaves_url, headers=_plex_headers(auth_token))
            if st != 200:
                msg = f"Plex allLeaves failed HTTP {st} (section={sec_key})"
                raise RuntimeError(msg)
            mc = _media_container(page)
            metas = _as_list(mc.get("Metadata"))
            if not metas:
                break
            stop_after_page = False
            page_skipped_thumb_ok_for_genre = False
            for meta_idx, m in enumerate(metas):
                if not isinstance(m, dict):
                    continue
                if not _leaf_type_matches(m, media_scope):
                    continue
                if not _plex_leaf_missing_thumb(m):
                    continue
                if gf and not item_matches_genre_include_filter(plex_leaf_genre_tags(m), gf):
                    page_skipped_thumb_ok_for_genre = True
                    any_skipped_thumb_ok_for_genre = True
                    continue
                if pf and not item_matches_people_include_filter(plex_leaf_person_tags(m), pf):
                    page_skipped_thumb_ok_for_genre = True
                    any_skipped_thumb_ok_for_genre = True
                    continue
                rk = _rating_key(m)
                if not rk:
                    continue
                if media_scope == MEDIA_SCOPE_TV:
                    out.append(
                        {
                            "granularity": "episode",
                            "item_id": rk,
                            "series_name": m.get("grandparentTitle") or m.get("parentTitle") or "",
                            "season_number": m.get("parentIndex"),
                            "episode_number": m.get("index"),
                            "episode_title": m.get("title") or "",
                        },
                    )
                else:
                    out.append(
                        {
                            "granularity": "movie_item",
                            "item_id": rk,
                            "title": m.get("title") or "",
                            "year": m.get("year"),
                        },
                    )
                if len(out) >= cap:
                    if meta_idx < len(metas) - 1 or page_skipped_thumb_ok_for_genre:
                        truncated = True
                    stop_after_page = True
                    break
            total = mc.get("totalSize")
            try:
                total_i = int(total) if total is not None else start + len(metas)
            except (TypeError, ValueError):
                total_i = start + len(metas)
            start += len(metas)
            if stop_after_page:
                if start < total_i:
                    truncated = True
                elif sec_idx < len(section_keys) - 1:
                    truncated = True
                elif any_skipped_thumb_ok_for_genre:
                    truncated = True
                break
            if start >= total_i or len(metas) == 0:
                break

    return out[:cap], truncated
