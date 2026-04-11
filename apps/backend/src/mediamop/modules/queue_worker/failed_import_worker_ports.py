"""Typed composition ports for Fetcher-owned failed-import queue workers.

Concrete implementations live in ``mediamop.modules.fetcher``. Lifespan wires Fetcher
periodic enqueue and Fetcher workers; this module stays import-light so Refiner never
imports Fetcher.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy


@runtime_checkable
class FailedImportRadarrDrivePolicySourcePort(Protocol):
    """Policy view Radarr live-queue drives read (structurally matches ``FailedImportDrivePolicySource``)."""

    def radarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy: ...


@runtime_checkable
class FailedImportSonarrDrivePolicySourcePort(Protocol):
    """Policy view Sonarr live-queue drives read."""

    def sonarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy: ...


class FailedImportRadarrWorkerRuntimePort(Protocol):
    """Fetcher-backed hooks for the Radarr failed-import cleanup queue worker."""

    def load_radarr_drive_policy_source(
        self,
        session: Session,
        settings: MediaMopSettings,
    ) -> FailedImportRadarrDrivePolicySourcePort: ...

    def record_run_started(self, session: Session) -> None: ...

    def record_drive_finished(self, session: Session, *, outcome_values: tuple[str, ...]) -> None: ...

    def record_drive_failed(self, session: Session, *, exc: Exception) -> None: ...


class FailedImportSonarrWorkerRuntimePort(Protocol):
    """Fetcher-backed hooks for the Sonarr failed-import cleanup queue worker."""

    def load_sonarr_drive_policy_source(
        self,
        session: Session,
        settings: MediaMopSettings,
    ) -> FailedImportSonarrDrivePolicySourcePort: ...

    def record_run_started(self, session: Session) -> None: ...

    def record_drive_finished(self, session: Session, *, outcome_values: tuple[str, ...]) -> None: ...

    def record_drive_failed(self, session: Session, *, exc: Exception) -> None: ...


class FailedImportTimedSchedulePassQueuedPort(Protocol):
    """Record Fetcher activity when timed schedule creates a new deduped failed-import job row."""

    def record_timed_schedule_pass_queued_first_row(self, session: Session, *, movies: bool) -> None: ...


@dataclass(frozen=True, slots=True)
class FailedImportQueueWorkerPorts:
    """Fetcher implementations wired into the in-process queue worker for failed-import drives + schedule."""

    radarr_worker: FailedImportRadarrWorkerRuntimePort
    sonarr_worker: FailedImportSonarrWorkerRuntimePort
    timed_schedule_pass_queued: FailedImportTimedSchedulePassQueuedPort


class NoOpFailedImportTimedSchedulePassQueuedPort:
    """Tests or callers that must not emit timed-schedule Fetcher activity."""

    __slots__ = ()

    def record_timed_schedule_pass_queued_first_row(self, session: Session, *, movies: bool) -> None:
        return None
