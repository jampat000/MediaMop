"""Authenticated Refiner operational routes (read + narrow manual recovery)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.inspection_service import (
    DEFAULT_TERMINAL_STATUSES,
    list_refiner_jobs_for_inspection,
    validate_inspection_statuses,
)
from mediamop.modules.refiner.jobs_model import RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import recover_handler_ok_finalize_failed_to_completed
from mediamop.modules.refiner.runtime_visibility import refiner_runtime_visibility_from_settings
from mediamop.modules.refiner.schemas_inspection import RefinerJobsInspectionOut
from mediamop.modules.refiner.schemas_recovery import RecoverFinalizeFailureIn, RecoverFinalizeFailureOut
from mediamop.modules.refiner.schemas_runtime_visibility import RefinerRuntimeVisibilityOut
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["refiner"])


@router.get("/refiner/runtime/visibility", response_model=RefinerRuntimeVisibilityOut)
def get_refiner_runtime_visibility(
    _user: UserPublicDep,
    settings: SettingsDep,
) -> RefinerRuntimeVisibilityOut:
    """Read-only Refiner runtime **configuration** (workers + cleanup-drive schedules).

    Does not report asyncio task liveness or external connectivity.
    """

    return refiner_runtime_visibility_from_settings(settings)


@router.get("/refiner/jobs/inspection", response_model=RefinerJobsInspectionOut)
def get_refiner_jobs_inspection(
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
    """Read-only job rows for operator inspection — ``handler_ok_finalize_failed`` is explicit, not folded into ``failed``."""

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
    "/refiner/jobs/{job_id}/recover-finalize-failure",
    response_model=RecoverFinalizeFailureOut,
)
def post_recover_finalize_failure(
    job_id: int,
    body: RecoverFinalizeFailureIn,
    request: Request,
    user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RecoverFinalizeFailureOut:
    """Manual recovery: ``handler_ok_finalize_failed`` → ``completed`` without re-running the handler."""

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refiner job not found.")
    if outcome == "wrong_status":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not in handler_ok_finalize_failed state.",
        )
    return RecoverFinalizeFailureOut(
        job_id=job_id,
        status=RefinerJobStatus.COMPLETED.value,
    )
