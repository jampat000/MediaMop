"""One inbound webhook for every media manager: ``POST /api/v1/intake/webhook/{source}``.

The source in the path selects a payload dialect, nothing more. What MediaMop then does
is decided by the event, not by who sent it: an ``imported`` event is Subber's cue to go
looking for subtitles, a ``handoff`` is Refiner's cue to clean the file and report back.
A manager that does both gets both from the same endpoint.
"""

from __future__ import annotations

import json
import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_path_settings_service import ensure_refiner_path_settings_row
from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES,
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
)
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.platform.media_managers.handoff_paths import relative_media_path_for_handoff
from mediamop.platform.media_managers.import_events import (
    MediaManagerImportEvent,
    dialect_for_source,
    known_source_keys,
)

router = APIRouter(tags=["media-manager-intake"])


def _validate_webhook_secret(
    settings: SettingsDep,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> None:
    """Reject requests when a webhook secret is configured and the header does not match."""

    configured = settings.subber_webhook_secret
    if not configured:
        return
    provided = (x_webhook_secret or "").strip()
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Webhook-Secret header.",
        )


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _enqueue_subtitle_import(session: Session, event: MediaManagerImportEvent) -> str:
    job_kind = SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV if event.media_scope == "tv" else SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES
    subber_enqueue_or_get_job(
        session,
        dedupe_key=f"subber:wh:{job_kind}:{uuid.uuid4()}",
        job_kind=job_kind,
        payload_json=_compact_json(event.to_subber_job_payload()),
    )
    return job_kind


def _enqueue_refine(session: Session, event: MediaManagerImportEvent) -> str:
    row = ensure_refiner_path_settings_row(session)
    watched = row.refiner_tv_watched_folder if event.media_scope == "tv" else row.refiner_watched_folder
    resolved = relative_media_path_for_handoff(watched_folder=watched, file_path=event.file_path)
    if not resolved.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resolved.problem)

    payload: dict[str, Any] = {
        "relative_media_path": resolved.relative_media_path,
        "media_scope": event.media_scope,
    }
    # Carried on the job so the completion report can find its way home without a
    # second table: the job row already persists its payload across restarts.
    if event.handoff_id or event.callback_path:
        payload["origin"] = {
            "source_key": event.source_key,
            "handoff_id": event.handoff_id,
            "callback_path": event.callback_path,
            "release_name": event.release_name,
        }

    # The manager's own idempotency key when it gave us one, so a repeated hand-off
    # after a restart returns the existing job instead of remuxing the file twice.
    dedupe_key = (
        f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:{event.source_key}:handoff:{event.handoff_id}"
        if event.handoff_id
        else f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:{uuid.uuid4().hex}"
    )
    refiner_enqueue_or_get_job(
        session,
        dedupe_key=dedupe_key,
        job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
        payload_json=_compact_json(payload),
    )
    return REFINER_FILE_REMUX_PASS_JOB_KIND


@router.post("/intake/webhook/{source_key}", dependencies=[Depends(_validate_webhook_secret)])
def post_media_manager_intake(
    db: DbSessionDep,
    source_key: Annotated[str, Path(description="Which media manager's payload dialect this body uses.")],
    payload: Annotated[dict[str, Any], Body(...)],
) -> dict[str, Any]:
    """Accept one event from a media manager and hand it to whichever module owns it."""

    dialect = dialect_for_source(source_key)
    if dialect is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown media manager source {source_key!r}. "
                f"Known sources: {', '.join(known_source_keys())}. "
                "Use 'native' for a manager without a dialect of its own."
            ),
        )

    event = dialect.normalize(payload)
    if event is None:
        # Managers send every event they have; most are not ours to act on. Saying so
        # plainly keeps their delivery logs clean instead of showing failed posts.
        return {"status": "ignored", "source": dialect.key}

    enqueued = _enqueue_subtitle_import(db, event) if event.event_kind == "imported" else _enqueue_refine(db, event)
    db.commit()
    return {
        "status": "ok",
        "source": dialect.key,
        "event": event.event_kind,
        "media_scope": event.media_scope,
        "enqueued": enqueued,
    }
