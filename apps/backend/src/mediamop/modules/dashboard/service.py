"""Compose dashboard payload — read-only for persistence (live Fetcher probe in JSON only).

Fetcher reachability is reported from :func:`probe_fetcher_healthz` without writing
``activity_events`` on dashboard load (SQLite-first: avoid write-on-read).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from mediamop import __version__
from mediamop.core.config import MediaMopSettings
from mediamop.modules.dashboard.schemas import (
    ActivitySummaryOut,
    DashboardStatusOut,
    FetcherIntegrationOut,
    SystemStatusOut,
)
from mediamop.modules.fetcher.probe import probe_fetcher_healthz
from mediamop.platform.activity.schemas import ActivityEventItemOut
from mediamop.platform.activity import service as activity_service
from mediamop.platform.health.service import get_health


def _fetcher_target_display(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return base_url.rstrip("/")


def _build_activity_summary(db: Session) -> ActivitySummaryOut:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    n = activity_service.count_activity_events_since(db, since=since)
    latest_row = activity_service.get_latest_activity_event(db)
    fetcher_row = activity_service.get_latest_fetcher_probe_event(db)
    latest = ActivityEventItemOut.model_validate(latest_row) if latest_row else None
    last_probe = ActivityEventItemOut.model_validate(fetcher_row) if fetcher_row else None
    return ActivitySummaryOut(events_last_24h=n, latest=latest, last_fetcher_probe=last_probe)


def build_dashboard_status(db: Session, settings: MediaMopSettings) -> DashboardStatusOut:
    health = get_health()
    raw_fetcher = (settings.fetcher_base_url or "").strip() or None

    if not raw_fetcher:
        out = DashboardStatusOut(
            system=SystemStatusOut(
                api_version=__version__,
                environment=settings.env,
                healthy=health.status == "ok",
            ),
            fetcher=FetcherIntegrationOut(
                configured=False,
                target_display=None,
                reachable=None,
                detail="Fetcher URL is not configured. Set MEDIAMOP_FETCHER_BASE_URL to probe a running Fetcher instance.",
            ),
            activity_summary=_build_activity_summary(db),
        )
        return out

    probe = probe_fetcher_healthz(raw_fetcher)
    display = _fetcher_target_display(raw_fetcher)
    detail: str | None = None
    if not probe.reachable:
        detail = probe.error_summary or "Fetcher did not respond as expected."

    return DashboardStatusOut(
        system=SystemStatusOut(
            api_version=__version__,
            environment=settings.env,
            healthy=health.status == "ok",
        ),
        fetcher=FetcherIntegrationOut(
            configured=True,
            target_display=display,
            reachable=probe.reachable,
            http_status=probe.http_status,
            latency_ms=probe.latency_ms,
            fetcher_app=probe.fetcher_app,
            fetcher_version=probe.fetcher_version,
            detail=detail,
        ),
        activity_summary=_build_activity_summary(db),
    )
