"""Operator-triggered add of Radarr/Sonarr failed-import download-queue pass jobs (Fetcher API support).

Calls enqueue helpers in this package only — no handler execution in-request.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    enqueue_sonarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.refiner.jobs_model import RefinerJob


def manual_enqueue_radarr_cleanup_drive(
    session: Session,
) -> tuple[RefinerJob, Literal["created", "already_present"]]:
    prior = session.scalar(
        select(RefinerJob.id).where(
            RefinerJob.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
        ),
    )
    job = enqueue_radarr_failed_import_cleanup_drive_job(session)
    if prior is not None:
        return job, "already_present"
    return job, "created"


def manual_enqueue_sonarr_cleanup_drive(
    session: Session,
) -> tuple[RefinerJob, Literal["created", "already_present"]]:
    prior = session.scalar(
        select(RefinerJob.id).where(
            RefinerJob.dedupe_key == SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
        ),
    )
    job = enqueue_sonarr_failed_import_cleanup_drive_job(session)
    if prior is not None:
        return job, "already_present"
    return job, "created"
