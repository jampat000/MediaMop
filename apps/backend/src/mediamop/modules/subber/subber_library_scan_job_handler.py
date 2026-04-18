"""Handlers for ``subber.library_scan.{tv,movies}.v1``."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from mediamop.modules.subber import subber_activity
from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
    SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
)
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row
from mediamop.modules.subber.subber_subtitle_state_service import get_missing_for_scope
from mediamop.modules.subber.worker_loop import SubberJobWorkContext
from mediamop.platform.activity import constants as C


def make_subber_library_scan_handler(
    session_factory: sessionmaker[Session],
    *,
    media_scope: str,
    search_job_kind: str,
    library_job_kind: str,
) -> Callable[[SubberJobWorkContext], None]:
    def handle(ctx: SubberJobWorkContext) -> None:
        payload = json.loads(ctx.payload_json or "{}")
        if str(payload.get("media_scope") or "") != media_scope:
            return
        when = datetime.now(timezone.utc)
        cutoff = when - timedelta(hours=6)
        enqueued = 0
        with session_factory() as session:
            with session.begin():
                settings_row = ensure_subber_settings_row(session)
                if not settings_row.enabled:
                    return
                for row in get_missing_for_scope(session, media_scope):
                    last = row.last_searched_at
                    if last is not None:
                        lu = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                        if lu > cutoff:
                            continue
                    dedupe = f"subber:subtitle:{media_scope}:{row.id}:{uuid.uuid4()}"
                    subber_enqueue_or_get_job(
                        session,
                        dedupe_key=dedupe,
                        job_kind=search_job_kind,
                        payload_json=json.dumps({"state_id": int(row.id)}, separators=(",", ":")),
                    )
                    enqueued += 1
                subber_activity.record_subber_activity(
                    session,
                    event_type=C.SUBBER_LIBRARY_SCAN_ENQUEUED,
                    title=f"Subber library scan ({media_scope})",
                    detail={"enqueued": enqueued, "media_scope": media_scope},
                )

    _ = library_job_kind
    return handle


def register_library_scan_handlers(
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[SubberJobWorkContext], None]]:
    return {
        SUBBER_JOB_KIND_LIBRARY_SCAN_TV: make_subber_library_scan_handler(
            session_factory,
            media_scope="tv",
            search_job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
            library_job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
        ),
        SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES: make_subber_library_scan_handler(
            session_factory,
            media_scope="movies",
            search_job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
            library_job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
        ),
    }
