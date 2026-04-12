"""Enqueue durable ``refiner.supplied_payload_evaluation.v1`` rows on ``refiner_jobs``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_job_kinds import (
    REFINER_SUPPLIED_PAYLOAD_EVALUATION_DEDUPE_KEY,
    REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND,
)


def enqueue_refiner_supplied_payload_evaluation_job(session: Session) -> RefinerJob:
    """Insert or return the singleton row (dedupe key is family-owned)."""

    return refiner_enqueue_or_get_job(
        session,
        dedupe_key=REFINER_SUPPLIED_PAYLOAD_EVALUATION_DEDUPE_KEY,
        job_kind=REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND,
    )
