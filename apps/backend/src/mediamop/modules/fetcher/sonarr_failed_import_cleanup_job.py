"""Sonarr failed-import cleanup: ``fetcher_jobs`` row producer + Fetcher in-process worker handler."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob
from mediamop.modules.fetcher.fetcher_jobs_ops import fetcher_enqueue_or_get_job
from mediamop.modules.fetcher.fetcher_worker_loop import FetcherJobWorkContext
from mediamop.modules.fetcher.sonarr_cleanup_execution import SonarrQueueHttpClient
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_drive import (
    SonarrQueueHttpFetchClient,
    drive_sonarr_failed_import_cleanup_from_live_queue,
)
from mediamop.modules.fetcher.failed_import_drive_job_kinds import (
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
)
from mediamop.modules.fetcher.failed_import_worker_ports import FailedImportSonarrWorkerRuntimePort

SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY = "failed_import.sonarr.cleanup_drive:v1"


def enqueue_sonarr_failed_import_cleanup_drive_job(session: Session) -> FetcherJob:
    """Insert or return the single durable Sonarr live cleanup sweep job."""

    return fetcher_enqueue_or_get_job(
        session,
        dedupe_key=SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
        job_kind=FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
        payload_json="{}",
    )


def make_sonarr_failed_import_cleanup_drive_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    fetcher_runtime: FailedImportSonarrWorkerRuntimePort,
) -> Callable[[FetcherJobWorkContext], None]:
    """Build a worker handler that runs the existing Sonarr live drive (HTTP clients from settings)."""

    def _run(_ctx: FetcherJobWorkContext) -> None:
        try:
            base = settings.fetcher_sonarr_base_url
            key = settings.fetcher_sonarr_api_key
            if not base or not key:
                msg = (
                    "Sonarr live cleanup drive requires MEDIAMOP_FETCHER_SONARR_BASE_URL and "
                    "MEDIAMOP_FETCHER_SONARR_API_KEY"
                )
                raise RuntimeError(msg)

            with session_factory() as session:
                with session.begin():
                    policy_source = fetcher_runtime.load_sonarr_drive_policy_source(session, settings)

            fetch_client = SonarrQueueHttpFetchClient(base, key)
            queue_ops = SonarrQueueHttpClient(base, key)
            with session_factory() as session:
                with session.begin():
                    fetcher_runtime.record_run_started(session)
            results = drive_sonarr_failed_import_cleanup_from_live_queue(
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
