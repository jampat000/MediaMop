"""Build read-only Fetcher failed-import automation summary from SQLite + loaded settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.schemas_automation_summary import (
    FetcherFailedImportAutomationSummaryOut,
    FetcherFailedImportAxisSummaryOut,
)
from mediamop.modules.refiner.inspection_service import DEFAULT_TERMINAL_STATUSES
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.radarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
)

_SCOPE_NOTE = (
    "From finished passes and saved settings in this app only. "
    "Does not show whether Radarr, Sonarr, or in-process automation is running right now."
)

_SLOTS_OFF_NOTE = (
    "Automation slots are set to 0 — timed passes will not start by themselves until that changes."
)

_SCHEDULE_ON_SECONDARY = (
    "Next run follows this saved interval when timed sweeps are on and automation is active."
)


def _format_saved_interval(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        h = seconds // 3600
        return f"Every {h} hour" + ("" if h == 1 else "s")
    if seconds >= 60 and seconds % 60 == 0:
        m = seconds // 60
        return f"Every {m} minute" + ("" if m == 1 else "s")
    return f"Every {seconds} seconds"


def _terminal_outcome_label(status: str) -> str:
    if status == RefinerJobStatus.COMPLETED.value:
        return "Completed"
    if status == RefinerJobStatus.FAILED.value:
        return "Stopped after errors"
    if status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value:
        return "Needs manual finish"
    return status


def _latest_terminal_job(session: Session, *, job_kind: str) -> RefinerJob | None:
    stmt = (
        select(RefinerJob)
        .where(
            RefinerJob.job_kind == job_kind,
            RefinerJob.status.in_(DEFAULT_TERMINAL_STATUSES),
        )
        .order_by(RefinerJob.updated_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def _axis_from_settings(
    *,
    empty_history_label: str,
    job: RefinerJob | None,
    schedule_enabled: bool,
    interval_seconds: int,
) -> FetcherFailedImportAxisSummaryOut:
    if job is None:
        last_at = None
        outcome = empty_history_label
    else:
        last_at = job.updated_at
        outcome = _terminal_outcome_label(job.status)

    if schedule_enabled:
        primary = f"Saved schedule: timed sweep on — {_format_saved_interval(interval_seconds)}"
        secondary = _SCHEDULE_ON_SECONDARY
    else:
        primary = "Saved schedule: timed sweep off"
        secondary = None

    return FetcherFailedImportAxisSummaryOut(
        last_finished_at=last_at,
        last_outcome_label=outcome,
        saved_schedule_primary=primary,
        saved_schedule_secondary=secondary,
    )


def build_fetcher_failed_import_automation_summary(
    session: Session,
    settings: MediaMopSettings,
) -> FetcherFailedImportAutomationSummaryOut:
    rad = _latest_terminal_job(session, job_kind=REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE)
    son = _latest_terminal_job(session, job_kind=REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE)

    slots_note = _SLOTS_OFF_NOTE if settings.refiner_worker_count == 0 else None

    movies = _axis_from_settings(
        empty_history_label="No finished movie pass recorded yet.",
        job=rad,
        schedule_enabled=settings.refiner_radarr_cleanup_drive_schedule_enabled,
        interval_seconds=settings.refiner_radarr_cleanup_drive_schedule_interval_seconds,
    )
    tv = _axis_from_settings(
        empty_history_label="No finished TV pass recorded yet.",
        job=son,
        schedule_enabled=settings.refiner_sonarr_cleanup_drive_schedule_enabled,
        interval_seconds=settings.refiner_sonarr_cleanup_drive_schedule_interval_seconds,
    )

    return FetcherFailedImportAutomationSummaryOut(
        scope_note=_SCOPE_NOTE,
        automation_slots_note=slots_note,
        movies=movies,
        tv_shows=tv,
    )
