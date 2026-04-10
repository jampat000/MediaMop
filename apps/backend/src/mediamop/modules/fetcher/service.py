"""Read-only Fetcher operational overview service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from mediamop import __version__
from mediamop.core.config import MediaMopSettings
from mediamop.core.datetime_util import as_utc
from mediamop.modules.fetcher.probe import probe_fetcher_healthz
from mediamop.modules.fetcher.schemas import (
    FetcherConnectionOut,
    FetcherOperationalOverviewOut,
    FetcherProbePersistedWindowOut,
)
from mediamop.platform.activity import service as activity_service
from mediamop.platform.activity.schemas import ActivityEventItemOut

_STALE_MINUTES = 30
_PROBE_LOG_WINDOW_HOURS = 24
_PROBE_FAILURE_WINDOW_DAYS = 7
_PROBE_FAILURE_LIST_LIMIT = 5


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


def build_fetcher_operational_overview(
    db: Session,
    settings: MediaMopSettings,
) -> FetcherOperationalOverviewOut:
    raw_fetcher = (settings.fetcher_base_url or "").strip() or None
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
        connection=connection,
        probe_persisted_24h=probe_window,
        probe_failure_window_days=fail_days,
        recent_probe_failures=failure_items,
        latest_probe_event=latest,
        recent_probe_events=recent,
    )
