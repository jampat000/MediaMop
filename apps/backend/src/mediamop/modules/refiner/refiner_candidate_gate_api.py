"""Refiner HTTP: manual enqueue for candidate gate (``refiner_jobs`` only)."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_candidate_gate_job_kinds import REFINER_CANDIDATE_GATE_JOB_KIND
from mediamop.modules.refiner.schemas_candidate_gate_manual import (
    RefinerCandidateGateManualEnqueueIn,
    RefinerCandidateGateManualEnqueueOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)

router = APIRouter(tags=["refiner"])


@router.post(
    "/refiner/jobs/candidate-gate/enqueue",
    response_model=RefinerCandidateGateManualEnqueueOut,
)
def post_refiner_candidate_gate_enqueue(
    body: RefinerCandidateGateManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerCandidateGateManualEnqueueOut:
    """Refiner: enqueue one ownership / upstream-blocking evaluation against the live *arr queue."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    payload = {
        "target": body.target,
        "release_title": body.release_title,
        "release_year": body.release_year,
        "output_path": body.output_path,
        "movie_id": body.movie_id,
        "series_id": body.series_id,
    }
    dedupe_key = f"{REFINER_CANDIDATE_GATE_JOB_KIND}:{uuid4().hex}"
    job = refiner_enqueue_or_get_job(
        db,
        dedupe_key=dedupe_key,
        job_kind=REFINER_CANDIDATE_GATE_JOB_KIND,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )
    db.commit()
    return RefinerCandidateGateManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
