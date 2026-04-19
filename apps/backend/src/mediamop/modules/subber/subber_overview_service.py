"""Dashboard aggregates for Subber overview tab (library state + last-30-day activity)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.subber.subber_schemas import SubberOverviewOut
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent


def _count_state(session: Session, *, media_scope: str | None = None, status: str | None = None) -> int:
    q = select(func.count()).select_from(SubberSubtitleState)
    if media_scope is not None:
        q = q.where(SubberSubtitleState.media_scope == media_scope)
    if status is not None:
        q = q.where(SubberSubtitleState.status == status)
    return int(session.scalar(q) or 0)


def build_subber_overview(session: Session, *, window_days: int = 30) -> SubberOverviewOut:
    wd = max(1, int(window_days))
    since = datetime.now(timezone.utc) - timedelta(days=wd)

    subtitles_downloaded = _count_state(session, status="found")
    still_missing = _count_state(session, status="missing")
    skipped = _count_state(session, status="skipped")

    tv_tracked = _count_state(session, media_scope="tv")
    movies_tracked = _count_state(session, media_scope="movies")
    tv_found = _count_state(session, media_scope="tv", status="found")
    movies_found = _count_state(session, media_scope="movies", status="found")
    tv_missing = _count_state(session, media_scope="tv", status="missing")
    movies_missing = _count_state(session, media_scope="movies", status="missing")

    search_rows = session.execute(
        select(ActivityEvent.detail).where(
            ActivityEvent.event_type == C.SUBBER_SUBTITLE_SEARCH_COMPLETED,
            ActivityEvent.created_at >= since,
        ),
    ).all()

    searches_last_30_days = len(search_rows)
    found_last_30_days = 0
    not_found_last_30_days = 0
    for (detail_raw,) in search_rows:
        if not detail_raw:
            continue
        try:
            obj = json.loads(str(detail_raw))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("ok") is True:
            found_last_30_days += 1
        elif obj.get("ok") is False:
            not_found_last_30_days += 1

    upgrade_rows = session.execute(
        select(ActivityEvent.detail).where(
            ActivityEvent.event_type == C.SUBBER_SUBTITLE_UPGRADE_COMPLETED,
            ActivityEvent.created_at >= since,
        ),
    ).all()

    upgrades_last_30_days = 0
    for (detail_raw,) in upgrade_rows:
        if not detail_raw:
            continue
        try:
            obj = json.loads(str(detail_raw))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        try:
            upgrades_last_30_days += int(obj.get("upgraded") or 0)
        except (TypeError, ValueError):
            continue

    return SubberOverviewOut(
        window_days=wd,
        subtitles_downloaded=subtitles_downloaded,
        still_missing=still_missing,
        skipped=skipped,
        tv_tracked=tv_tracked,
        movies_tracked=movies_tracked,
        tv_found=tv_found,
        movies_found=movies_found,
        tv_missing=tv_missing,
        movies_missing=movies_missing,
        searches_last_30_days=searches_last_30_days,
        found_last_30_days=found_last_30_days,
        not_found_last_30_days=not_found_last_30_days,
        upgrades_last_30_days=upgrades_last_30_days,
    )
