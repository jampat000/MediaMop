"""Enqueue durable ``refiner.work_temp_stale_sweep.v1`` rows on ``refiner_jobs`` (per scope)."""

from __future__ import annotations

import json
from typing import Literal

from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_temp_cleanup import normalize_work_temp_sweep_media_scope
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_job_kinds import (
    REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,
    refiner_work_temp_stale_sweep_dedupe_key_for_scope,
)

RefinerWorkTempStaleSweepEnqueueScope = Literal["movie", "tv"]


def enqueue_refiner_work_temp_stale_sweep_job(
    session: Session,
    *,
    media_scope: RefinerWorkTempStaleSweepEnqueueScope,
    dry_run: bool = False,
) -> None:
    """Insert or return the periodic row for **one** scope (Movies vs TV dedupe keys are distinct)."""

    ms = normalize_work_temp_sweep_media_scope(media_scope)
    body = json.dumps({"dry_run": bool(dry_run), "media_scope": ms}, separators=(",", ":"))
    refiner_enqueue_or_get_job(
        session,
        dedupe_key=refiner_work_temp_stale_sweep_dedupe_key_for_scope(ms),
        job_kind=REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,
        payload_json=body,
    )
