from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_subber_overview_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/subber/overview")
    assert r.status_code == 401


def test_subber_overview_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/subber/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 30
    assert "subtitles_downloaded" in body
    assert "still_missing" in body
    assert "tv_tracked" in body
    assert "movies_tracked" in body
    assert "searches_last_30_days" in body
