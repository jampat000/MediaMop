"""Refiner HTTP: manual enqueue for per-file remux pass (``refiner_jobs`` only)."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_library_service import resolve_library
from mediamop.modules.refiner.schemas_file_remux_pass_manual import (
    RefinerFileRemuxPassManualEnqueueIn,
    RefinerFileRemuxPassManualEnqueueOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)

router = APIRouter(tags=["refiner"])


@router.post(
    "/refiner/jobs/file-remux-pass/enqueue",
    response_model=RefinerFileRemuxPassManualEnqueueOut,
)
def post_refiner_file_remux_pass_enqueue(
    body: RefinerFileRemuxPassManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerFileRemuxPassManualEnqueueOut:
    """Enqueue one live ffprobe + remux-plan + optional ffmpeg pass."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    scope = body.media_scope
    library = resolve_library(db, library_id=body.library_id, media_scope=scope)
    if body.library_id is not None and (library is None or library.id != body.library_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected Refiner library no longer exists. Refresh Libraries and try again.",
        )
    watched_ok = (library.watched_folder or "").strip() if library is not None else ""
    if not watched_ok:
        label = "TV Refiner" if scope == "tv" else "Movies Refiner"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{label} watched folder is not set in saved path settings. "
                "Manual refiner.file.remux_pass.v1 jobs require it to resolve relative_media_path and for bounded source cleanup. "
                "Saving Refiner path settings does not require a watched folder, but you must configure it before enqueueing this job kind."
            ),
        )

    payload = {
        "relative_media_path": body.relative_media_path.strip(),
        "media_scope": scope,
        "library_id": library.id if library is not None else body.library_id,
    }
    dedupe_key = f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:{uuid4().hex}"
    job = refiner_enqueue_or_get_job(
        db,
        dedupe_key=dedupe_key,
        job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )
    db.commit()
    return RefinerFileRemuxPassManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
