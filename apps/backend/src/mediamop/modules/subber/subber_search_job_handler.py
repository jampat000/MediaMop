"""Handlers for ``subber.subtitle_search.{tv,movies}.v1``."""

from __future__ import annotations

import json
import os
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber import subber_activity
from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
)
from mediamop.modules.subber.subber_opensubtitles_client import SubberRateLimitError
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row
from mediamop.modules.subber.subber_subtitle_search_service import (
    opensubtitles_configured,
    search_and_download_subtitle,
)
from mediamop.modules.subber.subber_subtitle_state_service import (
    get_state_by_id,
    mark_searching,
    mark_skipped,
)
from mediamop.modules.subber.worker_loop import SubberJobWorkContext
from mediamop.platform.activity import constants as C


def make_subber_subtitle_search_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    media_scope: str,
    job_kind: str,
) -> Callable[[SubberJobWorkContext], None]:
    def handle(ctx: SubberJobWorkContext) -> None:
        payload = json.loads(ctx.payload_json or "{}")
        state_id = int(payload["state_id"])
        with session_factory() as session:
            with session.begin():
                row = get_state_by_id(session, state_id)
                if row is None:
                    return
                if row.status == "found" and row.subtitle_path and os.path.isfile(row.subtitle_path):
                    return
                if int(row.search_count or 0) >= 5:
                    mark_skipped(session, state_id)
                    subber_activity.record_subber_activity(
                        session,
                        event_type=C.SUBBER_SUBTITLE_SEARCH_COMPLETED,
                        title="Subtitle search skipped (limit)",
                        detail={"state_id": state_id, "reason": "search_count"},
                    )
                    return
                settings_row = ensure_subber_settings_row(session)
                if not settings_row.enabled:
                    return
                if not opensubtitles_configured(settings, settings_row):
                    return
                mark_searching(session, state_id)
                row2 = get_state_by_id(session, state_id)
                if row2 is None:
                    return
                try:
                    ok = search_and_download_subtitle(
                        settings=settings,
                        settings_row=settings_row,
                        state_row=row2,
                        db=session,
                    )
                except SubberRateLimitError:
                    raise
                subber_activity.record_subber_activity(
                    session,
                    event_type=C.SUBBER_SUBTITLE_SEARCH_COMPLETED,
                    title="Subtitle search finished",
                    detail={"state_id": state_id, "media_scope": media_scope, "ok": ok},
                )

    _ = job_kind
    return handle


def register_subtitle_search_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[SubberJobWorkContext], None]]:
    return {
        SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV: make_subber_subtitle_search_handler(
            settings,
            session_factory,
            media_scope="tv",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
        ),
        SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES: make_subber_subtitle_search_handler(
            settings,
            session_factory,
            media_scope="movies",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
        ),
    }
