"""Fetcher-owned HTTP API for Radarr/Sonarr download-queue failed-import task workflow.

Implementation still lives under ``mediamop.modules.refiner`` services and ``refiner_jobs`` — this module is the
product-facing boundary only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.fetcher.automation_summary_service import (
    build_fetcher_failed_import_automation_summary,
)
from mediamop.modules.fetcher.schemas_automation_summary import FetcherFailedImportAutomationSummaryOut
from mediamop.modules.refiner.inspection_service import (
    DEFAULT_TERMINAL_STATUSES,
    list_refiner_jobs_for_inspection,
    validate_inspection_statuses,
)
from mediamop.modules.refiner.jobs_model import RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import recover_handler_ok_finalize_failed_to_completed
from mediamop.modules.refiner.manual_cleanup_drive_enqueue import (
    manual_enqueue_radarr_cleanup_drive,
    manual_enqueue_sonarr_cleanup_drive,
)
from mediamop.modules.refiner.runtime_visibility import refiner_runtime_visibility_from_settings
from mediamop.modules.refiner.schemas_inspection import RefinerJobsInspectionOut
from mediamop.modules.refiner.schemas_manual_cleanup_enqueue import (
    ManualCleanupDriveEnqueueIn,
    ManualCleanupDriveEnqueueOut,
)
from mediamop.modules.refiner.schemas_recovery import RecoverFinalizeFailureIn, RecoverFinalizeFailureOut
from mediamop.modules.refiner.schemas_runtime_visibility import RefinerRuntimeVisibilityOut
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["fetcher"])


@router.get(
    "/fetcher/failed-imports/automation-summary",
    response_model=FetcherFailedImportAutomationSummaryOut,
)
def get_fetcher_failed_imports_automation_summary(
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> FetcherFailedImportAutomationSummaryOut:
    """Fetcher: read-only last finished passes (per app) + saved schedule wording — persisted/settings only."""

    return build_fetcher_failed_import_automation_summary(db, settings)


@router.get("/fetcher/failed-imports/settings", response_model=RefinerRuntimeVisibilityOut)
def get_fetcher_failed_imports_settings(
    _user: UserPublicDep,
    settings: SettingsDep,
) -> RefinerRuntimeVisibilityOut:
    """Fetcher: read-only settings for in-process workers and Radarr/Sonarr timed failed-import passes.

    Does not report live worker health, pass execution, or app connectivity.
    """

    return refiner_runtime_visibility_from_settings(settings)


@router.get("/fetcher/failed-imports/inspection", response_model=RefinerJobsInspectionOut)
def get_fetcher_failed_imports_inspection(
    _user: UserPublicDep,
    db: DbSessionDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Max rows to return.")] = 50,
    statuses: Annotated[
        list[str] | None,
        Query(
            alias="status",
            description=(
                "Filter by persisted status (repeat param). "
                "Omit to return only terminal rows: completed, failed, handler_ok_finalize_failed."
            ),
        ),
    ] = None,
) -> RefinerJobsInspectionOut:
    """Fetcher: read-only persisted rows for the failed-import queue workflow."""

    if statuses:
        try:
            st = validate_inspection_statuses(tuple(statuses))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return list_refiner_jobs_for_inspection(
            db,
            limit=limit,
            statuses=st,
            default_terminal_only=False,
        )
    return list_refiner_jobs_for_inspection(
        db,
        limit=limit,
        statuses=DEFAULT_TERMINAL_STATUSES,
        default_terminal_only=True,
    )


@router.post(
    "/fetcher/failed-imports/radarr/enqueue",
    response_model=ManualCleanupDriveEnqueueOut,
)
def post_fetcher_failed_imports_radarr_enqueue(
    body: ManualCleanupDriveEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ManualCleanupDriveEnqueueOut:
    """Fetcher: enqueue movies (Radarr) download-queue failed-import pass (deduped). Does not run processing here."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    job, outcome = manual_enqueue_radarr_cleanup_drive(db)
    return ManualCleanupDriveEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
        enqueue_outcome=outcome,
    )


@router.post(
    "/fetcher/failed-imports/sonarr/enqueue",
    response_model=ManualCleanupDriveEnqueueOut,
)
def post_fetcher_failed_imports_sonarr_enqueue(
    body: ManualCleanupDriveEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ManualCleanupDriveEnqueueOut:
    """Fetcher: enqueue TV (Sonarr) download-queue failed-import pass (deduped). Does not run processing here."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    job, outcome = manual_enqueue_sonarr_cleanup_drive(db)
    return ManualCleanupDriveEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
        enqueue_outcome=outcome,
    )


@router.post(
    "/fetcher/failed-imports/tasks/{job_id}/recover-finalize-failure",
    response_model=RecoverFinalizeFailureOut,
)
def post_fetcher_failed_imports_recover_finalize_failure(
    job_id: int,
    body: RecoverFinalizeFailureIn,
    request: Request,
    user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RecoverFinalizeFailureOut:
    """Fetcher: manual recovery handler_ok_finalize_failed → completed without re-running the handler."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    label = f"username={user.username} role={user.role}"
    outcome = recover_handler_ok_finalize_failed_to_completed(
        db,
        job_id=job_id,
        recovered_by_label=label,
    )
    if outcome == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fetcher task not found.")
    if outcome == "wrong_status":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not in handler_ok_finalize_failed state (needs manual finish only).",
        )
    return RecoverFinalizeFailureOut(
        job_id=job_id,
        status=RefinerJobStatus.COMPLETED.value,
    )
