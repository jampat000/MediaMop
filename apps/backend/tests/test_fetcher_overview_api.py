"""Fetcher operational overview API tests (read-only, authenticated)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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
    assert out.mediamop_version
    assert out.recent_probe_events == []
    assert out.probe_persisted_24h.window_hours == 24
    assert out.probe_persisted_24h.persisted_ok == 0
    assert out.probe_persisted_24h.persisted_failed == 0
    assert out.probe_failure_window_days == 7
    assert out.recent_probe_failures == []


def test_build_fetcher_overview_probe_persisted_24h_counts() -> None:
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url=None)
    now = datetime.now(timezone.utc)
    with fac() as db:
        db.execute(delete(ActivityEvent))
        for _ in range(2):
            db.add(
                ActivityEvent(
                    created_at=now - timedelta(hours=2),
                    event_type=activity_constants.FETCHER_PROBE_SUCCEEDED,
                    module="fetcher",
                    title="Fetcher health check OK",
                    detail="http://example.test",
                )
            )
        db.add(
            ActivityEvent(
                created_at=now - timedelta(hours=3),
                event_type=activity_constants.FETCHER_PROBE_FAILED,
                module="fetcher",
                title="Fetcher health check failed",
                detail="http://example.test",
            )
        )
        db.add(
            ActivityEvent(
                created_at=now - timedelta(hours=25),
                event_type=activity_constants.FETCHER_PROBE_SUCCEEDED,
                module="fetcher",
                title="Fetcher health check OK",
                detail="http://old.test",
            )
        )
        db.commit()
    with fac() as db:
        out = build_fetcher_operational_overview(db, settings)
        db.commit()
    assert out.probe_persisted_24h.persisted_ok == 2
    assert out.probe_persisted_24h.persisted_failed == 1
    assert len(out.recent_probe_failures) == 1
    assert out.recent_probe_failures[0].event_type == activity_constants.FETCHER_PROBE_FAILED


def test_build_fetcher_overview_recent_probe_failures_capped_and_ordered() -> None:
    settings, fac = _session_factory()
    settings = replace(settings, fetcher_base_url=None)
    now = datetime.now(timezone.utc)
    with fac() as db:
        db.execute(delete(ActivityEvent))
        for h in range(1, 7):
            db.add(
                ActivityEvent(
                    created_at=now - timedelta(hours=h),
                    event_type=activity_constants.FETCHER_PROBE_FAILED,
                    module="fetcher",
                    title="Fetcher health check failed",
                    detail=f"target-{h}",
                )
            )
        db.add(
            ActivityEvent(
                created_at=now - timedelta(days=8),
                event_type=activity_constants.FETCHER_PROBE_FAILED,
                module="fetcher",
                title="Fetcher health check failed",
                detail="too-old",
            )
        )
        db.commit()
    with fac() as db:
        out = build_fetcher_operational_overview(db, settings)
        db.commit()
    assert out.probe_failure_window_days == 7
    assert len(out.recent_probe_failures) == 5
    assert [e.detail for e in out.recent_probe_failures] == [
        "target-1",
        "target-2",
        "target-3",
        "target-4",
        "target-5",
    ]
    assert all(e.event_type == activity_constants.FETCHER_PROBE_FAILED for e in out.recent_probe_failures)


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
    assert out.latest_probe_event is not None
    assert out.latest_probe_event.event_type == activity_constants.FETCHER_PROBE_FAILED
    assert out.recent_probe_events
    assert out.probe_persisted_24h.window_hours == 24
    assert out.probe_persisted_24h.persisted_failed >= 1
    assert out.recent_probe_failures
    assert all(e.event_type == activity_constants.FETCHER_PROBE_FAILED for e in out.recent_probe_failures)


@patch("mediamop.modules.fetcher.service.probe_fetcher_healthz")
def test_build_fetcher_overview_records_probe_when_reachable(mock_probe: MagicMock) -> None:
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
                detail="http://127.0.0.1:8789",
            )
        )
        db.commit()
    with fac() as db:
        out = build_fetcher_operational_overview(db, settings)
        db.commit()
    assert out.connection.reachable is True
    assert out.status_label == "Connected"
    assert out.latest_probe_event is not None
    assert out.latest_probe_event.event_type == activity_constants.FETCHER_PROBE_SUCCEEDED
    assert out.probe_persisted_24h.persisted_ok >= 1
    assert out.recent_probe_failures == []


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
    assert body.get("mediamop_version")
    snap = body.get("probe_persisted_24h")
    assert isinstance(snap, dict)
    assert snap.get("window_hours") == 24
    assert "persisted_ok" in snap
    assert "persisted_failed" in snap
    assert body.get("probe_failure_window_days") == 7
    assert isinstance(body.get("recent_probe_failures"), list)
