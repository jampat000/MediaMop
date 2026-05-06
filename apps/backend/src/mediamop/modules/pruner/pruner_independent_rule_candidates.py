"""Independent Pruner preview collectors for genre / studio / people / year rule families (JF/Emby + Plex)."""

from __future__ import annotations

import logging
import urllib.error
from collections.abc import Callable, Sequence
from typing import Any

from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES, MEDIA_SCOPE_TV
from mediamop.modules.pruner.pruner_genre_filters import (
    item_matches_genre_include_filter,
    jellyfin_emby_item_genres,
    plex_leaf_genre_tags,
    plex_leaf_studio_tags,
)
from mediamop.modules.pruner.pruner_http import http_get_json, join_base_path
from mediamop.modules.pruner.pruner_people_filters import (
    item_matches_people_include_filter,
    jellyfin_emby_item_people_names,
    jellyfin_emby_people_names_for_roles,
    plex_leaf_person_tags,
    plex_leaf_person_tags_for_roles,
)
from mediamop.modules.pruner.pruner_preview_year_filters import (
    item_matches_preview_year_filter,
    jellyfin_emby_item_production_year_int,
    plex_leaf_release_year_int,
)
from mediamop.modules.pruner.pruner_plex_missing_thumb_candidates import (
    _as_list,
    _leaf_type_matches,
    _media_container,
    _plex_headers,
    _rating_key,
    _section_matches_scope,
)
from mediamop.modules.pruner.pruner_studio_collection_filters import jellyfin_emby_item_studio_names

logger = logging.getLogger(__name__)

def _jf_emby_truncated(
    *,
    total_hits: int | None,
    start: int,
    candidates_len: int,
    max_items: int,
    fetched: int,
    page: int,
) -> bool:
    truncated = False
    if total_hits is not None and candidates_len < total_hits and candidates_len >= max_items:
        truncated = True
    elif total_hits is not None and start < total_hits and candidates_len >= max_items:
        truncated = True
    elif fetched >= page and candidates_len >= max_items:
        truncated = True
    return truncated


def list_jf_emby_genre_match_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    preview_include_genres: Sequence[str],
) -> tuple[list[dict[str, Any]], bool]:
    """Items whose genre list intersects ``preview_include_genres`` (caller must pass non-empty)."""

    from mediamop.modules.pruner.pruner_media_library import _items_page

    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)

    gf = list(preview_include_genres)
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items))
    total_hits: int | None = None
    fetched = 0

    while len(candidates) < max_items:
        try:
            data = _items_page(
                base_url=base_url,
                api_key=api_key,
                include_item_types=include_types,
                start_index=start,
                page_limit=page,
                use_has_primary_image=False,
            )
        except urllib.error.HTTPError:
            raise
        if data is None:
            raise RuntimeError("Jellyfin/Emby Items query returned no payload.")
        items = data.get("Items")
        if not isinstance(items, list):
            logger.debug("Pruner genre-match preview stopped because Jellyfin/Emby Items payload had no list.")
            break
        fetched = len(items)
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not item_matches_genre_include_filter(jellyfin_emby_item_genres(it), gf):
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
            if media_scope == MEDIA_SCOPE_TV:
                candidates.append(
                    {
                        "granularity": "episode",
                        "item_id": iid,
                        "series_name": it.get("SeriesName") or it.get("Album") or "",
                        "season_number": it.get("ParentIndexNumber"),
                        "episode_number": it.get("IndexNumber"),
                        "episode_title": it.get("Name") or "",
                    },
                )
            else:
                candidates.append(
                    {
                        "granularity": "movie_item",
                        "item_id": iid,
                        "title": it.get("Name") or "",
                        "year": it.get("ProductionYear"),
                    },
                )
            if len(candidates) >= max_items:
                break

        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            break

    truncated = _jf_emby_truncated(
        total_hits=total_hits,
        start=start,
        candidates_len=len(candidates),
        max_items=max_items,
        fetched=fetched,
        page=page,
    )
    return candidates[:max_items], truncated


