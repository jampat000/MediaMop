"""Enqueue durable Refiner Pass 4 failure-cleanup sweeps."""

from __future__ import annotations

import json
from typing import Literal

from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_failure_cleanup_job_kinds import (
    REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_DEDUPE_KEY,
    REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND,
    REFINER_TV_FAILURE_CLEANUP_SWEEP_DEDUPE_KEY,
    REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND,
)

RefinerFailureCleanupScope = Literal["movie", "tv"]


def enqueue_refiner_failure_cleanup_sweep_job(
    session: Session,
    *,
    media_scope: RefinerFailureCleanupScope,
) -> None:
    ms = "tv" if str(media_scope).strip().lower() == "tv" else "movie"
    job_kind = REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND if ms == "tv" else REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND
    dedupe = REFINER_TV_FAILURE_CLEANUP_SWEEP_DEDUPE_KEY if ms == "tv" else REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_DEDUPE_KEY
    payload_json = json.dumps({"media_scope": ms}, separators=(",", ":"))
    refiner_enqueue_or_get_job(
        session,
        dedupe_key=dedupe,
        job_kind=job_kind,
        payload_json=payload_json,
    )

