"""Dashboard aggregates for Subber overview tab."""

from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.subber.subber_schemas import SubberOverviewOut
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState


def build_subber_overview(session: Session) -> SubberOverviewOut:
    total = int(session.scalar(select(func.count()).select_from(SubberSubtitleState)) or 0)
    by_status = {str(r[0]): int(r[1]) for r in session.execute(select(SubberSubtitleState.status, func.count()).group_by(SubberSubtitleState.status))}
    found = int(by_status.get("found", 0))
    missing = int(by_status.get("missing", 0))
    searching = int(by_status.get("searching", 0))
    skipped = int(by_status.get("skipped", 0))
    now = datetime.now(timezone.utc)
    day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    searches_today = int(
        session.scalar(
            select(func.count())
            .select_from(SubberSubtitleState)
            .where(
                SubberSubtitleState.last_searched_at.is_not(None),
                SubberSubtitleState.last_searched_at >= day_start,
            ),
        )
        or 0,
    )
    per_lang_rows = session.execute(
        select(SubberSubtitleState.language_code, SubberSubtitleState.status, func.count())
        .group_by(SubberSubtitleState.language_code, SubberSubtitleState.status),
    ).all()
    per_map: dict[str, dict[str, int]] = {}
    for lang, st, c in per_lang_rows:
        lc = str(lang)
        d = per_map.setdefault(lc, {"language": lc, "found": 0, "missing": 0, "searching": 0, "skipped": 0, "total": 0})
        d["total"] += int(c)
        ks = str(st)
        if ks in ("found", "missing", "searching", "skipped"):
            d[ks] += int(c)
    per_language = sorted(per_map.values(), key=lambda x: str(x["language"]))
    return SubberOverviewOut(
        total_tracked=total,
        found=found,
        missing=missing,
        searching=searching,
        skipped=skipped,
        searches_today=searches_today,
        per_language=per_language,
    )
