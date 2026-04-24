"""GET ``/api/v1/system/directories``."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_system_directories_requires_operator(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text

    r = client_with_viewer.get("/api/v1/system/directories")

    assert r.status_code == 403


def test_system_directories_lists_roots(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)

    r = client_with_admin.get("/api/v1/system/directories")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_path"] is None
    assert body["parent_path"] is None
    assert isinstance(body["entries"], list)
    assert body["entries"]
    assert {"name", "path", "kind", "description"}.issubset(body["entries"][0])


def test_system_directories_returns_not_found(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)

    r = client_with_admin.get("/api/v1/system/directories", params={"path": r"Z:\definitely-not-real-mediamop"})

    assert r.status_code == 404
    assert r.json()["detail"] == "The requested directory does not exist."
