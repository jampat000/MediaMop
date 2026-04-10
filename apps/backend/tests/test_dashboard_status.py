"""Dashboard JSON — service composition and authenticated route (SQLite)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, func, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.dashboard.service import build_dashboard_status
from mediamop.modules.fetcher.probe import FetcherHealthProbe
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _session_factory():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    return settings, fac


def test_build_dashboard_fetcher_not_configured() -> None:
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url=None)
    with fac() as db:
        out = build_dashboard_status(db, settings)
        db.commit()
    assert out.system.healthy is True
    assert out.fetcher.configured is False
    assert out.fetcher.reachable is None
    assert out.fetcher.detail is not None
    assert isinstance(out.activity_summary.events_last_24h, int)
    assert out.activity_summary.latest is None or out.activity_summary.latest.id > 0


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
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url="http://127.0.0.1:9")
    with fac() as db:
        db.execute(delete(ActivityEvent))
        db.commit()
    with fac() as db:
        out = build_dashboard_status(db, settings)
        db.commit()
    assert out.fetcher.configured is True
    assert out.fetcher.reachable is False
    assert out.fetcher.target_display == "http://127.0.0.1:9"
    assert "refused" in (out.fetcher.detail or "").lower()
    assert out.activity_summary.last_fetcher_probe is None


@patch("mediamop.modules.dashboard.service.probe_fetcher_healthz")
def test_build_dashboard_fetcher_probe_does_not_write_activity(mock_probe: MagicMock) -> None:
    mock_probe.return_value = FetcherHealthProbe(
        reachable=False,
        http_status=None,
        latency_ms=None,
        fetcher_app=None,
        fetcher_version=None,
        error_summary="Connection refused",
    )
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url="http://127.0.0.1:9")
    with fac() as db:
        db.execute(delete(ActivityEvent))
        db.commit()
    with fac() as db:
        build_dashboard_status(db, settings)
        db.commit()
    with fac() as db:
        build_dashboard_status(db, settings)
        db.commit()
    with fac() as db:
        n = db.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.FETCHER_PROBE_FAILED,
            ),
        )
    assert int(n or 0) == 0


def test_get_dashboard_status_authenticated(client_with_admin: TestClient) -> None:
    tok = fetch_csrf(client_with_admin)
    r_login = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": tok,
        },
    )
    assert r_login.status_code == 200, r_login.text
    r = client_with_admin.get("/api/v1/dashboard/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope_note"]
    assert body["system"]["healthy"] is True
    assert "api_version" in body["system"]
    assert body["fetcher"]["configured"] is False
    summ = body["activity_summary"]
    assert "events_last_24h" in summ
    assert "latest" in summ
    assert "last_fetcher_probe" in summ
