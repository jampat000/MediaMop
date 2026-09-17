"""One inbound webhook for every media manager: ``POST /api/v1/intake/webhook/{source}``.

The source in the path selects a payload dialect, nothing more. What Weir then does
is decided by the event, not by who sent it: a ``handoff`` is Refiner's cue to clean the
file and report back.

``imported`` was Subber's cue to go looking for subtitles. Subber now lives in Deluno,
which owns its own library and does not need telling, so the event is accepted and
ignored rather than refused — a manager configured to send it should not start logging
failed deliveries because a module moved.
"""

from __future__ import annotations

import json
import re
import secrets
import uuid
from pathlib import Path as FsPath
from pathlib import PurePath
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from weir.api.deps import DbSessionDep, SettingsDep
from weir.core.config import WeirSettings
from weir.platform.activity import constants as activity_constants
from weir.platform.activity import service as activity_service
from weir.platform.media_managers.connection_model import MediaManagerConnectionRow
from weir.platform.media_managers.connection_service import (
    connection_for_kind,
    webhook_secret_matches,
)
from weir.platform.media_managers.handoff_ledger import (
    cancel_handoff,
    current_status,
    find_handoff,
    record_handoff_received,
)
from weir.platform.media_managers.handoff_paths import HandoffPathResult, relative_media_path_for_handoff
from weir.platform.media_managers.import_events import (
    MediaManagerImportEvent,
    dialect_for_source,
    known_source_keys,
)
from weir.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from weir.refiner.jobs_ops import refiner_enqueue_or_get_job
from weir.refiner.refiner_library_model import RefinerLibraryRow
from weir.refiner.refiner_library_service import list_libraries, resolve_library
from weir.refiner.refiner_remux_rules import is_refiner_media_candidate

router = APIRouter(tags=["media-manager-intake"])


def _authorise(
    session: Session,
    settings: WeirSettings,
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


def _library_for_handoff(
    session: Session, event: MediaManagerImportEvent
) -> tuple[RefinerLibraryRow | None, HandoffPathResult]:
    """The library whose watched folder holds the file, and the file's path relative to it.

    Chosen by folder, not by media type (#460): with two film libraries, the first one of that
    type is not necessarily the one the manager dropped the file into. When several watched
    folders contain the file (one nested in another), the deepest wins, and a library of the
    hand-off's media type is preferred over one of the other type.
    """

    candidates = []
    for library in list_libraries(session):
        resolved = relative_media_path_for_handoff(watched_folder=library.watched_folder, file_path=event.file_path)
        if resolved.ok:
            depth = len([p for p in (library.watched_folder or "").replace("\\", "/").split("/") if p])
            candidates.append((library.media_type == event.media_scope, depth, -library.id, library, resolved))
    if candidates:
        _, _, _, library, resolved = max(candidates, key=lambda c: (c[0], c[1], c[2]))
        return library, resolved
    # Nothing contains it: explain against the library of this media type, as before.
    fallback = resolve_library(session, media_scope=event.media_scope)
    watched = (fallback.watched_folder or "") if fallback is not None else ""
    return fallback, relative_media_path_for_handoff(watched_folder=watched, file_path=event.file_path)


_SAMPLE_PART = re.compile(r"(^|[^a-z0-9])sample([^a-z0-9]|$)", re.IGNORECASE)


def _handoff_media_files(library: RefinerLibraryRow | None, relative_path: str) -> list[str]:
    """The files a hand-off asks Weir to process, relative to the watched folder.

    A manager may name a single file or the completed download's *folder*. A folder means the video
    files inside it, samples left out: a manager importing exactly one video from the processed
    output would otherwise find a processed sample beside the film and stop to ask a person.
    """

    if library is None or not relative_path:
        return [relative_path]
    folder = FsPath(library.watched_folder or "") / relative_path
    try:
        if not folder.is_dir():
            return [relative_path]
        videos = sorted(p for p in folder.rglob("*") if p.is_file() and is_refiner_media_candidate(p))
    except OSError:
        return [relative_path]
    main = [p for p in videos if not any(_SAMPLE_PART.search(part) for part in p.relative_to(folder).parts)]
    chosen = main or videos
    if not chosen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The hand-off names the folder {relative_path!r}, but it holds no video file Weir processes. "
                "Nothing was queued."
            ),
        )
    return [PurePath(relative_path, p.relative_to(folder)).as_posix() for p in chosen]


