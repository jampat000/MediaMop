"""Refiner HTTP: manual enqueue for ``refiner.supplied_payload_evaluation.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_enqueue import (
    enqueue_refiner_supplied_payload_evaluation_job,
)
from mediamop.modules.refiner.schemas_supplied_payload_evaluation_manual import (
    RefinerSuppliedPayloadEvaluationManualEnqueueIn,
    RefinerSuppliedPayloadEvaluationManualEnqueueOut,
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
    "/refiner/jobs/supplied-payload-evaluation/enqueue",
    response_model=RefinerSuppliedPayloadEvaluationManualEnqueueOut,
)
def post_refiner_supplied_payload_evaluation_enqueue(
    body: RefinerSuppliedPayloadEvaluationManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerSuppliedPayloadEvaluationManualEnqueueOut:
    """Enqueue the supplied-payload evaluation durable job (``refiner_jobs`` only)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    job = enqueue_refiner_supplied_payload_evaluation_job(db)
    db.commit()
    return RefinerSuppliedPayloadEvaluationManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
