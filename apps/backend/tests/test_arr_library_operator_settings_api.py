from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, csrf, trusted_browser_origin_headers


def _login_admin(client: TestClient) -> None:
    token = csrf(client)
    response = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": token},
    )
    assert response.status_code == 200, response.text


def test_arr_connection_test_handles_none_preview_credentials_without_strip_crash(
    client_with_admin: TestClient,
) -> None:
    _login_admin(client_with_admin)
    token = csrf(client_with_admin)

    with (
        patch(
            "mediamop.platform.arr_library.operator_settings_api.preview_sonarr_http_credentials_after_put",
            return_value=(None, "   "),
        ),
        patch("mediamop.platform.arr_library.operator_settings_api.ArrLibraryV3Client") as client_ctor,
    ):
        response = client_with_admin.post(
            "/api/v1/arr-library/arr-operator-settings/connection-test",
            json={
                "app": "sonarr",
                "enabled": True,
                "base_url": None,
                "api_key": None,
                "csrf_token": token,
            },
            headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert "not set up yet" in body["message"].lower()
    client_ctor.assert_not_called()
