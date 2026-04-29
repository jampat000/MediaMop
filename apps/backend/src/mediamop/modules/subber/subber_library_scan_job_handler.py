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
from mediamop.modules.subber.subber_subtitle_state_service import get_missing_for_scope, mark_skipped
from mediamop.modules.subber.worker_loop import SubberJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.observability.diagnostics import DiagnosticAction, DiagnosticModule, DiagnosticResult, DiagnosticTrigger
from mediamop.platform.observability.operator_messages import activity_detail_envelope, scan_title


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
        default_cutoff = when - timedelta(hours=6)
        enqueued = 0
        with session_factory() as session:
            with session.begin():
                settings_row = ensure_subber_settings_row(session)
                if not settings_row.enabled:
                    return
                for row in get_missing_for_scope(session, media_scope):
                    sc = int(row.search_count or 0)
                    perm = max(1, int(settings_row.permanent_skip_after_attempts or 10))
                    if sc >= perm:
                        mark_skipped(session, int(row.id))
                        continue
                    last = row.last_searched_at
                    if last is not None:
                        lu = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                        if bool(settings_row.adaptive_searching_enabled):
                            max_att = max(1, int(settings_row.adaptive_searching_max_attempts or 3))
                            delay_h = max(1, int(settings_row.adaptive_searching_delay_hours or 168))
                            if sc >= max_att:
                                if lu > when - timedelta(hours=delay_h):
                                    continue
                            elif lu > default_cutoff:
                                continue
                        elif lu > default_cutoff:
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
                    title=scan_title(
                        module_label="Subber",
                        result=DiagnosticResult.SUCCESS,
                        count=enqueued,
                        scope=media_scope,
                    ),
                    detail={
                        **activity_detail_envelope(
                            module=DiagnosticModule.SUBBER,
                            action=DiagnosticAction.SCAN,
                            trigger=DiagnosticTrigger.MANUAL,
                            result=DiagnosticResult.SUCCESS,
                            media_scope=media_scope,
                            counts={"queued": enqueued},
                            user_message=(
                                f"Subber queued {enqueued} subtitle search"
                                f"{'' if enqueued == 1 else 'es'} for {media_scope}."
                            ),
                        ),
                        "enqueued": enqueued,
                        "media_scope": media_scope,
                    },
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
