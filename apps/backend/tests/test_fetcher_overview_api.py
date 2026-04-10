"""Fetcher operational overview API tests (read-only, authenticated)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.fetcher.probe import FetcherHealthProbe
from mediamop.modules.fetcher.service import build_fetcher_operational_overview
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _session_factory():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    return settings, fac


def test_build_fetcher_overview_not_configured() -> None:
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url=None)
    with fac() as db:
        out = build_fetcher_operational_overview(db, settings)
        db.commit()
    assert out.connection.configured is False
    assert out.status_label == "Not configured"
    assert out.recent_probe_events == []


@patch("mediamop.modules.fetcher.service.probe_fetcher_healthz")
def test_build_fetcher_overview_failed_probe(mock_probe: MagicMock) -> None:
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
        out = build_fetcher_operational_overview(db, settings)
        db.commit()
    assert out.connection.configured is True
    assert out.connection.reachable is False
    assert out.status_label == "Needs attention"
    assert out.latest_probe_event is None
    assert out.recent_probe_events == []


@patch("mediamop.modules.fetcher.service.probe_fetcher_healthz")
def test_build_fetcher_overview_stale_signal(mock_probe: MagicMock) -> None:
    mock_probe.return_value = FetcherHealthProbe(
        reachable=True,
        http_status=200,
        latency_ms=12.0,
        fetcher_app="Fetcher",
        fetcher_version="1.0",
        error_summary=None,
    )
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url="http://127.0.0.1:8789")
    old_dt = datetime.now(timezone.utc) - timedelta(minutes=31)
    with fac() as db:
        db.execute(delete(ActivityEvent))
        db.add(
            ActivityEvent(
                created_at=old_dt,
                event_type=activity_constants.FETCHER_PROBE_SUCCEEDED,
                module="fetcher",
                title="Fetcher probe succeeded",
                detail="Target: http://127.0.0.1:8789",
            )
        )
        db.commit()
    with fac() as db:
        out = build_fetcher_operational_overview(db, settings)
        db.commit()
    assert out.connection.reachable is True
    assert out.status_label == "Stale signal"
    assert out.latest_probe_event is not None
    assert out.latest_probe_event.event_type == activity_constants.FETCHER_PROBE_SUCCEEDED


def test_get_fetcher_overview_authenticated(client_with_admin: TestClient) -> None:
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
    r = client_with_admin.get("/api/v1/fetcher/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "status_label" in body
    assert "status_detail" in body
    assert "connection" in body
    assert "recent_probe_events" in body
