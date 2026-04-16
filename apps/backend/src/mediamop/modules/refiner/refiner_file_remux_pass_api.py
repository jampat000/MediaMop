"""Refiner HTTP: manual enqueue for per-file remux pass (``refiner_jobs`` only)."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_path_settings_service import ensure_refiner_path_settings_row
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.schemas_file_remux_pass_manual import (
    RefinerFileRemuxPassManualEnqueueIn,
    RefinerFileRemuxPassManualEnqueueOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
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
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    row = ensure_refiner_path_settings_row(db)
    scope = body.media_scope
    watched_ok = (
        (row.refiner_tv_watched_folder or "").strip() if scope == "tv" else (row.refiner_watched_folder or "").strip()
    )
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
