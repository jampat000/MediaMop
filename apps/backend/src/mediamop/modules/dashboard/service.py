"""Compose dashboard payload — read-only for persistence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop import __version__
from mediamop.core.config import MediaMopSettings
from mediamop.modules.dashboard.schemas import (
    ActivitySummaryOut,
    DashboardStatusOut,
    ModuleOperationalStatusOut,
    SystemStatusOut,
    WorkerLaneHealthOut,
)
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_work_admission import resolve_pause_state
from mediamop.platform.activity import service as activity_service
from mediamop.platform.activity.schemas import ActivityEventItemOut
from mediamop.platform.jobs.worker_health import build_worker_health_snapshot
from mediamop.platform.suite_settings.model import SuiteSettingsRow


def _build_activity_summary(db: Session) -> ActivitySummaryOut:
    since = datetime.now(UTC) - timedelta(hours=24)
    n = activity_service.count_activity_events_since(db, since=since)
    latest_row = activity_service.get_latest_activity_event(db)
    latest = ActivityEventItemOut.model_validate(latest_row) if latest_row else None
    return ActivitySummaryOut(events_last_24h=n, latest=latest)


def _count_jobs(db: Session, model, status: str | tuple[str, ...]) -> int:
    values = (status,) if isinstance(status, str) else status
    return int(db.scalar(select(func.count()).select_from(model).where(model.status.in_(values))) or 0)


def _build_module_statuses(
    db: Session,
    *,
    worker_health: list[WorkerLaneHealthOut],
) -> tuple[list[ModuleOperationalStatusOut], int]:
    now = datetime.now(UTC)
    pause_row = db.get(SuiteSettingsRow, 1)
    paused = bool(pause_row and resolve_pause_state(pause_row, now=now).paused)
    statuses: list[ModuleOperationalStatusOut] = []

    refiner_configured = bool(
        db.scalar(
            select(func.count())
            .select_from(RefinerLibraryRow)
            .where(RefinerLibraryRow.enabled.is_(True))
            .where(func.length(func.trim(RefinerLibraryRow.watched_folder)) > 0),
        )
        or 0
    )
    refiner_active = _count_jobs(db, RefinerJob, (RefinerJobStatus.LEASED.value,))
    refiner_queued = _count_jobs(db, RefinerJob, (RefinerJobStatus.PENDING.value,))
    refiner_failed = _count_jobs(
        db, RefinerJob, (RefinerJobStatus.FAILED.value, RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value)
    )
    refiner_quarantined = int(
        db.scalar(
            select(func.count())
            .select_from(RefinerFileRow)
            .where(RefinerFileRow.status == RefinerFileStatus.ON_HOLD.value)
            .where(RefinerFileRow.failure_attempts >= 3),
        )
        or 0
    )
    refiner_worker = next((row for row in worker_health if row.module == "refiner"), None)
    if paused:
        refiner_state, refiner_summary = "paused", "Processing is paused; queued work will wait until it is resumed."
    elif not refiner_configured:
        refiner_state, refiner_summary = (
            "setup_required",
            "Add an enabled watched-folder library before Refiner can process files.",
        )
    elif refiner_failed or refiner_quarantined:
        refiner_state = "degraded"
        parts: list[str] = []
        if refiner_failed:
            parts.append(
                f"{refiner_failed} Refiner job(s) need review. Open Refiner Jobs for the explanation and recovery action."
            )
        if refiner_quarantined:
            parts.append(
                f"{refiner_quarantined} file(s) are held after repeated failures. Open Refiner Files to fix or start them again."
            )
        if refiner_worker and refiner_worker.status == "degraded":
            parts.append(refiner_worker.detail)
        refiner_summary = " ".join(parts)
    elif refiner_worker and refiner_worker.status == "degraded":
        refiner_state, refiner_summary = "degraded", refiner_worker.detail
    elif refiner_active or refiner_queued:
        refiner_state, refiner_summary = (
            "processing",
            f"Refiner has {refiner_active + refiner_queued} current job(s) in flight.",
        )
    else:
        refiner_state, refiner_summary = "healthy", "Refiner is configured and waiting for eligible files."
    statuses.append(
        ModuleOperationalStatusOut(
            module="refiner",
            state=refiner_state,
            configured=refiner_configured,
            active_job_count=refiner_active,
            queued_job_count=refiner_queued,
            failed_job_count=refiner_failed,
            quarantined_file_count=refiner_quarantined,
            summary=refiner_summary,
            action_path=(
                "/refiner?tab=files&status=on_hold"
                if refiner_quarantined and not refiner_failed
                else "/refiner?tab=jobs&status=failed"
                if refiner_failed
                else "/refiner?tab=jobs"
                if (refiner_worker and refiner_worker.status == "degraded")
                else "/refiner?tab=libraries"
            ),
        )
    )

    enabled_pruner = db.scalar(
        select(func.count()).select_from(PrunerServerInstance).where(PrunerServerInstance.enabled.is_(True))
    )
    pruner_configured = bool(enabled_pruner)
    pruner_active = _count_jobs(db, PrunerJob, (PrunerJobStatus.LEASED.value,))
    pruner_queued = _count_jobs(db, PrunerJob, (PrunerJobStatus.PENDING.value,))
    pruner_failed = _count_jobs(
        db, PrunerJob, (PrunerJobStatus.FAILED.value, PrunerJobStatus.HANDLER_OK_FINALIZE_FAILED.value)
    )
    failed_connection = bool(
        db.scalar(
            select(func.count())
            .select_from(PrunerServerInstance)
            .where(PrunerServerInstance.enabled.is_(True))
            .where(PrunerServerInstance.last_connection_test_ok.is_(False)),
        )
        or 0
    )
    pruner_worker = next((row for row in worker_health if row.module == "pruner"), None)
    if paused:
        pruner_state, pruner_summary = (
            "paused",
            "Processing is paused; scheduled cleanup will wait until it is resumed.",
        )
    elif not pruner_configured:
        pruner_state, pruner_summary = (
            "setup_required",
            "Connect an enabled Emby, Jellyfin, or Plex server before Pruner can run.",
        )
    elif (pruner_worker and pruner_worker.status == "degraded") or failed_connection or pruner_failed:
        pruner_state = "degraded"
        parts = []
        if failed_connection:
            parts.append("The connected media server needs a connection test.")
        if pruner_failed:
            parts.append(f"{pruner_failed} Pruner job(s) need review in Pruner Jobs.")
        if pruner_worker and pruner_worker.status == "degraded":
            parts.append(pruner_worker.detail)
        pruner_summary = " ".join(parts)
    elif pruner_active or pruner_queued:
        pruner_state, pruner_summary = (
            "processing",
            f"Pruner has {pruner_active + pruner_queued} current job(s) in flight.",
        )
    else:
        pruner_state, pruner_summary = "healthy", "Pruner is configured and idle."
    statuses.append(
        ModuleOperationalStatusOut(
            module="pruner",
            state=pruner_state,
            configured=pruner_configured,
            active_job_count=pruner_active,
            queued_job_count=pruner_queued,
            failed_job_count=pruner_failed,
            summary=pruner_summary,
            action_path=(
                "/pruner?tab=jobs"
                if pruner_failed or (pruner_worker and pruner_worker.status == "degraded")
                else "/pruner?tab=emby"
            ),
        )
    )
    incidents = refiner_failed + pruner_failed + refiner_quarantined + int(failed_connection)
    return statuses, incidents


def build_dashboard_status(db: Session, settings: MediaMopSettings) -> DashboardStatusOut:
    worker_health = build_worker_health_snapshot(
        expected_workers={
            "refiner": int(settings.refiner_worker_count),
            "pruner": int(settings.pruner_worker_count),
        },
    )
    workers_healthy = all(row.status in {"healthy", "disabled"} for row in worker_health)
    worker_rows = [WorkerLaneHealthOut(**asdict(row)) for row in worker_health]
    modules, incident_count = _build_module_statuses(db, worker_health=worker_rows)
    return DashboardStatusOut(
        system=SystemStatusOut(
            api_version=__version__,
            environment=settings.env,
            healthy=workers_healthy,
            worker_health=worker_rows,
        ),
        activity_summary=_build_activity_summary(db),
        modules=modules,
        incident_count=incident_count,
    )
