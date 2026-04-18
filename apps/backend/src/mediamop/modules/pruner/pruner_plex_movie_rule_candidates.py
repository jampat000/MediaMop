"""Plex **movie** preview collectors using ``GET /library/sections`` + paged ``GET …/allLeaves`` only.

These paths are the same surface area as ``missing_primary_media_reported`` previews: one ``X-Plex-Token`` and no
separate account API calls.

Supported rule families (Movies scope only):

* ``watched_movies_reported`` — ``viewCount`` >= 1 **or** positive ``lastViewedAt`` on the leaf (token-scoped).
* ``watched_movie_low_rating_reported`` — same watched test, plus numeric ``audienceRating`` on the leaf at or below
  the per-scope ``watched_movie_low_rating_max_plex_audience_rating`` ceiling (persisted separately from the
  Jellyfin/Emby ``CommunityRating`` ceiling). Leaves with no numeric ``audienceRating`` are skipped.
* ``unwatched_movie_stale_reported`` — not watched by the watched test above, plus ``addedAt`` library age at or
  above the configured minimum. ``addedAt`` is interpreted as Unix epoch seconds; values above 10 billion are treated
  as milliseconds.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES
from mediamop.modules.pruner.pruner_http import http_get_json, join_base_path
from mediamop.modules.pruner.pruner_plex_missing_thumb_candidates import (
    _as_list,
    _media_container,
    _plex_headers,
    _rating_key,
    _section_matches_scope,
)


def plex_movie_leaf_watched_for_token(meta: dict[str, Any]) -> bool:
    """True when Plex leaf metadata shows play history for the authenticated token's user scope."""

    vc = meta.get("viewCount")
    if isinstance(vc, str) and vc.strip().isdigit():
        vc = int(vc.strip())
    if isinstance(vc, bool):
        return False
    if isinstance(vc, int) and vc >= 1:
        return True
    lv = meta.get("lastViewedAt")
    if lv is None or lv == "":
        return False
    try:
        n = int(float(str(lv).strip()))
    except (TypeError, ValueError):
        return False
    return n > 0


def plex_movie_leaf_unwatched_for_token(meta: dict[str, Any]) -> bool:
    return not plex_movie_leaf_watched_for_token(meta)


def plex_leaf_audience_rating_float(meta: dict[str, Any]) -> float | None:
    """Plex ``audienceRating`` on a movie leaf (often 0–10). ``None`` when absent or non-numeric."""

    r = meta.get("audienceRating")
    if isinstance(r, bool):
        return None
    if isinstance(r, (int, float)):
        return float(r)
    if isinstance(r, str):
        t = r.strip()
        if not t:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def plex_leaf_added_at_utc(meta: dict[str, Any]) -> datetime | None:
    """Library ``addedAt`` from Plex leaf metadata as UTC ``datetime``."""

    raw = meta.get("addedAt")
    if raw is None:
        return None
    try:
        ts = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None
    if ts > 10_000_000_000:
        ts = ts // 1000
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _leaf_is_movie(meta: dict[str, Any]) -> bool:
    return str(meta.get("type", "")).strip().lower() == "movie"


def _plex_collect_movie_rows(
    *,
    base_url: str,
    auth_token: str,
    max_items: int,
    row_predicate: Callable[[dict[str, Any]], bool],
    build_row: Callable[[dict[str, Any], str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    if max_items < 1:
        return [], False
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
        if not _section_matches_scope(d.get("type"), MEDIA_SCOPE_MOVIES):
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
            page_had_skipped_potential = False
            for meta_idx, m in enumerate(metas):
                if not isinstance(m, dict):
                    continue
                if not _leaf_is_movie(m):
                    continue
                if not row_predicate(m):
                    page_had_skipped_potential = True
                    continue
                rk = _rating_key(m)
                if not rk:
                    continue
                out.append(build_row(m, rk))
                if len(out) >= cap:
                    if meta_idx < len(metas) - 1 or page_had_skipped_potential:
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
                elif page_had_skipped_potential:
                    truncated = True
                break
            if start >= total_i or len(metas) == 0:
                break

    return out[:cap], truncated


def list_plex_watched_movie_candidates(
    *,
    base_url: str,
    auth_token: str,
    max_items: int,
) -> tuple[list[dict[str, Any]], bool]:
    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
        }

    return _plex_collect_movie_rows(
        base_url=base_url,
        auth_token=auth_token,
        max_items=max_items,
        row_predicate=plex_movie_leaf_watched_for_token,
        build_row=build,
    )


def list_plex_watched_movie_low_rating_candidates(
    *,
    base_url: str,
    auth_token: str,
    max_items: int,
    audience_rating_max_inclusive: float,
) -> tuple[list[dict[str, Any]], bool]:
    cap = float(audience_rating_max_inclusive)

    def pred(m: dict[str, Any]) -> bool:
        if not plex_movie_leaf_watched_for_token(m):
            return False
        ar = plex_leaf_audience_rating_float(m)
        if ar is None:
            return False
        return ar <= cap

    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        ar = plex_leaf_audience_rating_float(m)
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
            "plex_audience_rating": ar,
            "watched_movie_low_rating_max_plex_audience_rating": cap,
        }

    return _plex_collect_movie_rows(
        base_url=base_url,
        auth_token=auth_token,
        max_items=max_items,
        row_predicate=pred,
        build_row=build,
    )


def list_plex_unwatched_movie_stale_candidates(
    *,
    base_url: str,
    auth_token: str,
    max_items: int,
    min_age_days: int,
) -> tuple[list[dict[str, Any]], bool]:
    age = max(1, int(min_age_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=age)

    def pred(m: dict[str, Any]) -> bool:
        if not plex_movie_leaf_unwatched_for_token(m):
            return False
        added = plex_leaf_added_at_utc(m)
        if added is None or added > cutoff:
            return False
        return True

    def build(m: dict[str, Any], rk: str) -> dict[str, Any]:
        return {
            "granularity": "movie_item",
            "item_id": rk,
            "title": m.get("title") or "",
            "year": m.get("year"),
            "addedAt": m.get("addedAt"),
            "unwatched_movie_stale_min_age_days": age,
        }

    return _plex_collect_movie_rows(
        base_url=base_url,
        auth_token=auth_token,
        max_items=max_items,
        row_predicate=pred,
        build_row=build,
    )
