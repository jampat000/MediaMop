"""Read-only distinct studio names from a live library (Pruner UI dropdown)."""

from __future__ import annotations

import time
import urllib.error
from typing import Any

from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES, MEDIA_SCOPE_TV
from mediamop.modules.pruner.pruner_genre_filters import plex_leaf_studio_tags
from mediamop.modules.pruner.pruner_http import http_get_json, join_base_path
from mediamop.modules.pruner.pruner_plex_missing_thumb_candidates import (
    _as_list,
    _leaf_type_matches,
    _media_container,
    _plex_headers,
    _section_matches_scope,
)
from mediamop.modules.pruner.pruner_studio_collection_filters import jellyfin_emby_item_studio_names

_STUDIO_LIST_WALL_SEC = 10.0
_STUDIO_PAGE_LIMIT = 200


def _jf_emby_headers(api_key: str) -> dict[str, str]:
    return {"X-Emby-Token": api_key, "Accept": "application/json"}


def _sort_cap_studios(by_casefold: dict[str, str], *, max_studios: int) -> list[str]:
    names = sorted(by_casefold.values(), key=lambda s: s.casefold())
    return names[: max(0, int(max_studios))]


def _list_distinct_studios_jellyfin_emby(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_studios: int,
) -> list[str]:
    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        return []

    by_fold: dict[str, str] = {}
    start = 0
    t0 = time.monotonic()

    while len(by_fold) < max_studios:
        if time.monotonic() - t0 >= _STUDIO_LIST_WALL_SEC:
            return []
        remaining = max(0.25, _STUDIO_LIST_WALL_SEC - (time.monotonic() - t0))
        params: dict[str, str] = {
            "Recursive": "true",
            "IncludeItemTypes": include_types,
            "StartIndex": str(start),
            "Limit": str(_STUDIO_PAGE_LIMIT),
            "Fields": "Studios",
        }
        url = join_base_path(base_url, "Items", params)
        try:
            status, data = http_get_json(url, headers=_jf_emby_headers(api_key), timeout_sec=min(10.0, remaining))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
            return []
        except Exception:  # noqa: BLE001 — fail open for UI list
            return []
        if status != 200 or not isinstance(data, dict):
            return []
        items = data.get("Items")
        if not isinstance(items, list):
            return []
        if len(items) == 0:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            for name in jellyfin_emby_item_studio_names(item):
                key = name.casefold()
                if key not in by_fold:
                    by_fold[key] = name
                    if len(by_fold) >= max_studios:
                        return _sort_cap_studios(by_fold, max_studios=max_studios)
        total = data.get("TotalRecordCount")
        try:
            total_i = int(total) if total is not None else start + len(items)
        except (TypeError, ValueError):
            total_i = start + len(items)
        start += len(items)
        if start >= total_i or len(items) == 0:
            break

    return _sort_cap_studios(by_fold, max_studios=max_studios)


def _list_distinct_studios_plex(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_studios: int,
) -> list[str]:
    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        return []

    t0 = time.monotonic()
    try:
        remaining0 = max(0.25, _STUDIO_LIST_WALL_SEC - (time.monotonic() - t0))
        sections_url = join_base_path(base_url, "library/sections")
        status, data = http_get_json(sections_url, headers=_plex_headers(auth_token), timeout_sec=min(10.0, remaining0))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
        return []
    except Exception:  # noqa: BLE001
        return []
    if status != 200:
        return []

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
        sk = str(key).strip()
        if sk:
            section_keys.append(sk)

    by_fold: dict[str, str] = {}
    page_size = _STUDIO_PAGE_LIMIT

    for sec_key in section_keys:
        if len(by_fold) >= max_studios:
            break
        if time.monotonic() - t0 >= _STUDIO_LIST_WALL_SEC:
            return []
        start = 0
        while len(by_fold) < max_studios:
            if time.monotonic() - t0 >= _STUDIO_LIST_WALL_SEC:
                return []
            remaining = max(0.25, _STUDIO_LIST_WALL_SEC - (time.monotonic() - t0))
            params: dict[str, str] = {
                "X-Plex-Container-Start": str(start),
                "X-Plex-Container-Size": str(page_size),
            }
            leaves_url = join_base_path(base_url, f"library/sections/{sec_key}/allLeaves", params)
            try:
                st, page = http_get_json(leaves_url, headers=_plex_headers(auth_token), timeout_sec=min(10.0, remaining))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
                return []
            except Exception:  # noqa: BLE001
                return []
            if st != 200:
                return []
            mc = _media_container(page)
            metas = _as_list(mc.get("Metadata"))
            if not metas:
                break
            for m in metas:
                if not isinstance(m, dict):
                    continue
                if not _leaf_type_matches(m, media_scope):
                    continue
                for name in plex_leaf_studio_tags(m):
                    key = name.casefold()
                    if key not in by_fold:
                        by_fold[key] = name
                        if len(by_fold) >= max_studios:
                            return _sort_cap_studios(by_fold, max_studios=max_studios)
            total = mc.get("totalSize")
            try:
                total_i = int(total) if total is not None else start + len(metas)
            except (TypeError, ValueError):
                total_i = start + len(metas)
            start += len(metas)
            if start >= total_i or len(metas) == 0:
                break

    return _sort_cap_studios(by_fold, max_studios=max_studios)


def list_distinct_studios(
    *,
    provider: str,
    base_url: str,
    secrets: dict[str, str],
    media_scope: str,
    max_studios: int = 500,
) -> list[str]:
    """Return sorted studio display names (deduped case-insensitively), capped at ``max_studios``.

    On any failure, timeout, or unsupported input, returns an empty list.
    """

    try:
        cap = max(0, int(max_studios))
    except (TypeError, ValueError):
        cap = 500
    if cap == 0:
        return []

    prov = str(provider).strip().lower()
    url = str(base_url).strip()
    if not url:
        return []

    try:
        if prov in ("emby", "jellyfin"):
            key = secrets.get("api_key") or ""
            if not str(key).strip():
                return []
            return _list_distinct_studios_jellyfin_emby(
                base_url=url,
                api_key=str(key).strip(),
                media_scope=media_scope,
                max_studios=cap,
            )
        if prov == "plex":
            token = secrets.get("auth_token") or secrets.get("plex_token") or ""
            if not str(token).strip():
                return []
            return _list_distinct_studios_plex(
                base_url=url,
                auth_token=str(token).strip(),
                media_scope=media_scope,
                max_studios=cap,
            )
    except Exception:  # noqa: BLE001
        return []
    return []