def _enqueue_refine(session: Session, event: MediaManagerImportEvent) -> str:
    library, resolved = _library_for_handoff(session, event)
    if not resolved.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=resolved.problem)

    payload: dict[str, Any] = {
        "relative_media_path": resolved.relative_media_path,
        # The job's cleanup shape follows the library it landed in, not what the manager called it.
        "media_scope": library.media_type if library is not None else event.media_scope,
        "trigger": "webhook",
    }
    if library is not None:
        payload["library_id"] = library.id
    # Carried on the job so the completion report can find its way home without a
    # second table: the job row already persists its payload across restarts.
    if event.handoff_id or event.callback_path:
        payload["origin"] = {
            "source_key": event.source_key,
            "handoff_id": event.handoff_id,
            "callback_path": event.callback_path,
            "release_name": event.release_name,
            "library_id": event.library_id,
        }

    targets = _handoff_media_files(library, resolved.relative_media_path or "")

    # The manager's own idempotency key when it gave us one, so a repeated hand-off
    # after a restart returns the existing job instead of remuxing the file twice.
    base_key = (
        f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:{event.source_key}:handoff:{event.handoff_id}"
        if event.handoff_id
        else f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:{uuid.uuid4().hex}"
    )
    for target in targets:
        # One file keeps the plain key; a folder's files are keyed apart so each runs once.
        dedupe_key = (
            base_key if len(targets) == 1 and target == resolved.relative_media_path else f"{base_key}:{target}"
        )
        refiner_enqueue_or_get_job(
            session,
            dedupe_key=dedupe_key,
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=_compact_json({**payload, "relative_media_path": target}),
        )
    if event.handoff_id:
        # So the manager can ask about this hand-off for as long as it cares, not just while
        # the job row exists (#480).
        record_handoff_received(
            session,
            source_key=event.source_key,
            handoff_id=event.handoff_id,
            library_id=library.id if library is not None else None,
            relative_path=resolved.relative_media_path or "",
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
        # Nothing left in Weir acts on an import. Reported the same way as an
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


# --- a manager asking about a hand-off it gave us (#480, Deluno#511) ---------------------------

_NEEDS_SECRET = "Set a webhook secret in Weir so a media manager can ask about hand-offs."
HANDOFF_CAPABILITIES: tuple[str, ...] = ("handoff-status", "handoff-cancel")


def _require_secret(
    session: Session,
    settings: WeirSettings,
    *,
    presented: str | None,
    source_key: str | None,
) -> None:
    """These routes reveal file paths, so unlike the intake webhook they never run unauthenticated.

    No secret configured anywhere is a 403 with the reason, not a 404: the manager should tell
    its operator what to set, not conclude the hand-off does not exist.
    """

    provided = (presented or "").strip()
    rows = list(
        session.scalars(
            select(MediaManagerConnectionRow).where(
                MediaManagerConnectionRow.enabled.is_(True),
                MediaManagerConnectionRow.webhook_secret_ciphertext.is_not(None),
            )
        )
    )
    if source_key is not None:
        rows = [row for row in rows if row.kind == source_key]
    configured = settings.media_manager_webhook_secret
    if not rows and not configured:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NEEDS_SECRET)
    if provided:
        if any(webhook_secret_matches(settings, row, provided) for row in rows):
            return
        if configured and secrets.compare_digest(provided, configured):
            return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-Webhook-Secret header.",
    )


def _source(source_key: str) -> str:
    dialect = dialect_for_source(source_key)
    if dialect is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown media manager source {source_key!r}.",
        )
    return dialect.key


@router.get("/intake/capabilities")
def get_intake_capabilities(
    db: DbSessionDep,
    settings: SettingsDep,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> dict[str, list[str]]:
    """What a media manager may ask Weir about its hand-offs."""

    _require_secret(db, settings, presented=x_webhook_secret, source_key=None)
    return {"capabilities": list(HANDOFF_CAPABILITIES)}


@router.get("/intake/handoffs/{source_key}/{handoff_id}")
def get_intake_handoff(
    db: DbSessionDep,
    settings: SettingsDep,
    source_key: Annotated[str, Path(description="The manager that gave Weir the hand-off.")],
    handoff_id: Annotated[str, Path(description="The manager's own hand-off id.")],
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> dict[str, object]:
    """Where a hand-off is: queued, scheduled, working, or how it ended. 404 means never received."""

    key = _source(source_key)
    _require_secret(db, settings, presented=x_webhook_secret, source_key=key)
    row = find_handoff(db, source_key=key, handoff_id=handoff_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weir has never received this hand-off.",
        )
    answer = current_status(db, row)
    db.commit()
    return answer.as_json()


@router.delete("/intake/handoffs/{source_key}/{handoff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_intake_handoff(
    db: DbSessionDep,
    settings: SettingsDep,
    source_key: Annotated[str, Path(description="The manager that gave Weir the hand-off.")],
    handoff_id: Annotated[str, Path(description="The manager's own hand-off id.")],
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> Response:
    """Drop a hand-off Weir has not started. Refuses (409) once work has begun; never touches a file."""

    key = _source(source_key)
    _require_secret(db, settings, presented=x_webhook_secret, source_key=key)
    row = find_handoff(db, source_key=key, handoff_id=handoff_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weir has never received this hand-off.",
        )
    cancelled, sentence = cancel_handoff(db, row)
    if not cancelled:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=sentence)
    activity_service.record_activity_event(
        db,
        event_type=activity_constants.REFINER_HANDOFF_CANCELLED,
        module="refiner",
        title=f"{key.capitalize()} cancelled its hand-off of {PurePath(row.relative_path).name}",
        detail=json.dumps(
            {
                "source": key,
                "handoff_id": handoff_id,
                "relative_media_path": row.relative_path,
                "library_id": row.library_id,
                "trigger": "webhook",
                "result": "success",
                "message": sentence,
            },
            separators=(",", ":"),
        ),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
