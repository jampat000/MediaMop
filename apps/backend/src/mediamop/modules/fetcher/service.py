"""Read-only Fetcher operational overview service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.datetime_util import as_utc
from mediamop.modules.fetcher.probe import probe_fetcher_healthz
from mediamop.modules.fetcher.schemas import FetcherConnectionOut, FetcherOperationalOverviewOut
from mediamop.platform.activity import service as activity_service
from mediamop.platform.activity.schemas import ActivityEventItemOut

_STALE_MINUTES = 30


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
            "Checking",
            "No persisted Fetcher probe events yet. Keep this page open while checks run.",
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


def build_fetcher_operational_overview(
    db: Session,
    settings: MediaMopSettings,
) -> FetcherOperationalOverviewOut:
    raw_fetcher = (settings.fetcher_base_url or "").strip() or None
    if not raw_fetcher:
        connection = FetcherConnectionOut(
            configured=False,
            detail="Fetcher URL is not configured. Set MEDIAMOP_FETCHER_BASE_URL to probe a running Fetcher instance.",
        )
        label, detail = _status_lines(configured=False, reachable=None, latest_probe_event=None)
        return FetcherOperationalOverviewOut(
            status_label=label,
            status_detail=detail,
            connection=connection,
            latest_probe_event=None,
            recent_probe_events=[],
        )

    probe = probe_fetcher_healthz(raw_fetcher)
    display = _fetcher_target_display(raw_fetcher)
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
        status_label=label,
        status_detail=detail,
        connection=connection,
        latest_probe_event=latest,
        recent_probe_events=recent,
    )