def list_jf_emby_studio_match_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    preview_include_studios: Sequence[str],
) -> tuple[list[dict[str, Any]], bool]:
    """Items whose studio list intersects ``preview_include_studios`` (caller must pass non-empty)."""

    from mediamop.modules.pruner.pruner_media_library import _items_page

    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)

    sf = list(preview_include_studios)
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items))
    total_hits: int | None = None
    fetched = 0

    while len(candidates) < max_items:
        try:
            data = _items_page(
                base_url=base_url,
                api_key=api_key,
                include_item_types=include_types,
                start_index=start,
                page_limit=page,
                use_has_primary_image=False,
            )
        except urllib.error.HTTPError:
            raise
        if data is None:
            raise RuntimeError("Jellyfin/Emby Items query returned no payload.")
        items = data.get("Items")
        if not isinstance(items, list):
            logger.debug("Pruner studio-match preview stopped because Jellyfin/Emby Items payload had no list.")
            break
        fetched = len(items)
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not item_matches_genre_include_filter(jellyfin_emby_item_studio_names(it), sf):
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
            if media_scope == MEDIA_SCOPE_TV:
                candidates.append(
                    {
                        "granularity": "episode",
                        "item_id": iid,
                        "series_name": it.get("SeriesName") or it.get("Album") or "",
                        "season_number": it.get("ParentIndexNumber"),
                        "episode_number": it.get("IndexNumber"),
                        "episode_title": it.get("Name") or "",
                    },
                )
            else:
                candidates.append(
                    {
                        "granularity": "movie_item",
                        "item_id": iid,
                        "title": it.get("Name") or "",
                        "year": it.get("ProductionYear"),
                    },
                )
            if len(candidates) >= max_items:
                break

        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            break

    truncated = _jf_emby_truncated(
        total_hits=total_hits,
        start=start,
        candidates_len=len(candidates),
        max_items=max_items,
        fetched=fetched,
        page=page,
    )
    return candidates[:max_items], truncated


def list_jf_emby_people_match_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    preview_include_people: Sequence[str],
    preview_include_people_roles: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Items involving any named person in the configured roles (caller must pass non-empty people)."""

    from mediamop.modules.pruner.pruner_media_library import _items_page

    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)

    pf = list(preview_include_people)
    roles = list(preview_include_people_roles) if preview_include_people_roles is not None else []
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items))
    total_hits: int | None = None
    fetched = 0

    while len(candidates) < max_items:
        try:
            data = _items_page(
                base_url=base_url,
                api_key=api_key,
                include_item_types=include_types,
                start_index=start,
                page_limit=page,
                use_has_primary_image=False,
            )
        except urllib.error.HTTPError:
            raise
        if data is None:
            raise RuntimeError("Jellyfin/Emby Items query returned no payload.")
        items = data.get("Items")
        if not isinstance(items, list):
            logger.debug("Pruner people-match preview stopped because Jellyfin/Emby Items payload had no list.")
            break
        fetched = len(items)
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if roles:
                names = jellyfin_emby_people_names_for_roles(it, roles)
            else:
                names = jellyfin_emby_item_people_names(it)
            if not item_matches_people_include_filter(names, pf):
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
            if media_scope == MEDIA_SCOPE_TV:
                candidates.append(
                    {
                        "granularity": "episode",
                        "item_id": iid,
                        "series_name": it.get("SeriesName") or it.get("Album") or "",
                        "season_number": it.get("ParentIndexNumber"),
                        "episode_number": it.get("IndexNumber"),
                        "episode_title": it.get("Name") or "",
                    },
                )
            else:
                candidates.append(
                    {
                        "granularity": "movie_item",
                        "item_id": iid,
                        "title": it.get("Name") or "",
                        "year": it.get("ProductionYear"),
                    },
                )
            if len(candidates) >= max_items:
                break

        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            break

    truncated = _jf_emby_truncated(
        total_hits=total_hits,
        start=start,
        candidates_len=len(candidates),
        max_items=max_items,
        fetched=fetched,
        page=page,
    )
    return candidates[:max_items], truncated


def list_jf_emby_year_range_match_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    preview_year_min: int | None,
    preview_year_max: int | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Items whose ``ProductionYear`` falls in range (caller must set at least one bound)."""

    from mediamop.modules.pruner.pruner_media_library import _items_page

    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)

    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items))
    total_hits: int | None = None
    fetched = 0

    while len(candidates) < max_items:
        try:
            data = _items_page(
                base_url=base_url,
                api_key=api_key,
                include_item_types=include_types,
                start_index=start,
                page_limit=page,
                use_has_primary_image=False,
            )
        except urllib.error.HTTPError:
            raise
        if data is None:
            raise RuntimeError("Jellyfin/Emby Items query returned no payload.")
        items = data.get("Items")
        if not isinstance(items, list):
            logger.debug("Pruner year-range preview stopped because Jellyfin/Emby Items payload had no list.")
            break
        fetched = len(items)
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not item_matches_preview_year_filter(
                jellyfin_emby_item_production_year_int(it),
                preview_year_min,
                preview_year_max,
            ):
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
            if media_scope == MEDIA_SCOPE_TV:
                candidates.append(
                    {
                        "granularity": "episode",
                        "item_id": iid,
                        "series_name": it.get("SeriesName") or it.get("Album") or "",
                        "season_number": it.get("ParentIndexNumber"),
                        "episode_number": it.get("IndexNumber"),
                        "episode_title": it.get("Name") or "",
                    },
                )
            else:
                candidates.append(
                    {
                        "granularity": "movie_item",
                        "item_id": iid,
                        "title": it.get("Name") or "",
                        "year": it.get("ProductionYear"),
                    },
                )
            if len(candidates) >= max_items:
                break

        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            break

    truncated = _jf_emby_truncated(
        total_hits=total_hits,
        start=start,
        candidates_len=len(candidates),
        max_items=max_items,
        fetched=fetched,
        page=page,
    )
    return candidates[:max_items], truncated


