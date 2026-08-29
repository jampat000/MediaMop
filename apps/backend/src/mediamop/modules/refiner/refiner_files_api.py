"""Refiner HTTP: the Files screen — ``/api/v1/refiner/files``.

The screen this serves is the one that answers "why isn't this file processing?", which
Refiner previously could not answer at all: the scan decided and moved on, and the reason
never left the function that produced it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Path, Query, Request
from starlette import status as http_status
from starlette.responses import PlainTextResponse

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_ops import move_refiner_job_to_top
from mediamop.modules.refiner.refiner_file_log_service import logs_for_file, render_log_text
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.refiner_file_state_service import forget_file, list_files, status_counts
from mediamop.modules.refiner.refiner_job_queue_lookup import pending_remux_job_for_relative_path
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_requeue_service import requeue_file, requeue_files
from mediamop.modules.refiner.schemas_refiner_files import (
    RefinerFileForgetIn,
    RefinerFileLogEntryOut,
    RefinerFileLogOut,
    RefinerFileMoveToTopIn,
    RefinerFileMoveToTopOut,
    RefinerFileOut,
    RefinerFileRequeueIn,
    RefinerFilesBulkRequeueIn,
    RefinerFilesPageOut,
    RefinerFileStatusName,
    RefinerRequeueOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["refiner"])


def _log_detail(raw: str) -> dict[str, object]:
    """Parse a stored payload, never raising: a record that cannot be parsed is still
    worth showing, and an exception here would hide the whole file's history."""

    import json as _json

    try:
        parsed = _json.loads(raw or "{}")
    except _json.JSONDecodeError:
        return {"unparsed_detail": raw}
    return parsed if isinstance(parsed, dict) else {"detail": parsed}


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")


@router.get("/refiner/files", response_model=RefinerFilesPageOut)
def get_refiner_files(
    _user: UserPublicDep,
    db: DbSessionDep,
    library_id: int | None = Query(default=None, ge=1),
    file_status: RefinerFileStatusName | None = Query(default=None),
    path_contains: str | None = Query(default=None, max_length=400),
    within_days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=200, ge=1, le=1000),
) -> RefinerFilesPageOut:
    """Files Refiner has seen, with the reason it is or is not working on each."""

    since = datetime.now(UTC) - timedelta(days=within_days) if within_days else None
    rows = list_files(
        db,
        library_id=library_id,
        status=file_status,
        path_contains=path_contains,
        since=since,
        limit=limit,
    )
    names = {row.id: row.name for row in db.query(RefinerLibraryRow).all()}
    files = [
        RefinerFileOut(
            id=row.id,
            library_id=row.library_id,
            library_name=names.get(row.library_id, "Unknown library"),
            relative_path=row.relative_path,
            status=row.status,  # type: ignore[arg-type]
            status_reason=row.status_reason,
            blocked_by_connection=row.blocked_by_connection,
            size_bytes=row.size_bytes,
            last_seen_at=row.last_seen_at,
            last_attempt_at=row.last_attempt_at,
        )
        for row in rows
    ]
    return RefinerFilesPageOut(
        files=files,
        status_counts=status_counts(db, library_id=library_id),
        returned=len(files),
        limit=limit,
    )


@router.delete("/refiner/files/{file_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_refiner_file(
    body: RefinerFileForgetIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    file_id: int = Path(ge=1),
) -> None:
    """Forget a file. Removes MediaMop's record of it, never the file on disk."""

    _verify_csrf(request, settings, body.csrf_token)
    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")
    forget_file(db, row)
    db.commit()


