"""Smoke tests for the MediaMop backend spine."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mediamop.api.factory import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
