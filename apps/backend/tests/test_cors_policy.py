from __future__ import annotations

from starlette.testclient import TestClient

from mediamop.api.factory import create_app


def _client_with_cors(monkeypatch):
    monkeypatch.setenv("MEDIAMOP_CORS_ORIGINS", "http://localhost:5173")
    return TestClient(create_app())


def test_cors_preflight_allows_media_mop_browser_methods_and_headers(monkeypatch) -> None:
    with _client_with_cors(monkeypatch) as client:
        response = client.options(
            "/api/v1/auth/csrf",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, X-CSRF-Token",
            },
        )

    assert response.status_code == 200
    methods = response.headers["access-control-allow-methods"]
    headers = response.headers["access-control-allow-headers"]
    assert "GET" in methods
    assert "POST" in methods
    assert "OPTIONS" in methods
    assert "Content-Type" in headers
    assert "X-CSRF-Token" in headers


def test_cors_preflight_rejects_unneeded_methods(monkeypatch) -> None:
    with _client_with_cors(monkeypatch) as client:
        trace = client.options(
            "/api/v1/auth/csrf",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "TRACE",
            },
        )
        connect = client.options(
            "/api/v1/auth/csrf",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "CONNECT",
            },
        )

    assert trace.status_code == 400
    assert connect.status_code == 400
    assert "TRACE" not in trace.headers.get("access-control-allow-methods", "")
    assert "CONNECT" not in connect.headers.get("access-control-allow-methods", "")


def test_cors_preflight_rejects_unneeded_headers(monkeypatch) -> None:
    with _client_with_cors(monkeypatch) as client:
        response = client.options(
            "/api/v1/auth/csrf",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Injected-Header",
            },
        )

    assert response.status_code == 400
