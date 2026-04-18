"""Handlers for ``subber.webhook_import.{tv,movies}.v1``."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.modules.subber import subber_activity
from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES,
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
)
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row, language_preferences_list
from mediamop.modules.subber.subber_subtitle_state_service import upsert_subtitle_state
from mediamop.modules.subber.worker_loop import SubberJobWorkContext
from mediamop.platform.activity import constants as C


def make_subber_webhook_import_handler(
    session_factory: sessionmaker[Session],
    *,
    media_scope: str,
    search_job_kind: str,
    webhook_job_kind: str,
) -> Callable[[SubberJobWorkContext], None]:
    def handle(ctx: SubberJobWorkContext) -> None:
        p = json.loads(ctx.payload_json or "{}")
        if str(p.get("media_scope") or "") != media_scope:
            return
        file_path = str(p.get("file_path") or "").strip()
        if not file_path:
            return
        title = str(p.get("title") or "").strip()
        year = p.get("year")
        year_i = int(year) if year is not None and str(year).strip().isdigit() else None
        show_title = p.get("show_title")
        show_s = str(show_title).strip() if show_title is not None else None
        sn = p.get("season_number")
        en = p.get("episode_number")
        et = p.get("episode_title")
        son = int(sn) if sn is not None and str(sn).strip().lstrip("-").isdigit() else None
        epn = int(en) if en is not None and str(en).strip().lstrip("-").isdigit() else None
        ep_title = str(et).strip() if et is not None else None
        se_id = p.get("sonarr_episode_id")
        rm_id = p.get("radarr_movie_id")
        sonarr_episode_id = int(se_id) if se_id is not None and str(se_id).strip().isdigit() else None
        radarr_movie_id = int(rm_id) if rm_id is not None and str(rm_id).strip().isdigit() else None
        enqueued = 0
        with session_factory() as session:
            with session.begin():
                settings_row = ensure_subber_settings_row(session)
                if not settings_row.enabled:
                    return
                for lang in language_preferences_list(settings_row):
                    st = upsert_subtitle_state(
                        session,
                        media_scope=media_scope,
                        file_path=file_path,
                        language_code=lang,
                        status="missing",
                        source="webhook",
                        show_title=show_s,
                        season_number=son,
                        episode_number=epn,
                        episode_title=ep_title,
                        movie_title=title if media_scope == "movies" else None,
                        movie_year=year_i if media_scope == "movies" else None,
                        sonarr_episode_id=sonarr_episode_id if media_scope == "tv" else None,
                        radarr_movie_id=radarr_movie_id if media_scope == "movies" else None,
                    )
                    dedupe = f"subber:subtitle:{media_scope}:{st.id}:{uuid.uuid4()}"
                    subber_enqueue_or_get_job(
                        session,
                        dedupe_key=dedupe,
                        job_kind=search_job_kind,
                        payload_json=json.dumps({"state_id": int(st.id)}, separators=(",", ":")),
                    )
                    enqueued += 1
                subber_activity.record_subber_activity(
                    session,
                    event_type=C.SUBBER_WEBHOOK_IMPORT_ENQUEUED,
                    title=f"Subber webhook import ({media_scope})",
                    detail={"enqueued": enqueued, "file_path": file_path},
                )

    _ = webhook_job_kind
    return handle


def register_webhook_import_handlers(
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[SubberJobWorkContext], None]]:
    return {
        SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV: make_subber_webhook_import_handler(
            session_factory,
            media_scope="tv",
            search_job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
            webhook_job_kind=SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
        ),
        SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES: make_subber_webhook_import_handler(
            session_factory,
            media_scope="movies",
            search_job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
            webhook_job_kind=SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES,
        ),
    }
