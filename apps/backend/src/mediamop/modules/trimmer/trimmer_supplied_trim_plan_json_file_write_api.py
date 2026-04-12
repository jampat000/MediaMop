"""Trimmer HTTP: manual enqueue for supplied trim plan JSON file write (``trimmer_jobs`` only)."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.trimmer.schemas_trim_plan_json_file_write_manual import (
    TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueIn,
    TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueOut,
)
from mediamop.modules.trimmer.trimmer_jobs_ops import trimmer_enqueue_or_get_job
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_job_kinds import (
    TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)

router = APIRouter(tags=["trimmer"])


@router.post(
    "/trimmer/jobs/supplied-trim-plan-json-file-write/enqueue",
    response_model=TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueOut,
)
def post_trimmer_supplied_trim_plan_json_file_write_enqueue(
    body: TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueOut:
    """Enqueue one validated trim plan write as JSON under ``MEDIAMOP_HOME/trimmer/plan_exports/`` (no transcode)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    payload = {
        "segments": [{"start_sec": s.start_sec, "end_sec": s.end_sec} for s in body.segments],
        "source_duration_sec": body.source_duration_sec,
    }
    dedupe_key = f"{TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND}:{uuid4().hex}"
    job = trimmer_enqueue_or_get_job(
        db,
        dedupe_key=dedupe_key,
        job_kind=TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )
    db.commit()
    return TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
