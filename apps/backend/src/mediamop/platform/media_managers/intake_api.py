"""One inbound webhook for every media manager: ``POST /api/v1/intake/webhook/{source}``.

The source in the path selects a payload dialect, nothing more. What MediaMop then does
is decided by the event, not by who sent it: a ``handoff`` is Refiner's cue to clean the
file and report back.

``imported`` was Subber's cue to go looking for subtitles. Subber now lives in Deluno,
which owns its own library and does not need telling, so the event is accepted and
ignored rather than refused — a manager configured to send it should not start logging
failed deliveries because a module moved.
"""

from __future__ import annotations

import json
import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_path_settings_service import ensure_refiner_path_settings_row
from mediamop.platform.media_managers.connection_service import (
    connection_for_kind,
    webhook_secret_matches,
)
from mediamop.platform.media_managers.handoff_paths import relative_media_path_for_handoff
from mediamop.platform.media_managers.import_events import (
    MediaManagerImportEvent,
    dialect_for_source,
    known_source_keys,
)

router = APIRouter(tags=["media-manager-intake"])


def _authorise(
    session: Session,
    settings: MediaMopSettings,
    *,
    source_key: str,
    presented: str | None,
) -> None:
    """Check the caller may post as this source.

    A connection's own secret is preferred, so revoking one manager does not lock out
    the others. The instance-wide secret remains the fallback for an install that has
    not created connections yet, and no secret anywhere means no check — the previous
    behaviour, kept so an upgrade does not silently start rejecting a working webhook.
    """

    connection = connection_for_kind(session, source_key)
    if connection is not None and connection.webhook_secret_ciphertext:
        if not webhook_secret_matches(settings, connection, presented):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-Webhook-Secret header.",
            )
        return

    configured = settings.media_manager_webhook_secret
    if not configured:
        return
    provided = (presented or "").strip()
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Webhook-Secret header.",
        )


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


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


@router.post("/intake/webhook/{source_key}")
def post_media_manager_intake(
    db: DbSessionDep,
    settings: SettingsDep,
    source_key: Annotated[str, Path(description="Which media manager's payload dialect this body uses.")],
    payload: Annotated[dict[str, Any], Body(...)],
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
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

    _authorise(db, settings, source_key=dialect.key, presented=x_webhook_secret)

    event = dialect.normalize(payload)
    if event is None:
        # Managers send every event they have; most are not ours to act on. Saying so
        # plainly keeps their delivery logs clean instead of showing failed posts.
        return {"status": "ignored", "source": dialect.key}

    if event.event_kind == "imported":
        # Nothing left in MediaMop acts on an import. Reported the same way as an
        # event we do not recognise, so the manager's delivery log stays clean.
        return {"status": "ignored", "source": dialect.key, "event": event.event_kind}

    enqueued = _enqueue_refine(db, event)
    db.commit()
    return {
        "status": "ok",
        "source": dialect.key,
        "event": event.event_kind,
        "media_scope": event.media_scope,
        "enqueued": enqueued,
    }
