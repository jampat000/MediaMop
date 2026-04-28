"""Smoke tests for the MediaMop backend spine."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from fastapi.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.platform.jobs.worker_health import reset_worker_health_for_tests
from mediamop.platform.readiness.service import build_readiness


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok_after_lifespan_startup() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert {step["name"] for step in body["steps"]} == {"database", "workers"}


def test_readiness_reports_starting_before_startup_complete() -> None:
    class State:
        startup_started_at = 0.0
        startup_ready = False
        engine = None
        session_factory = None

    payload = build_readiness(State())

    assert payload.ready is False
    assert payload.status == "starting"
    assert payload.steps[0].status == "starting"


def test_readiness_reports_failed_when_worker_heartbeat_missing() -> None:
    reset_worker_health_for_tests()

    class State:
        startup_started_at = 0.0
        startup_ready = True
        engine = object()
        session_factory = object()
        settings = replace(MediaMopSettings.load(), refiner_worker_count=1, pruner_worker_count=0, subber_worker_count=0)

    payload = build_readiness(State())

    assert payload.ready is False
    assert payload.status == "failed"
    assert any(step.name == "workers" and step.status == "failed" for step in payload.steps)


def test_unknown_upgrade_api_browser_landing_redirects_to_settings() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/suite/upgrade-now", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/app/settings"


def test_regular_unknown_api_path_still_returns_json_404() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/does-not-exist", follow_redirects=False)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_packaged_app_routes_refresh_to_react_shell(tmp_path: Path, monkeypatch) -> None:
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<!doctype html><title>MediaMop</title>", encoding="utf-8")
    monkeypatch.setenv("MEDIAMOP_WEB_DIST", str(web_dist))
    client = TestClient(create_app())

    response = client.get("/app/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MediaMop" in response.text


def test_unknown_non_app_path_still_returns_404(tmp_path: Path, monkeypatch) -> None:
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<!doctype html><title>MediaMop</title>", encoding="utf-8")
    monkeypatch.setenv("MEDIAMOP_WEB_DIST", str(web_dist))
    client = TestClient(create_app())

    response = client.get("/not-a-real-route", follow_redirects=False)

    assert response.status_code == 404
