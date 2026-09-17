"""Port of the retired Python backend's tests/test_health.py (smoke tests for the backend spine)."""

from __future__ import annotations

import pytest

from tests.contract.support.client import API


@pytest.fixture(scope="module")
def server_env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    # A packaged web build of our own, so the SPA fallback tests know exactly what the shell holds.
    web_dist = tmp_path_factory.mktemp("web")
    (web_dist / "index.html").write_text("<!doctype html><title>Weir</title>", encoding="utf-8")
    return {"WEIR_WEB_DIST": str(web_dist)}


def test_health_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "dependencies": {"database": "ok"}}
    assert response.headers.get("Cache-Control", "").startswith("no-store")
    assert response.headers.get("X-Request-ID")


def test_request_id_header_is_echoed(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "audit-request-1"})

    assert response.headers.get("X-Request-ID") == "audit-request-1"


def test_ready_ok_after_lifespan_startup(client) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert set(body) == {"ready", "status"}
    assert response.headers.get("Cache-Control", "").startswith("no-store")


def test_unknown_upgrade_api_browser_landing_redirects_to_settings(client) -> None:
    response = client.get(f"{API}/suite/upgrade-now")

    assert response.status_code == 303
    assert response.headers["location"] == "/settings"


def test_regular_unknown_api_path_still_returns_json_404(client) -> None:
    response = client.get(f"{API}/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_packaged_app_routes_refresh_to_react_shell(client) -> None:
    response = client.get("/settings", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Weir" in response.text


def test_unknown_non_app_path_still_returns_404(client) -> None:
    response = client.get("/not-a-real-route")

    assert response.status_code == 404
