"""Radarr-only refiner_jobs producer + worker handler for the live failed-import cleanup drive (Pass 15).

Enqueue uses a stable dedupe key so only one sweep row exists at a time. The handler reuses
:func:`~mediamop.modules.refiner.radarr_failed_import_cleanup_drive.drive_radarr_failed_import_cleanup_from_live_queue`.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.radarr_cleanup_execution import RadarrQueueHttpClient
from mediamop.modules.refiner.radarr_failed_import_cleanup_drive import (
    RadarrQueueHttpFetchClient,
    drive_radarr_failed_import_cleanup_from_live_queue,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext

REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE = "refiner.radarr.failed_import_cleanup_drive.v1"

RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY = "refiner.radarr.failed_import_cleanup_drive:v1"


def enqueue_radarr_failed_import_cleanup_drive_job(session: Session) -> RefinerJob:
    """Insert or return the single durable Radarr live cleanup sweep job."""

    return refiner_enqueue_or_get_job(
        session,
        dedupe_key=RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
        job_kind=REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
        payload_json="{}",
    )


def make_radarr_failed_import_cleanup_drive_handler(
    settings: MediaMopSettings,
) -> Callable[[RefinerJobWorkContext], None]:
    """Build a worker handler that runs the existing Radarr live drive (HTTP clients from settings)."""

    def _run(_ctx: RefinerJobWorkContext) -> None:
        base = settings.refiner_radarr_base_url
        key = settings.refiner_radarr_api_key
        if not base or not key:
            msg = (
                "Radarr live cleanup drive requires MEDIAMOP_REFINER_RADARR_BASE_URL and "
                "MEDIAMOP_REFINER_RADARR_API_KEY"
            )
            raise RuntimeError(msg)

        fetch_client = RadarrQueueHttpFetchClient(base, key)
        queue_ops = RadarrQueueHttpClient(base, key)
        drive_radarr_failed_import_cleanup_from_live_queue(
            settings,
            queue_fetch_client=fetch_client,
            queue_operations=queue_ops,
        )

    return _run
