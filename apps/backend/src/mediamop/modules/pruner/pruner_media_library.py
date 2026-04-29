"""Emby / Jellyfin / Plex library probes for Pruner (connection test + rule-family previews)."""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta, timezone
from collections.abc import Sequence
from typing import Any

from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_GENRE_MATCH_REPORTED,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
    RULE_FAMILY_PEOPLE_MATCH_REPORTED,
    RULE_FAMILY_STUDIO_MATCH_REPORTED,
    RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
    RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
    RULE_FAMILY_WATCHED_TV_REPORTED,
    RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
)
from mediamop.modules.pruner.pruner_independent_rule_candidates import (
    list_jf_emby_genre_match_candidates,
    list_jf_emby_people_match_candidates,
    list_jf_emby_studio_match_candidates,
    list_jf_emby_year_range_match_candidates,
    list_plex_genre_match_candidates,
    list_plex_people_match_candidates,
    list_plex_studio_match_candidates,
    list_plex_year_range_match_candidates,
)
from mediamop.modules.pruner.pruner_plex_missing_thumb_candidates import list_plex_missing_thumb_candidates
from mediamop.modules.pruner.pruner_plex_movie_rule_candidates import (
    list_plex_unwatched_movie_stale_candidates,
    list_plex_watched_movie_candidates,
    list_plex_watched_movie_low_rating_candidates,
)
from mediamop.modules.pruner.pruner_http import (
    PrunerHttpStatusError,
    http_get_json,
    http_get_text,
    join_base_path,
)

def jf_emby_pruner_preview_items_fields_csv() -> str:
    """Comma-separated Jellyfin/Emby ``Fields`` for **all** Pruner preview ``Items`` queries in this module.

    Jellyfin and Emby only return top-level keys listed in ``Fields``. **People filters** require ``People`` on each
    row; **watched low-rating** requires ``CommunityRating`` (0–10 on that field for Jellyfin/Emby); **studio**
    preview includes require ``Studios``. Any new preview collector that reads additional Item properties **must**
    extend this union — do not add ad hoc ``Fields`` strings per call site or filters will silently see empty data.
    """

    return ",".join(
        (
            "CommunityRating",
            "DateCreated",
            "Genres",
            "Id",
            "ImageTags",
            "IndexNumber",
            "Name",
            "ParentIndexNumber",
            "People",
            "PrimaryImageItemId",
            "ProductionYear",
            "SeriesName",
            "Studios",
            "UserData",
        ),
    )


def _jf_emby_items_params_attach_preview_fields(params: dict[str, str]) -> None:
    params["Fields"] = jf_emby_pruner_preview_items_fields_csv()


def _emby_style_headers(api_key: str) -> dict[str, str]:
    return {"X-Emby-Token": api_key, "Accept": "application/json"}


def test_emby_jellyfin_connection(*, base_url: str, api_key: str = "") -> tuple[bool, str]:
    """Authenticated Jellyfin/Emby connection test using the saved API key."""

    if not api_key.strip():
        return False, "API key is missing. Re-enter the server API key and try the connection test again."

    url = join_base_path(base_url, "Users")
    try:
        status, data = http_get_json(url, headers=_emby_style_headers(api_key))
    except urllib.error.URLError as e:
        return False, f"network error: {e}"
    except Exception as e:  # noqa: BLE001 — surface to operator
        return False, f"error: {e}"
    if status in (401, 403):
        return False, "Authentication failed. Re-enter the server API key and run the connection test again."
    if status != 200:
        return False, f"HTTP {status}"
    if not isinstance(data, list):
        return False, "unexpected response from authenticated Users endpoint"
    return True, "Authenticated API key accepted"


def test_plex_connection(*, base_url: str, auth_token: str | None) -> tuple[bool, str]:
    """Minimal Plex ping: ``GET /identity`` (local servers; optional ``X-Plex-Token``)."""

    url = join_base_path(base_url, "identity")
    headers: dict[str, str] = {"Accept": "application/xml"}
    if auth_token:
        headers["X-Plex-Token"] = auth_token
    try:
        status, text = http_get_text(url, headers=headers)
    except urllib.error.URLError as e:
        return False, f"network error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"error: {e}"
    if status != 200:
        return False, f"HTTP {status}"
    snippet = text[:2000].lower()
    if "media" not in snippet and "plex" not in snippet:
        return False, "unexpected identity payload (not Plex?)"
    return True, "Plex identity OK"


