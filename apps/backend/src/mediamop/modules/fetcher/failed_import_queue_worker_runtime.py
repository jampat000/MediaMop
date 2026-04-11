"""Concrete Fetcher implementations of :mod:`mediamop.modules.refiner.failed_import_queue_worker_ports`."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.cleanup_policy_service import (
    FailedImportDrivePolicySource,
    load_fetcher_failed_import_cleanup_bundle,
)
from mediamop.modules.fetcher import failed_import_activity
from mediamop.modules.refiner.failed_import_queue_worker_ports import (
    FailedImportQueueWorkerPorts,
    FailedImportTimedSchedulePassQueuedPort,
)


class _FetcherRadarrWorkerRuntime:
    __slots__ = ()

    def load_radarr_drive_policy_source(
        self,
        session: Session,
        settings: MediaMopSettings,
    ) -> FailedImportDrivePolicySource:
        bundle, _ = load_fetcher_failed_import_cleanup_bundle(session, settings.failed_import_cleanup_env)
        return FailedImportDrivePolicySource(bundle)

    def record_run_started(self, session: Session) -> None:
        failed_import_activity.record_fetcher_failed_import_run_started(session, movies=True)

    def record_drive_finished(self, session: Session, *, outcome_values: tuple[str, ...]) -> None:
        failed_import_activity.record_fetcher_failed_import_drive_finished(
            session,
            movies=True,
            outcome_values=outcome_values,
        )

    def record_drive_failed(self, session: Session, *, exc: Exception) -> None:
        failed_import_activity.record_fetcher_failed_import_drive_failed(session, movies=True, exc=exc)


class _FetcherSonarrWorkerRuntime:
    __slots__ = ()

    def load_sonarr_drive_policy_source(
        self,
        session: Session,
        settings: MediaMopSettings,
    ) -> FailedImportDrivePolicySource:
        bundle, _ = load_fetcher_failed_import_cleanup_bundle(session, settings.failed_import_cleanup_env)
        return FailedImportDrivePolicySource(bundle)

    def record_run_started(self, session: Session) -> None:
        failed_import_activity.record_fetcher_failed_import_run_started(session, movies=False)

    def record_drive_finished(self, session: Session, *, outcome_values: tuple[str, ...]) -> None:
        failed_import_activity.record_fetcher_failed_import_drive_finished(
            session,
            movies=False,
            outcome_values=outcome_values,
        )

    def record_drive_failed(self, session: Session, *, exc: Exception) -> None:
        failed_import_activity.record_fetcher_failed_import_drive_failed(session, movies=False, exc=exc)


class _FetcherTimedSchedulePassQueued(FailedImportTimedSchedulePassQueuedPort):
    __slots__ = ()

    def record_timed_schedule_pass_queued_first_row(self, session: Session, *, movies: bool) -> None:
        failed_import_activity.record_fetcher_failed_import_pass_queued(
            session,
            movies=movies,
            source="timed_schedule",
        )


def build_failed_import_queue_worker_runtime_bundle() -> FailedImportQueueWorkerPorts:
    """Production wiring: Fetcher policy + activity behind Refiner ports."""

    return FailedImportQueueWorkerPorts(
        radarr_worker=_FetcherRadarrWorkerRuntime(),
        sonarr_worker=_FetcherSonarrWorkerRuntime(),
        timed_schedule_pass_queued=_FetcherTimedSchedulePassQueued(),
    )