def _plex_collect_leaf_matches(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_items: int,
    leaf_matches: Callable[[dict[str, Any]], bool],
    build_row: Callable[[dict[str, Any], str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)
    cap = max(0, int(max_items))
    if cap == 0:
        return [], False

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
        sk = str(key).strip()
        if sk:
            section_keys.append(sk)

    out: list[dict[str, Any]] = []
    truncated = False
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
            page_had_more = False
            for meta_idx, m in enumerate(metas):
                if not isinstance(m, dict):
                    continue
                if not _leaf_type_matches(m, media_scope):
                    continue
                if not leaf_matches(m):
                    page_had_more = True
                    continue
                rk = _rating_key(m)
                if not rk:
                    continue
                out.append(build_row(m, rk))
                if len(out) >= cap:
                    if meta_idx < len(metas) - 1 or page_had_more:
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
                break
            if start >= total_i or len(metas) == 0:
                break

    return out[:cap], truncated


def list_plex_genre_match_candidates(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_items: int,
    preview_include_genres: Sequence[str],
) -> tuple[list[dict[str, Any]], bool]:
    gf = list(preview_include_genres)

    def matches(m: dict[str, Any]) -> bool:
        return item_matches_genre_include_filter(plex_leaf_genre_tags(m), gf)

    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        if media_scope == MEDIA_SCOPE_TV:
            return {
                "granularity": "episode",
                "item_id": rk,
                "series_name": m.get("grandparentTitle") or "",
                "season_number": m.get("parentIndex"),
                "episode_number": m.get("index"),
                "episode_title": m.get("title") or "",
            }
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
        }

    return _plex_collect_leaf_matches(
        base_url=base_url,
        auth_token=auth_token,
        media_scope=media_scope,
        max_items=max_items,
        leaf_matches=matches,
        build_row=build,
    )


def list_plex_studio_match_candidates(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_items: int,
    preview_include_studios: Sequence[str],
) -> tuple[list[dict[str, Any]], bool]:
    sf = list(preview_include_studios)

    def matches(m: dict[str, Any]) -> bool:
        return item_matches_genre_include_filter(plex_leaf_studio_tags(m), sf)

    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        if media_scope == MEDIA_SCOPE_TV:
            return {
                "granularity": "episode",
                "item_id": rk,
                "series_name": m.get("grandparentTitle") or "",
                "season_number": m.get("parentIndex"),
                "episode_number": m.get("index"),
                "episode_title": m.get("title") or "",
            }
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
        }

    return _plex_collect_leaf_matches(
        base_url=base_url,
        auth_token=auth_token,
        media_scope=media_scope,
        max_items=max_items,
        leaf_matches=matches,
        build_row=build,
    )


def list_plex_people_match_candidates(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_items: int,
    preview_include_people: Sequence[str],
    preview_include_people_roles: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], bool]:
    pf = list(preview_include_people)
    roles = list(preview_include_people_roles) if preview_include_people_roles is not None else []

    def matches(m: dict[str, Any]) -> bool:
        if roles:
            tags = plex_leaf_person_tags_for_roles(m, roles)
        else:
            tags = plex_leaf_person_tags(m)
        return item_matches_people_include_filter(tags, pf)

    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        if media_scope == MEDIA_SCOPE_TV:
            return {
                "granularity": "episode",
                "item_id": rk,
                "series_name": m.get("grandparentTitle") or "",
                "season_number": m.get("parentIndex"),
                "episode_number": m.get("index"),
                "episode_title": m.get("title") or "",
            }
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
        }

    return _plex_collect_leaf_matches(
        base_url=base_url,
        auth_token=auth_token,
        media_scope=media_scope,
        max_items=max_items,
        leaf_matches=matches,
        build_row=build,
    )


def list_plex_year_range_match_candidates(
    *,
    base_url: str,
    auth_token: str,
    media_scope: str,
    max_items: int,
    preview_year_min: int | None,
    preview_year_max: int | None,
) -> tuple[list[dict[str, Any]], bool]:
    def matches(m: dict[str, Any]) -> bool:
        return item_matches_preview_year_filter(
            plex_leaf_release_year_int(m),
            preview_year_min,
            preview_year_max,
        )

    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        if media_scope == MEDIA_SCOPE_TV:
            return {
                "granularity": "episode",
                "item_id": rk,
                "series_name": m.get("grandparentTitle") or "",
                "season_number": m.get("parentIndex"),
                "episode_number": m.get("index"),
                "episode_title": m.get("title") or "",
            }
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
        }

    return _plex_collect_leaf_matches(
        base_url=base_url,
        auth_token=auth_token,
        media_scope=media_scope,
        max_items=max_items,
        leaf_matches=matches,
        build_row=build,
    )