def _items_query(*, base_url: str, api_key: str, params: dict[str, str]) -> dict[str, Any] | None:
    url = join_base_path(base_url, "Items", params)
    status, data = http_get_json(url, headers=_emby_style_headers(api_key))
    if status != 200:
        raise PrunerHttpStatusError(url=url, status_code=status, body=data)
    if not isinstance(data, dict):
        msg = "Items query returned non-object JSON"
        raise RuntimeError(msg)
    return data


def _items_page(
    *,
    base_url: str,
    api_key: str,
    include_item_types: str,
    start_index: int,
    page_limit: int,
    use_has_primary_image: bool,
) -> dict[str, Any] | None:
    params: dict[str, str] = {
        "Recursive": "true",
        "IncludeItemTypes": include_item_types,
        "StartIndex": str(start_index),
        "Limit": str(page_limit),
    }
    if use_has_primary_image:
        params["HasPrimaryImage"] = "false"
    _jf_emby_items_params_attach_preview_fields(params)
    return _items_query(base_url=base_url, api_key=api_key, params=params)


def _item_missing_primary(item: dict[str, Any]) -> bool:
    if item.get("ImageTags") and isinstance(item["ImageTags"], dict) and item["ImageTags"].get("Primary"):
        return False
    if item.get("PrimaryImageItemId"):
        return False
    return True


def list_missing_primary_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return candidate dicts for TV (episodes) or Movies (movie items), newest-first pages.

    ``truncated`` is True when more rows existed beyond ``max_items``.
    """

    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)

    use_filter = True
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items))
    total_hits: int | None = None

    while len(candidates) < max_items:
        try:
            data = _items_page(
                base_url=base_url,
                api_key=api_key,
                include_item_types=include_types,
                start_index=start,
                page_limit=page,
                use_has_primary_image=use_filter,
            )
        except PrunerHttpStatusError as e:
            if e.status_code == 400 and use_filter:
                use_filter = False
                start = 0
                candidates.clear()
                total_hits = None
                continue
            raise
        assert data is not None
        items = data.get("Items")
        if not isinstance(items, list):
            break
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not use_filter and not _item_missing_primary(it):
                continue
            if media_scope == MEDIA_SCOPE_TV:
                candidates.append(
                    {
                        "granularity": "episode",
                        "item_id": str(it.get("Id", "")),
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
                        "item_id": str(it.get("Id", "")),
                        "title": it.get("Name") or "",
                        "year": it.get("ProductionYear"),
                    },
                )
            if len(candidates) >= max_items:
                break

        fetched = len(items)
        start += fetched
        if fetched == 0:
            break

    truncated = False
    if total_hits is not None and len(candidates) < total_hits and len(candidates) >= max_items:
        truncated = True
    elif total_hits is not None and start < total_hits and len(candidates) >= max_items:
        truncated = True

    return candidates, truncated


def _parse_item_date_created(raw: object) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _item_unplayed_by_userdata(item: dict[str, Any]) -> bool:
    ud = item.get("UserData")
    if isinstance(ud, dict):
        if ud.get("Played") is True:
            return False
        pc = ud.get("PlayCount")
        if isinstance(pc, int) and pc > 0:
            return False
    return True


def _item_watched_by_userdata(item: dict[str, Any]) -> bool:
    """Watched for the authenticated library user (API token), per Jellyfin/Emby ``UserData``."""

    ud = item.get("UserData")
    if isinstance(ud, dict):
        if ud.get("Played") is True:
            return True
        pc = ud.get("PlayCount")
        if isinstance(pc, int) and pc > 0:
            return True
    return False


def jellyfin_emby_item_community_rating(item: dict[str, Any]) -> float | None:
    """Jellyfin/Emby ``CommunityRating`` on Items (documented 0–10 scale for this field — not remapped)."""

    r = item.get("CommunityRating")
    if isinstance(r, bool):
        return None
    if isinstance(r, (int, float)):
        return float(r)
    return None


def list_watched_tv_episode_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Episodes the server reports as watched for this API user (``UserData`` / optional ``IsPlayed`` filter).

    **TV scope only** — callers must pass ``media_scope=tv``.
    """

    if media_scope != MEDIA_SCOPE_TV:
        msg = f"watched_tv_reported requires media_scope={MEDIA_SCOPE_TV!r}, got {media_scope!r}"
        raise ValueError(msg)

    include_types = "Episode"
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items * 3))
    use_is_played_filter = True
    total_hits: int | None = None
    truncated = False

    while len(candidates) < max_items:
        params: dict[str, str] = {
            "Recursive": "true",
            "IncludeItemTypes": include_types,
            "StartIndex": str(start),
            "Limit": str(page),
        }
        if use_is_played_filter:
            params["IsPlayed"] = "true"
        _jf_emby_items_params_attach_preview_fields(params)
        try:
            data = _items_query(base_url=base_url, api_key=api_key, params=params)
        except PrunerHttpStatusError as e:
            if e.status_code == 400 and use_is_played_filter:
                use_is_played_filter = False
                start = 0
                candidates.clear()
                total_hits = None
                continue
            raise
        assert data is not None
        items = data.get("Items")
        if not isinstance(items, list):
            break
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not use_is_played_filter and not _item_watched_by_userdata(it):
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
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
            if len(candidates) >= max_items:
                break

        fetched = len(items)
        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            if total_hits is not None and start < total_hits:
                truncated = True
            elif fetched >= page:
                truncated = True
            break

    return candidates[:max_items], truncated


