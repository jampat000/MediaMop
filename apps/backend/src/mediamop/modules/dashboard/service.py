"""Compose dashboard payload — no side effects."""

from __future__ import annotations

from urllib.parse import urlparse

from mediamop import __version__
from mediamop.core.config import MediaMopSettings
from mediamop.modules.dashboard.schemas import (
    DashboardStatusOut,
    FetcherIntegrationOut,
    SystemStatusOut,
)
from mediamop.modules.fetcher.probe import probe_fetcher_healthz
from mediamop.platform.health.service import get_health


def _fetcher_target_display(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return base_url.rstrip("/")


def build_dashboard_status(settings: MediaMopSettings) -> DashboardStatusOut:
    health = get_health()
    raw_fetcher = (settings.fetcher_base_url or "").strip() or None
    if not raw_fetcher:
        return DashboardStatusOut(
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
        )

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
    )
