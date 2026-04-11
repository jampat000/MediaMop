"""Radarr failed-import cleanup: refiner_jobs row producer + in-process worker handler (Fetcher-owned).

Uses :mod:`mediamop.modules.refiner` for persisted jobs and queue drive execution; job_kind values
remain the stable ``refiner.*`` strings stored in ``refiner_jobs``.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.failed_import_fetcher_runtime_ports import FailedImportRadarrWorkerRuntimePort
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
    session_factory: sessionmaker[Session],
    *,
    fetcher_runtime: FailedImportRadarrWorkerRuntimePort,
) -> Callable[[RefinerJobWorkContext], None]:
    """Build a worker handler that runs the existing Radarr live drive (HTTP clients from settings)."""

    def _run(_ctx: RefinerJobWorkContext) -> None:
        try:
            base = settings.refiner_radarr_base_url
            key = settings.refiner_radarr_api_key
            if not base or not key:
                msg = (
                    "Radarr live cleanup drive requires MEDIAMOP_REFINER_RADARR_BASE_URL and "
                    "MEDIAMOP_REFINER_RADARR_API_KEY"
                )
                raise RuntimeError(msg)

            with session_factory() as session:
                with session.begin():
                    policy_source = fetcher_runtime.load_radarr_drive_policy_source(session, settings)

            fetch_client = RadarrQueueHttpFetchClient(base, key)
            queue_ops = RadarrQueueHttpClient(base, key)
            with session_factory() as session:
                with session.begin():
                    fetcher_runtime.record_run_started(session)
            results = drive_radarr_failed_import_cleanup_from_live_queue(
                policy_source,
                queue_fetch_client=fetch_client,
                queue_operations=queue_ops,
            )
            outcome_values = tuple(r.outcome.value for r in results)
            with session_factory() as session:
                with session.begin():
                    fetcher_runtime.record_drive_finished(session, outcome_values=outcome_values)
        except Exception as exc:
            with session_factory() as session:
                with session.begin():
                    fetcher_runtime.record_drive_failed(session, exc=exc)
            raise

    return _run
