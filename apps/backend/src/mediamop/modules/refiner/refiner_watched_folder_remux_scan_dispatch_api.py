"""Refiner HTTP: manual enqueue for watched-folder remux scan dispatch (``refiner_jobs`` only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_enqueue import (
    enqueue_watched_folder_remux_scan_dispatch_job,
    validate_watched_folder_scan_dispatch_prerequisites,
)
from mediamop.modules.refiner.schemas_watched_folder_remux_scan_dispatch_manual import (
    RefinerWatchedFolderRemuxScanDispatchManualEnqueueIn,
    RefinerWatchedFolderRemuxScanDispatchManualEnqueueOut,
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
    "/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue",
    response_model=RefinerWatchedFolderRemuxScanDispatchManualEnqueueOut,
)
def post_refiner_watched_folder_remux_scan_dispatch_enqueue(
    body: RefinerWatchedFolderRemuxScanDispatchManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerWatchedFolderRemuxScanDispatchManualEnqueueOut:
    """Enqueue one scan of the saved watched folder (manual trigger; Refiner-local)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    ok, err = validate_watched_folder_scan_dispatch_prerequisites(
        db,
        enqueue_remux_jobs=body.enqueue_remux_jobs,
        media_scope=body.media_scope,
    )
    if not ok:
        if err == "no_saved_watched_folder":
            scope = body.media_scope
            label = "TV Refiner" if scope == "tv" else "Movies Refiner"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{label} watched folder is not set in saved path settings. "
                    "This scan reads media files under that folder — configure it first."
                ),
            )
        if err == "missing_output_for_live_remux":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "enqueue_remux_jobs requires a saved output folder for this media scope."
                ),
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scan prerequisites.")

    job = enqueue_watched_folder_remux_scan_dispatch_job(
        db,
        enqueue_remux_jobs=body.enqueue_remux_jobs,
        scan_trigger="manual",
        media_scope=body.media_scope,
    )
    db.commit()
    return RefinerWatchedFolderRemuxScanDispatchManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