def list_watched_movie_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Movie library items the server reports as watched for this API user (``UserData`` / optional ``IsPlayed`` filter).

    **Movies scope only** — callers must pass ``media_scope=movies``.
    """

    if media_scope != MEDIA_SCOPE_MOVIES:
        msg = f"watched_movies_reported requires media_scope={MEDIA_SCOPE_MOVIES!r}, got {media_scope!r}"
        raise ValueError(msg)

    include_types = "Movie"
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items * 3))
    use_is_played_filter = True
    total_hits: int | None = None
    truncated = False

    while len(candidates) < max_items:
        params: dict[str, str] = {
            "Recursive": "true",
            "IncludeItemTypes": include_types,
            "StartIndex": str(start),
            "Limit": str(page),
        }
        if use_is_played_filter:
            params["IsPlayed"] = "true"
        _jf_emby_items_params_attach_preview_fields(params)
        try:
            data = _items_query(base_url=base_url, api_key=api_key, params=params)
        except PrunerHttpStatusError as e:
            if e.status_code == 400 and use_is_played_filter:
                use_is_played_filter = False
                start = 0
                candidates.clear()
                total_hits = None
                continue
            raise
        assert data is not None
        items = data.get("Items")
        if not isinstance(items, list):
            break
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not use_is_played_filter and not _item_watched_by_userdata(it):
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
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

        fetched = len(items)
        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            if total_hits is not None and start < total_hits:
                truncated = True
            elif fetched >= page:
                truncated = True
            break

    return candidates[:max_items], truncated


def list_watched_movie_low_rating_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    community_rating_max_inclusive: float,
) -> tuple[list[dict[str, Any]], bool]:
    """Watched **movie** items with Jellyfin/Emby ``CommunityRating`` at or below ``community_rating_max_inclusive``.

    Uses the same watched signal as ``list_watched_movie_candidates`` (``UserData`` / ``IsPlayed``). The rating gate
    uses the provider's ``CommunityRating`` field only (0–10 on that field in this slice — not remapped to another
    scale). Items with no numeric ``CommunityRating`` are skipped.

    **Movies scope only.**
    """

    if media_scope != MEDIA_SCOPE_MOVIES:
        msg = f"watched_movie_low_rating_reported requires media_scope={MEDIA_SCOPE_MOVIES!r}, got {media_scope!r}"
        raise ValueError(msg)

    cap = float(community_rating_max_inclusive)
    include_types = "Movie"
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items * 3))
    use_is_played_filter = True
    total_hits: int | None = None
    truncated = False

    while len(candidates) < max_items:
        params: dict[str, str] = {
            "Recursive": "true",
            "IncludeItemTypes": include_types,
            "StartIndex": str(start),
            "Limit": str(page),
        }
        if use_is_played_filter:
            params["IsPlayed"] = "true"
        _jf_emby_items_params_attach_preview_fields(params)
        try:
            data = _items_query(base_url=base_url, api_key=api_key, params=params)
        except PrunerHttpStatusError as e:
            if e.status_code == 400 and use_is_played_filter:
                use_is_played_filter = False
                start = 0
                candidates.clear()
                total_hits = None
                continue
            raise
        assert data is not None
        items = data.get("Items")
        if not isinstance(items, list):
            break
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not use_is_played_filter and not _item_watched_by_userdata(it):
                continue
            rating = jellyfin_emby_item_community_rating(it)
            if rating is None or rating > cap:
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
            candidates.append(
                {
                    "granularity": "movie_item",
                    "item_id": iid,
                    "title": it.get("Name") or "",
                    "year": it.get("ProductionYear"),
                    "community_rating": rating,
                    "watched_movie_low_rating_max_jellyfin_emby_community_rating": cap,
                },
            )
            if len(candidates) >= max_items:
                break

        fetched = len(items)
        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            if total_hits is not None and start < total_hits:
                truncated = True
            elif fetched >= page:
                truncated = True
            break

    return candidates[:max_items], truncated


def list_unwatched_movie_stale_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    min_age_days: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Unwatched **movie** items whose library ``DateCreated`` is older than ``min_age_days`` (UTC).

    Same unplayed + ``DateCreated`` semantics as ``list_never_played_stale_candidates`` for movies, but as its own
    rule family with a separate per-scope age setting.

    **Movies scope only.**
    """

    if media_scope != MEDIA_SCOPE_MOVIES:
        msg = f"unwatched_movie_stale_reported requires media_scope={MEDIA_SCOPE_MOVIES!r}, got {media_scope!r}"
        raise ValueError(msg)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(min_age_days)))
    include_types = "Movie"
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items * 3))
    use_is_played_filter = True
    total_hits: int | None = None
    truncated = False

    while len(candidates) < max_items:
        params: dict[str, str] = {
            "Recursive": "true",
            "IncludeItemTypes": include_types,
            "StartIndex": str(start),
            "Limit": str(page),
        }
        if use_is_played_filter:
            params["IsPlayed"] = "false"
        _jf_emby_items_params_attach_preview_fields(params)
        try:
            data = _items_query(base_url=base_url, api_key=api_key, params=params)
        except PrunerHttpStatusError as e:
            if e.status_code == 400 and use_is_played_filter:
                use_is_played_filter = False
                start = 0
                candidates.clear()
                total_hits = None
                continue
            raise
        assert data is not None
        items = data.get("Items")
        if not isinstance(items, list):
            break
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not _item_unplayed_by_userdata(it):
                continue
            created = _parse_item_date_created(it.get("DateCreated"))
            if created is None or created > cutoff:
                continue
            iid = str(it.get("Id", "")).strip()
            if not iid:
                continue
            candidates.append(
                {
                    "granularity": "movie_item",
                    "item_id": iid,
                    "title": it.get("Name") or "",
                    "year": it.get("ProductionYear"),
                    "date_created": it.get("DateCreated"),
                    "unwatched_movie_stale_min_age_days": int(min_age_days),
                },
            )
            if len(candidates) >= max_items:
                break

        fetched = len(items)
        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            if total_hits is not None and start < total_hits:
                truncated = True
            elif fetched >= page:
                truncated = True
            break

    return candidates[:max_items], truncated


