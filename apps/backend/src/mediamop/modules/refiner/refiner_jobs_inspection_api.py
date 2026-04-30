"""HTTP: read-only ``refiner_jobs`` inspection + pending-only cancel (Refiner lane)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.jobs_model import RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import cancel_pending_refiner_job
from mediamop.modules.refiner.refiner_jobs_inspection_service import (
    list_refiner_jobs_for_inspection,
    validate_refiner_inspection_statuses,
)
from mediamop.modules.refiner.schemas_refiner_jobs_inspection import (
    RefinerJobCancelPendingIn,
    RefinerJobCancelPendingOut,
    RefinerJobsInspectionOut,
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
                "Optional filter by persisted status (repeat param). "
                "Omit to return the newest rows across all statuses (pending, leased, terminal, cancelled)."
            ),
        ),
    ] = None,
) -> RefinerJobsInspectionOut:
    """Refiner: read-only persisted ``refiner_jobs`` rows (all Refiner ``job_kind`` values on this lane)."""

    if statuses:
        try:
            st = validate_refiner_inspection_statuses(tuple(statuses))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return list_refiner_jobs_for_inspection(db, limit=limit, statuses=st)
    return list_refiner_jobs_for_inspection(db, limit=limit, statuses=None)


@router.post(
    "/refiner/jobs/{job_id}/cancel-pending",
    response_model=RefinerJobCancelPendingOut,
)
def post_refiner_job_cancel_pending(
    job_id: int,
    body: RefinerJobCancelPendingIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerJobCancelPendingOut:
    """Abandon a **pending** row only — refuses leased, completed, failed, or cancelled jobs."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    outcome = cancel_pending_refiner_job(db, job_id=job_id)
    if outcome == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refiner job not found.")
    if outcome == "wrong_status":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending jobs can be cancelled (not leased, completed, failed, or already cancelled).",
        )
    db.commit()
    return RefinerJobCancelPendingOut(job_id=job_id, status=RefinerJobStatus.CANCELLED.value)