@router.post("/refiner/files/{file_id}/move-to-top", response_model=RefinerFileMoveToTopOut)
def move_refiner_file_to_top(
    body: RefinerFileMoveToTopIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    file_id: int = Path(ge=1),
) -> RefinerFileMoveToTopOut:
    """Put this file's queued work ahead of everything else waiting.

    Only affects work that has not started. A file already being processed cannot be
    started earlier, and saying so is more use than a button that appears to work.
    """

    _verify_csrf(request, settings, body.csrf_token)
    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")

    job = pending_remux_job_for_relative_path(db, relative_path=row.relative_path)
    if job is None:
        db.commit()
        return RefinerFileMoveToTopOut(
            moved=False,
            detail=(
                "There is no queued work for this file to move. It may already be running, or it may not "
                "have been picked up by a scan yet."
            ),
        )

    outcome = move_refiner_job_to_top(db, job_id=int(job.id))
    db.commit()
    if outcome != "ok":
        return RefinerFileMoveToTopOut(
            moved=False,
            detail="This file's work has already started, so it cannot be moved ahead of anything.",
        )
    return RefinerFileMoveToTopOut(
        moved=True,
        detail="Moved to the front of the queue. It starts as soon as there is capacity for it.",
    )


@router.post("/refiner/files/{file_id}/requeue", response_model=RefinerRequeueOut)
def requeue_refiner_file(
    body: RefinerFileRequeueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    file_id: int = Path(ge=1),
) -> RefinerRequeueOut:
    """Try this file again now.

    A manual requeue resets the attempt count and ignores the backoff: whoever asked has
    usually just fixed the thing that broke, so making them wait it out — or refusing
    because the automatic attempts are spent — would answer a question they did not ask.
    """

    _verify_csrf(request, settings, body.csrf_token)
    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")
    result = requeue_file(db, row=row, manual=True)
    db.commit()
    return RefinerRequeueOut(requeued=result.requeued, skipped=result.skipped, detail=result.detail)


@router.post("/refiner/files/requeue", response_model=RefinerRequeueOut)
def requeue_refiner_files(
    body: RefinerFilesBulkRequeueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerRequeueOut:
    """Try every file matching this filter again.

    The filter is the same one the list uses, and ``limit`` is a ceiling rather than a
    page size: a mis-typed filter should not be able to queue a whole library.
    """

    _verify_csrf(request, settings, body.csrf_token)
    rows = list_files(
        db,
        library_id=body.library_id,
        status=body.file_status,
        path_contains=body.path_contains,
        limit=body.limit,
    )
    result = requeue_files(db, rows=rows)
    db.commit()
    return RefinerRequeueOut(requeued=result.requeued, skipped=result.skipped, detail=result.detail)


@router.get("/refiner/files/{file_id}/log", response_model=RefinerFileLogOut)
def get_refiner_file_log(
    _user: UserPublicDep,
    db: DbSessionDep,
    file_id: int = Path(ge=1),
    limit: int = Query(default=50, ge=1, le=500),
) -> RefinerFileLogOut:
    """Everything MediaMop retained about what it did to this file, newest first."""

    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")
    operator = ensure_refiner_operator_settings_row(db)
    rows = logs_for_file(db, file_id=file_id, limit=limit)
    db.commit()
    return RefinerFileLogOut(
        file_id=file_id,
        relative_path=row.relative_path,
        retention_days=int(operator.file_log_retention_days),
        entries=[
            RefinerFileLogEntryOut(
                id=entry.id,
                recorded_at=entry.recorded_at,
                outcome=entry.outcome,
                title=entry.title,
                library_name=entry.library_name,
                detail=_log_detail(entry.detail_json),
            )
            for entry in rows
        ],
    )


@router.get("/refiner/files/{file_id}/log/download")
def download_refiner_file_log(
    _user: UserPublicDep,
    db: DbSessionDep,
    file_id: int = Path(ge=1),
) -> PlainTextResponse:
    """The same record as plain text, for attaching to a bug report.

    Text rather than raw JSON: the reason anyone downloads this is to send it to somebody
    else, and minified JSON is not something a person reads in a forum post.
    """

    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")
    rows = logs_for_file(db, file_id=file_id, limit=500)
    db.commit()
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in row.relative_path)[-80:].strip("-") or "file"
    return PlainTextResponse(
        render_log_text(rows),
        headers={"Content-Disposition": f'attachment; filename="mediamop-{safe}.log.txt"'},
    )
