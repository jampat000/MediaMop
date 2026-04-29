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
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row
from mediamop.modules.subber.subber_subtitle_search_service import (
    search_and_download_subtitle,
    subber_any_search_configured,
)
from mediamop.modules.subber.subber_subtitle_state_service import (
    get_state_by_id,
    mark_searching,
    mark_skipped,
)
from mediamop.modules.subber.worker_loop import SubberJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.observability.diagnostics import DiagnosticAction, DiagnosticModule, DiagnosticResult, DiagnosticTrigger
from mediamop.platform.observability.operator_messages import activity_detail_envelope, media_scope_label


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
                settings_row = ensure_subber_settings_row(session)
                if not settings_row.enabled:
                    return
                if not subber_any_search_configured(settings, settings_row, session):
                    return
                perm = max(1, int(settings_row.permanent_skip_after_attempts or 10))
                if int(row.search_count or 0) >= perm:
                    mark_skipped(session, state_id)
                    subber_activity.record_subber_activity(
                        session,
                        event_type=C.SUBBER_SUBTITLE_SEARCH_COMPLETED,
                        title="Subtitle search skipped because the retry limit was reached",
                        detail={
                            **activity_detail_envelope(
                                module=DiagnosticModule.SUBBER,
                                action=DiagnosticAction.SEARCH,
                                trigger=DiagnosticTrigger.WORKER,
                                result=DiagnosticResult.SKIPPED,
                                media_scope=media_scope,
                                counts={"checked": 1, "downloaded": 0, "skipped": 1},
                                user_message="Subber has already searched this item enough times.",
                                next_action="Change Subber retry settings or manually add a subtitle if this item still needs one.",
                            ),
                            "state_id": state_id,
                            "reason": "search_count",
                        },
                    )
                    return
                mark_searching(session, state_id)
                row2 = get_state_by_id(session, state_id)
                if row2 is None:
                    return
                provider_events: list[dict[str, str]] = []
                ok = search_and_download_subtitle(
                    settings=settings,
                    settings_row=settings_row,
                    state_row=row2,
                    db=session,
                    provider_events=provider_events,
                )
                subber_activity.record_subber_activity(
                    session,
                    event_type=C.SUBBER_SUBTITLE_SEARCH_COMPLETED,
                    title=(
                        f"Subtitle downloaded for {media_scope_label(media_scope)}"
                        if ok
                        else f"No subtitle found for {media_scope_label(media_scope)}"
                    ),
                    detail={
                        **activity_detail_envelope(
                            module=DiagnosticModule.SUBBER,
                            action=DiagnosticAction.SEARCH,
                            trigger=DiagnosticTrigger.WORKER,
                            result=DiagnosticResult.SUCCESS if ok else DiagnosticResult.SKIPPED,
                            media_scope=media_scope,
                            counts={"checked": 1, "downloaded": int(bool(ok)), "skipped": int(not ok)},
                            user_message=(
                                "Subber downloaded a matching subtitle."
                                if ok
                                else "Subber checked the configured providers but did not find a usable subtitle."
                            ),
                        ),
                        "state_id": state_id,
                        "media_scope": media_scope,
                        "ok": ok,
                        "provider_events": provider_events,
                    },
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
