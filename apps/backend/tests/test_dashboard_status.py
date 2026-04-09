"""Dashboard JSON — service composition and authenticated route (no PostgreSQL required for route test)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.modules.dashboard.service import build_dashboard_status
from mediamop.modules.fetcher.probe import FetcherHealthProbe
from mediamop.platform.auth.deps_auth import get_current_user_public
from mediamop.platform.auth.schemas import UserPublic


def _settings(**overrides: object) -> MediaMopSettings:
    base: dict[str, object] = {
        "env": "development",
        "database_url": None,
        "log_level": "INFO",
        "cors_origins": (),
        "session_secret": None,
        "session_cookie_name": "mediamop_session",
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
        "session_idle_minutes": 720,
        "session_absolute_days": 14,
        "trusted_browser_origins_override": (),
        "auth_login_rate_max_attempts": 30,
        "auth_login_rate_window_seconds": 60,
        "bootstrap_rate_max_attempts": 10,
        "bootstrap_rate_window_seconds": 3600,
        "security_enable_hsts": False,
        "mediamop_home": "/tmp/mediamop-dashboard-test",
        "fetcher_base_url": None,
    }
    base.update(overrides)
    return MediaMopSettings(**base)  # type: ignore[arg-type]


def test_build_dashboard_fetcher_not_configured() -> None:
    out = build_dashboard_status(_settings())
    assert out.system.healthy is True
    assert out.fetcher.configured is False
    assert out.fetcher.reachable is None
    assert out.fetcher.detail is not None


@patch("mediamop.modules.dashboard.service.probe_fetcher_healthz")
def test_build_dashboard_fetcher_unreachable(mock_probe: MagicMock) -> None:
    mock_probe.return_value = FetcherHealthProbe(
        reachable=False,
        http_status=None,
        latency_ms=None,
        fetcher_app=None,
        fetcher_version=None,
        error_summary="Connection refused",
    )
    out = build_dashboard_status(_settings(fetcher_base_url="http://127.0.0.1:9"))
    assert out.fetcher.configured is True
    assert out.fetcher.reachable is False
    assert out.fetcher.target_display == "http://127.0.0.1:9"
    assert "refused" in (out.fetcher.detail or "").lower()


def test_get_dashboard_status_authenticated() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user_public] = lambda: UserPublic(
        id=1,
        username="dash_tester",
        role="admin",
    )
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/dashboard/status")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["scope_note"]
    assert body["system"]["healthy"] is True
    assert "api_version" in body["system"]
    assert body["fetcher"]["configured"] is False
