"""Read-only Fetcher operational overview service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop import __version__
from mediamop.core.config import MediaMopSettings
from mediamop.core.datetime_util import as_utc
from mediamop.modules.fetcher.probe import probe_fetcher_healthz
from mediamop.modules.fetcher.schemas import (
    FetcherConnectionOut,
    FetcherFailedImportAutomationLaneOut,
    FetcherFailedImportAutomationSummaryOut,
    FetcherOperationalOverviewOut,
    FetcherProbePersistedWindowOut,
)
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.radarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
)
from mediamop.platform.activity import service as activity_service
from mediamop.platform.activity.schemas import ActivityEventItemOut

_STALE_MINUTES = 30
_PROBE_LOG_WINDOW_HOURS = 24
_PROBE_FAILURE_WINDOW_DAYS = 7
_PROBE_FAILURE_LIST_LIMIT = 5
_FAILED_IMPORT_TERMINAL_STATUS: tuple[str, ...] = (
    RefinerJobStatus.COMPLETED.value,
    RefinerJobStatus.FAILED.value,
    RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
)
_LAST_OUTCOME_LABEL: dict[str, str] = {
    RefinerJobStatus.COMPLETED.value: "Completed",
    RefinerJobStatus.FAILED.value: "Finished with errors",
    RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value: "Needs manual finish",
}
_NEXT_RUN_NOTE_ENABLED = "Next run follows this saved interval when automation is active."
_NEXT_RUN_NOTE_OFF = "Schedule off."
_SUMMARY_SOURCE_NOTE = "From persisted task history and saved settings only."


def _fetcher_target_display(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return base_url.rstrip("/")


def _status_lines(
    *,
    configured: bool,
    reachable: bool | None,
    latest_probe_event: ActivityEventItemOut | None,
) -> tuple[str, str]:
    if not configured:
        return (
            "Not configured",
            "Set MEDIAMOP_FETCHER_BASE_URL to enable live Fetcher operational checks.",
        )
    if reachable is False:
        return (
            "Needs attention",
            "Current health probe failed. Check Fetcher service availability and base URL.",
        )
    if latest_probe_event is None:
        return (
            "Live OK",
            "Fetcher responded on this request, but the activity log has no probe row yet or the last write was throttled.",
        )
    created = as_utc(latest_probe_event.created_at)
    if datetime.now(timezone.utc) - created >= timedelta(minutes=_STALE_MINUTES):
        return (
            "Stale signal",
            "Last persisted Fetcher probe is older than 30 minutes.",
        )
    return (
        "Connected",
        "Current probe succeeded and recent persisted Fetcher probe events are available.",
    )


def _recent_probe_failure_items(
    db: Session,
) -> tuple[int, list[ActivityEventItemOut]]:
    since_fail = datetime.now(timezone.utc) - timedelta(days=_PROBE_FAILURE_WINDOW_DAYS)
    fail_rows = activity_service.list_recent_fetcher_probe_failures(
        db,
        since=since_fail,
        limit=_PROBE_FAILURE_LIST_LIMIT,
    )
    return (
        _PROBE_FAILURE_WINDOW_DAYS,
        [ActivityEventItemOut.model_validate(r) for r in fail_rows],
    )


def _format_saved_schedule(interval_seconds: int) -> str:
    if interval_seconds >= 3600 and interval_seconds % 3600 == 0:
        hours = interval_seconds // 3600
        return f"Every {hours} hour" if hours == 1 else f"Every {hours} hours"
    if interval_seconds >= 60 and interval_seconds % 60 == 0:
        minutes = interval_seconds // 60
        return f"Every {minutes} minute" if minutes == 1 else f"Every {minutes} minutes"
    return f"Every {interval_seconds} seconds"


def _last_finished_lane_row(
    db: Session,
    *,
    job_kind: str,
) -> tuple[datetime | None, str | None]:
    row = db.execute(
        select(RefinerJob.updated_at, RefinerJob.status)
        .where(
            RefinerJob.job_kind == job_kind,
            RefinerJob.status.in_(_FAILED_IMPORT_TERMINAL_STATUS),
        )
        .order_by(RefinerJob.updated_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    finished_at, status = row
    return finished_at, _LAST_OUTCOME_LABEL.get(status)


def _lane_summary(
    db: Session,
    *,
    job_kind: str,
    schedule_enabled: bool,
    schedule_interval_seconds: int,
) -> FetcherFailedImportAutomationLaneOut:
    finished_at, outcome = _last_finished_lane_row(db, job_kind=job_kind)
    if schedule_enabled:
        saved_schedule = _format_saved_schedule(schedule_interval_seconds)
        next_note = _NEXT_RUN_NOTE_ENABLED
    else:
        saved_schedule = "Off"
        next_note = _NEXT_RUN_NOTE_OFF
    return FetcherFailedImportAutomationLaneOut(
        last_finished_at=finished_at,
        last_outcome=outcome,
        saved_schedule=saved_schedule,
        next_run_note=next_note,
    )


def _failed_import_automation_summary(
    db: Session,
    settings: MediaMopSettings,
) -> FetcherFailedImportAutomationSummaryOut:
    return FetcherFailedImportAutomationSummaryOut(
        movies=_lane_summary(
            db,
            job_kind=REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
            schedule_enabled=settings.refiner_radarr_cleanup_drive_schedule_enabled,
            schedule_interval_seconds=settings.refiner_radarr_cleanup_drive_schedule_interval_seconds,
        ),
        tv_shows=_lane_summary(
            db,
            job_kind=REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
            schedule_enabled=settings.refiner_sonarr_cleanup_drive_schedule_enabled,
            schedule_interval_seconds=settings.refiner_sonarr_cleanup_drive_schedule_interval_seconds,
        ),
        source_note=_SUMMARY_SOURCE_NOTE,
    )


def build_fetcher_operational_overview(
    db: Session,
    settings: MediaMopSettings,
) -> FetcherOperationalOverviewOut:
    raw_fetcher = (settings.fetcher_base_url or "").strip() or None
    automation_summary = _failed_import_automation_summary(db, settings)
    if not raw_fetcher:
        since_24h = datetime.now(timezone.utc) - timedelta(hours=_PROBE_LOG_WINDOW_HOURS)
        ok_24h, failed_24h = activity_service.count_fetcher_probe_outcomes_since(db, since=since_24h)
        probe_window = FetcherProbePersistedWindowOut(
            window_hours=_PROBE_LOG_WINDOW_HOURS,
            persisted_ok=ok_24h,
            persisted_failed=failed_24h,
        )
        fail_days, failure_items = _recent_probe_failure_items(db)
        connection = FetcherConnectionOut(
            configured=False,
            detail="Fetcher URL is not configured. Set MEDIAMOP_FETCHER_BASE_URL to probe a running Fetcher instance.",
        )
        label, detail = _status_lines(configured=False, reachable=None, latest_probe_event=None)
        return FetcherOperationalOverviewOut(
            mediamop_version=__version__,
            status_label=label,
            status_detail=detail,
            failed_import_automation=automation_summary,
            connection=connection,
            probe_persisted_24h=probe_window,
            probe_failure_window_days=fail_days,
            recent_probe_failures=failure_items,
            latest_probe_event=None,
            recent_probe_events=[],
        )

    probe = probe_fetcher_healthz(raw_fetcher)
    display = _fetcher_target_display(raw_fetcher)
    activity_service.maybe_record_fetcher_probe_result(
        db,
        target_display=display,
        probe_succeeded=probe.reachable is True,
    )
    since_24h = datetime.now(timezone.utc) - timedelta(hours=_PROBE_LOG_WINDOW_HOURS)
    ok_24h, failed_24h = activity_service.count_fetcher_probe_outcomes_since(db, since=since_24h)
    probe_window = FetcherProbePersistedWindowOut(
        window_hours=_PROBE_LOG_WINDOW_HOURS,
        persisted_ok=ok_24h,
        persisted_failed=failed_24h,
    )
    fail_days, failure_items = _recent_probe_failure_items(db)
    latest_row = activity_service.get_latest_fetcher_probe_event(db)
    recent_rows = activity_service.list_recent_fetcher_probe_events(db, limit=8)
    latest = ActivityEventItemOut.model_validate(latest_row) if latest_row else None
    recent = [ActivityEventItemOut.model_validate(r) for r in recent_rows]

    connection = FetcherConnectionOut(
        configured=True,
        target_display=display,
        reachable=probe.reachable,
        http_status=probe.http_status,
        latency_ms=probe.latency_ms,
        fetcher_app=probe.fetcher_app,
        fetcher_version=probe.fetcher_version,
        detail=probe.error_summary if probe.reachable is not True else None,
    )
    label, detail = _status_lines(
        configured=True,
        reachable=probe.reachable,
        latest_probe_event=latest,
    )
    return FetcherOperationalOverviewOut(
        mediamop_version=__version__,
        status_label=label,
        status_detail=detail,
        failed_import_automation=automation_summary,
        connection=connection,
        probe_persisted_24h=probe_window,
        probe_failure_window_days=fail_days,
        recent_probe_failures=failure_items,
        latest_probe_event=latest,
        recent_probe_events=recent,
    )
