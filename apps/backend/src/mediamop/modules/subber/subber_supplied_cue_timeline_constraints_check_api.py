"""Subber HTTP: manual enqueue for cue timeline constraint check (``subber_jobs`` only)."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.subber.schemas_cue_timeline_constraints_manual import (
    SubberSuppliedCueTimelineConstraintsCheckManualEnqueueIn,
    SubberSuppliedCueTimelineConstraintsCheckManualEnqueueOut,
)
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_check_job_kinds import (
    SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)

router = APIRouter(tags=["subber"])


@router.post(
    "/subber/jobs/cue-timeline-constraints-check/enqueue",
    response_model=SubberSuppliedCueTimelineConstraintsCheckManualEnqueueOut,
)
def post_subber_supplied_cue_timeline_constraints_check_enqueue(
    body: SubberSuppliedCueTimelineConstraintsCheckManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> SubberSuppliedCueTimelineConstraintsCheckManualEnqueueOut:
    """Enqueue one payload-only evaluation of cue display intervals (not OCR, download, sync, or mux)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    payload = {
        "cues": [{"start_sec": c.start_sec, "end_sec": c.end_sec} for c in body.cues],
        "source_duration_sec": body.source_duration_sec,
    }
    dedupe_key = f"{SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND}:{uuid4().hex}"
    job = subber_enqueue_or_get_job(
        db,
        dedupe_key=dedupe_key,
        job_kind=SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )
    db.commit()
    return SubberSuppliedCueTimelineConstraintsCheckManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
