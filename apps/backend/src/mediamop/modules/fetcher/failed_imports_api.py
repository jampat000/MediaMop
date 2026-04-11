"""Fetcher-owned HTTP API for Radarr/Sonarr download-queue failed-import task workflow.

Persistence still uses ``refiner_jobs`` and Refiner worker plumbing; planning and live-queue drives live
under ``mediamop.modules.fetcher`` with shared classification/policy in ``mediamop.modules.arr_failed_import``.
This module is the product-facing boundary only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from starlette import status
from sqlalchemy.orm import Session

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.automation_summary_service import (
    build_fetcher_failed_import_automation_summary,
)
from mediamop.modules.fetcher.cleanup_policy_service import (
    load_fetcher_failed_import_cleanup_bundle,
    upsert_fetcher_failed_import_cleanup_policy,
)
from mediamop.modules.fetcher.failed_import_activity import (
    record_fetcher_failed_import_pass_queued,
    record_fetcher_failed_import_recovered,
)
from mediamop.modules.fetcher.schemas_automation_summary import FetcherFailedImportAutomationSummaryOut
from mediamop.modules.fetcher.schemas_cleanup_policy import (
    FailedImportCleanupPolicyAxisOut,
    FetcherFailedImportCleanupPolicyOut,
    FetcherFailedImportCleanupPolicyPutIn,
)
from mediamop.modules.arr_failed_import.env_settings import AppFailedImportCleanupPolicySettings
from mediamop.modules.refiner.inspection_service import (
    DEFAULT_TERMINAL_STATUSES,
    list_refiner_jobs_for_inspection,
    validate_inspection_statuses,
)
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import recover_handler_ok_finalize_failed_to_completed
from mediamop.modules.fetcher.manual_cleanup_drive_enqueue import (
    manual_enqueue_radarr_cleanup_drive,
    manual_enqueue_sonarr_cleanup_drive,
)
from mediamop.modules.refiner.runtime_visibility import refiner_runtime_visibility_from_settings
from mediamop.modules.refiner.schemas_inspection import RefinerJobsInspectionOut
from mediamop.modules.fetcher.schemas_manual_cleanup_enqueue import (
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


def _axis_out(app: AppFailedImportCleanupPolicySettings) -> FailedImportCleanupPolicyAxisOut:
    return FailedImportCleanupPolicyAxisOut(
        remove_quality_rejections=app.remove_quality_rejections,
        remove_unmatched_manual_import_rejections=app.remove_unmatched_manual_import_rejections,
        remove_corrupt_imports=app.remove_corrupt_imports,
        remove_failed_downloads=app.remove_failed_downloads,
        remove_failed_imports=app.remove_failed_imports,
    )


def _cleanup_policy_response(
    db: Session,
    settings: MediaMopSettings,
) -> FetcherFailedImportCleanupPolicyOut:
    effective, row = load_fetcher_failed_import_cleanup_bundle(db, settings.refiner_failed_import_cleanup)
    return FetcherFailedImportCleanupPolicyOut(
        movies=_axis_out(effective.radarr),
        tv_shows=_axis_out(effective.sonarr),
        updated_at=row.updated_at,
    )


@router.get(
    "/fetcher/failed-imports/cleanup-policy",
    response_model=FetcherFailedImportCleanupPolicyOut,
)
def get_fetcher_failed_imports_cleanup_policy(
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> FetcherFailedImportCleanupPolicyOut:
    """Fetcher: read effective removal rules for Radarr/Sonarr download-queue failed-import passes."""

    return _cleanup_policy_response(db, settings)


@router.put(
    "/fetcher/failed-imports/cleanup-policy",
    response_model=FetcherFailedImportCleanupPolicyOut,
)
def put_fetcher_failed_imports_cleanup_policy(
    body: FetcherFailedImportCleanupPolicyPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> FetcherFailedImportCleanupPolicyOut:
    """Fetcher: persist removal rules (movies and TV are independent)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    upsert_fetcher_failed_import_cleanup_policy(
        db,
        env_bundle=settings.refiner_failed_import_cleanup,
        radarr=body.movies.to_app_settings(),
        sonarr=body.tv_shows.to_app_settings(),
    )
    return _cleanup_policy_response(db, settings)


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
    """Fetcher: add a movies (Radarr) download-queue failed-import pass for the worker (deduped). Does not run the pass here."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    job, outcome = manual_enqueue_radarr_cleanup_drive(db)
    record_fetcher_failed_import_pass_queued(
        db,
        movies=True,
        source="manual",
        queue_outcome=outcome,
    )
    return ManualCleanupDriveEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
        queue_outcome=outcome,
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
    """Fetcher: add a TV (Sonarr) download-queue failed-import pass for the worker (deduped). Does not run the pass here."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    job, outcome = manual_enqueue_sonarr_cleanup_drive(db)
    record_fetcher_failed_import_pass_queued(
        db,
        movies=False,
        source="manual",
        queue_outcome=outcome,
    )
    return ManualCleanupDriveEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
        queue_outcome=outcome,
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
    job_row = db.get(RefinerJob, job_id)
    if job_row is not None:
        record_fetcher_failed_import_recovered(db, job_id=job_id, job_kind=job_row.job_kind)
    return RecoverFinalizeFailureOut(
        job_id=job_id,
        status=RefinerJobStatus.COMPLETED.value,
    )
