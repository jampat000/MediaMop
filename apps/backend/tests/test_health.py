"""Smoke tests for the MediaMop backend spine."""

from __future__ import annotations

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
