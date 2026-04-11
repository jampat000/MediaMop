"""Radarr failed-import cleanup: ``fetcher_jobs`` row producer + Fetcher in-process worker handler."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob
from mediamop.modules.fetcher.fetcher_jobs_ops import fetcher_enqueue_or_get_job
from mediamop.modules.fetcher.fetcher_worker_loop import FetcherJobWorkContext
from mediamop.modules.fetcher.radarr_cleanup_execution import RadarrQueueHttpClient
from mediamop.modules.fetcher.radarr_failed_import_cleanup_drive import (
    RadarrQueueHttpFetchClient,
    drive_radarr_failed_import_cleanup_from_live_queue,
)
from mediamop.modules.fetcher.failed_import_drive_job_kinds import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
)
from mediamop.modules.fetcher.failed_import_worker_ports import FailedImportRadarrWorkerRuntimePort

RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY = "failed_import.radarr.cleanup_drive:v1"


def enqueue_radarr_failed_import_cleanup_drive_job(session: Session) -> FetcherJob:
    """Insert or return the single durable Radarr live cleanup sweep job."""

    return fetcher_enqueue_or_get_job(
        session,
        dedupe_key=RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
        job_kind=FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
        payload_json="{}",
    )


def make_radarr_failed_import_cleanup_drive_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    fetcher_runtime: FailedImportRadarrWorkerRuntimePort,
) -> Callable[[FetcherJobWorkContext], None]:
    """Build a worker handler that runs the existing Radarr live drive (HTTP clients from settings)."""

    def _run(_ctx: FetcherJobWorkContext) -> None:
        try:
            base = settings.fetcher_radarr_base_url
            key = settings.fetcher_radarr_api_key
            if not base or not key:
                msg = (
                    "Radarr live cleanup drive requires MEDIAMOP_FETCHER_RADARR_BASE_URL and "
                    "MEDIAMOP_FETCHER_RADARR_API_KEY"
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