def list_never_played_stale_candidates(
    *,
    base_url: str,
    api_key: str,
    media_scope: str,
    max_items: int,
    min_age_days: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Unplayed episodes or movies whose library ``DateCreated`` is older than ``min_age_days`` (UTC).

    Uses Jellyfin/Emby ``GET /Items`` with ``IsPlayed=false`` when accepted; otherwise pages without that filter and
    applies unplayed + age checks client-side. Play state is **the library user's view for this API token** — not a
    global household aggregate.
    """

    if media_scope == MEDIA_SCOPE_TV:
        include_types = "Episode"
    elif media_scope == MEDIA_SCOPE_MOVIES:
        include_types = "Movie"
    else:
        msg = f"unsupported media_scope: {media_scope!r}"
        raise ValueError(msg)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(min_age_days)))
    candidates: list[dict[str, Any]] = []
    start = 0
    page = min(100, max(1, max_items * 3))
    use_is_played_filter = True
    total_hits: int | None = None
    truncated = False

    while len(candidates) < max_items:
        params: dict[str, str] = {
            "Recursive": "true",
            "IncludeItemTypes": include_types,
            "StartIndex": str(start),
            "Limit": str(page),
        }
        if use_is_played_filter:
            params["IsPlayed"] = "false"
        _jf_emby_items_params_attach_preview_fields(params)
        try:
            data = _items_query(base_url=base_url, api_key=api_key, params=params)
        except PrunerHttpStatusError as e:
            if e.status_code == 400 and use_is_played_filter:
                use_is_played_filter = False
                start = 0
                candidates.clear()
                total_hits = None
                continue
            raise
        assert data is not None
        items = data.get("Items")
        if not isinstance(items, list):
            break
        if "TotalRecordCount" in data and isinstance(data["TotalRecordCount"], int):
            total_hits = int(data["TotalRecordCount"])

        for it in items:
            if not isinstance(it, dict):
                continue
            if not _item_unplayed_by_userdata(it):
                continue
            created = _parse_item_date_created(it.get("DateCreated"))
            if created is None or created > cutoff:
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
                        "date_created": it.get("DateCreated"),
                        "min_age_days_threshold": int(min_age_days),
                    },
                )
            else:
                candidates.append(
                    {
                        "granularity": "movie_item",
                        "item_id": iid,
                        "title": it.get("Name") or "",
                        "year": it.get("ProductionYear"),
                        "date_created": it.get("DateCreated"),
                        "min_age_days_threshold": int(min_age_days),
                    },
                )
            if len(candidates) >= max_items:
                break

        fetched = len(items)
        start += fetched
        if fetched == 0:
            break
        if len(candidates) >= max_items:
            if total_hits is not None and start < total_hits:
                truncated = True
            elif fetched >= page:
                truncated = True
            break

    return candidates[:max_items], truncated


def plex_preview_unsupported_detail() -> str:
    return (
        "Plex: this rule family has no candidate preview on MediaMop in this release (use Connection for a Plex ping). "
        "Plex supports preview → apply for missing primary art, watched movies, watched low-rating movies (leaf "
        "audienceRating), and unwatched stale movies (leaf addedAt) via allLeaves with your token; stale never-played "
        "and watched TV previews are not implemented for Plex here."
    )


def plex_never_played_preview_unsupported_detail() -> str:
    return (
        "Plex: never-played stale library candidacy is not implemented on MediaMop (Jellyfin/Emby only for this rule). "
        "Use Connection for a Plex ping."
    )


def plex_watched_tv_preview_unsupported_detail() -> str:
    return (
        "Plex: watched TV preview is not implemented on MediaMop in this release (Jellyfin/Emby only). "
        "Use Connection for a Plex ping."
    )


def preview_payload_json(
    *,
    provider: str,
    base_url: str,
    media_scope: str,
    secrets: dict[str, str],
    max_items: int,
    rule_family_id: str,
    never_played_min_age_days: int | None = None,
    preview_include_genres: Sequence[str] | None = None,
    preview_include_people: Sequence[str] | None = None,
    preview_include_people_roles: Sequence[str] | None = None,
    watched_movie_low_rating_max_jellyfin_emby_community_rating: float | None = None,
    watched_movie_low_rating_max_plex_audience_rating: float | None = None,
    unwatched_movie_stale_min_age_days: int | None = None,
    preview_year_min: int | None = None,
    preview_year_max: int | None = None,
    preview_include_studios: Sequence[str] | None = None,
) -> tuple[str, str, list[dict[str, Any]], bool]:
    """Returns ``(outcome, unsupported_detail_or_empty, candidates, truncated)``."""

    if provider == "plex":
        if rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED:
            return "unsupported", plex_watched_tv_preview_unsupported_detail(), [], False
        if rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
            return "unsupported", plex_never_played_preview_unsupported_detail(), [], False

        token = str(secrets.get("auth_token") or secrets.get("plex_token") or "").strip()

        def _require_plex_token() -> str:
            if not token:
                msg = "plex auth token missing in credentials envelope"
                raise ValueError(msg)
            return token

        preview_genres = list(preview_include_genres or [])
        preview_studios = list(preview_include_studios or [])
        preview_people = list(preview_include_people or [])

        if rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED:
            if media_scope != MEDIA_SCOPE_MOVIES:
                return (
                    "unsupported",
                    "watched_movies_reported applies to the Movies tab only (TV is out of scope for this rule pass).",
                    [],
                    False,
                )
            cands, trunc = list_plex_watched_movie_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                max_items=max_items,
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED:
            if media_scope != MEDIA_SCOPE_MOVIES:
                return (
                    "unsupported",
                    "watched_movie_low_rating_reported applies to the Movies tab only (TV is out of scope for this rule pass).",
                    [],
                    False,
                )
            if watched_movie_low_rating_max_plex_audience_rating is None:
                msg = (
                    "watched_movie_low_rating_max_plex_audience_rating is required for "
                    "watched_movie_low_rating_reported preview on Plex"
                )
                raise ValueError(msg)
            cands, trunc = list_plex_watched_movie_low_rating_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                max_items=max_items,
                audience_rating_max_inclusive=float(watched_movie_low_rating_max_plex_audience_rating),
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED:
            if media_scope != MEDIA_SCOPE_MOVIES:
                return (
                    "unsupported",
                    "unwatched_movie_stale_reported applies to the Movies tab only (TV is out of scope for this rule pass).",
                    [],
                    False,
                )
            if unwatched_movie_stale_min_age_days is None:
                msg = "unwatched_movie_stale_min_age_days is required for unwatched_movie_stale_reported preview"
                raise ValueError(msg)
            cands, trunc = list_plex_unwatched_movie_stale_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                max_items=max_items,
                min_age_days=int(unwatched_movie_stale_min_age_days),
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
            if not token:
                msg = "plex auth token missing in credentials envelope"
                raise ValueError(msg)
            # Same read-only Plex leaf probe as ``pruner_plex_missing_thumb_candidates.list_plex_missing_thumb_candidates``
            # (empty/missing ``thumb`` on episode/movie leaves). Preview-only — never performs apply or live removal.
            # Item cap is enforced in ``pruner_preview_job_handler`` via ``plex_missing_primary_effective_max_items``.
            cands, trunc = list_plex_missing_thumb_candidates(
                base_url=base_url,
                auth_token=token,
                media_scope=media_scope,
                max_items=max_items,
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_GENRE_MATCH_REPORTED:
            if not preview_genres:
                return (
                    "unsupported",
                    "No genres selected — select at least one genre to use this rule.",
                    [],
                    False,
                )
            cands, trunc = list_plex_genre_match_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                media_scope=media_scope,
                max_items=max_items,
                preview_include_genres=preview_genres,
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_STUDIO_MATCH_REPORTED:
            if not preview_studios:
                return (
                    "unsupported",
                    "No studios selected — select at least one studio to use this rule.",
                    [],
                    False,
                )
            cands, trunc = list_plex_studio_match_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                media_scope=media_scope,
                max_items=max_items,
                preview_include_studios=preview_studios,
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_PEOPLE_MATCH_REPORTED:
            if not preview_people:
                return (
                    "unsupported",
                    "No people entered — enter at least one name to use this rule.",
                    [],
                    False,
                )
            cands, trunc = list_plex_people_match_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                media_scope=media_scope,
                max_items=max_items,
                preview_include_people=preview_people,
                preview_include_people_roles=preview_include_people_roles,
            )
            return "success", "", cands, trunc
        if rule_family_id == RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED:
            if preview_year_min is None and preview_year_max is None:
                return (
                    "unsupported",
                    "No year range set — set at least one year bound to use this rule.",
                    [],
                    False,
                )
            cands, trunc = list_plex_year_range_match_candidates(
                base_url=base_url,
                auth_token=_require_plex_token(),
                media_scope=media_scope,
                max_items=max_items,
                preview_year_min=preview_year_min,
                preview_year_max=preview_year_max,
            )
            return "success", "", cands, trunc
        return "unsupported", plex_preview_unsupported_detail(), [], False
    api_key = secrets.get("api_key", "")
    preview_genres = list(preview_include_genres or [])
    preview_studios = list(preview_include_studios or [])
    preview_people = list(preview_include_people or [])
    if rule_family_id == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
        cands, trunc = list_missing_primary_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED:
        if media_scope != MEDIA_SCOPE_TV:
            return (
                "unsupported",
                "watched_tv_reported applies to the TV tab only (Movies is out of scope for this rule pass).",
                [],
                False,
            )
        cands, trunc = list_watched_tv_episode_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED:
        if media_scope != MEDIA_SCOPE_MOVIES:
            return (
                "unsupported",
                "watched_movies_reported applies to the Movies tab only (TV is out of scope for this rule pass).",
                [],
                False,
            )
        cands, trunc = list_watched_movie_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
        if never_played_min_age_days is None:
            msg = "never_played_min_age_days is required for never_played_stale_reported preview"
            raise ValueError(msg)
        cands, trunc = list_never_played_stale_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            min_age_days=int(never_played_min_age_days),
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED:
        if media_scope != MEDIA_SCOPE_MOVIES:
            return (
                "unsupported",
                "watched_movie_low_rating_reported applies to the Movies tab only (TV is out of scope for this rule pass).",
                [],
                False,
            )
        if watched_movie_low_rating_max_jellyfin_emby_community_rating is None:
            msg = (
                "watched_movie_low_rating_max_jellyfin_emby_community_rating is required for "
                "watched_movie_low_rating_reported preview on Jellyfin/Emby"
            )
            raise ValueError(msg)
        cands, trunc = list_watched_movie_low_rating_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            community_rating_max_inclusive=float(watched_movie_low_rating_max_jellyfin_emby_community_rating),
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED:
        if media_scope != MEDIA_SCOPE_MOVIES:
            return (
                "unsupported",
                "unwatched_movie_stale_reported applies to the Movies tab only (TV is out of scope for this rule pass).",
                [],
                False,
            )
        if unwatched_movie_stale_min_age_days is None:
            msg = "unwatched_movie_stale_min_age_days is required for unwatched_movie_stale_reported preview"
            raise ValueError(msg)
        cands, trunc = list_unwatched_movie_stale_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            min_age_days=int(unwatched_movie_stale_min_age_days),
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_GENRE_MATCH_REPORTED:
        if not preview_genres:
            return (
                "unsupported",
                "No genres selected — select at least one genre to use this rule.",
                [],
                False,
            )
        cands, trunc = list_jf_emby_genre_match_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            preview_include_genres=preview_genres,
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_STUDIO_MATCH_REPORTED:
        if not preview_studios:
            return (
                "unsupported",
                "No studios selected — select at least one studio to use this rule.",
                [],
                False,
            )
        cands, trunc = list_jf_emby_studio_match_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            preview_include_studios=preview_studios,
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_PEOPLE_MATCH_REPORTED:
        if not preview_people:
            return (
                "unsupported",
                "No people entered — enter at least one name to use this rule.",
                [],
                False,
            )
        cands, trunc = list_jf_emby_people_match_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            preview_include_people=preview_people,
            preview_include_people_roles=preview_include_people_roles,
        )
        return "success", "", cands, trunc
    if rule_family_id == RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED:
        if preview_year_min is None and preview_year_max is None:
            return (
                "unsupported",
                "No year range set — set at least one year bound to use this rule.",
                [],
                False,
            )
        cands, trunc = list_jf_emby_year_range_match_candidates(
            base_url=base_url,
            api_key=api_key,
            media_scope=media_scope,
            max_items=max_items,
            preview_year_min=preview_year_min,
            preview_year_max=preview_year_max,
        )
        return "success", "", cands, trunc
    msg = f"unsupported rule_family_id for preview: {rule_family_id!r}"
    raise ValueError(msg)


def serialize_candidates(candidates: list[dict[str, Any]]) -> str:
    return json.dumps(candidates, separators=(",", ":"))[:8_000_000]
