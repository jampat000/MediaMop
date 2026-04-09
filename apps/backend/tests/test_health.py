"""Smoke tests for the MediaMop backend spine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mediamop.api.factory import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
