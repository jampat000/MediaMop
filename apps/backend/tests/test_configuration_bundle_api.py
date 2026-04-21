"""GET/PUT ``/api/v1/system/suite-configuration-bundle`` (and legacy suite paths) — export and restore settings."""

from __future__ import annotations

from copy import deepcopy
from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, csrf as fetch_csrf, trusted_browser_origin_headers


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_configuration_bundle_get_requires_operator(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    r = client_with_viewer.get("/api/v1/system/suite-configuration-bundle")
    assert r.status_code == 403


def test_configuration_bundle_get_legacy_path_still_works(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/suite/configuration-bundle")
    assert r.status_code == 200, r.text
    assert r.json()["format_version"] == 1


def test_configuration_bundle_round_trip_suite_name(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r0 = client_with_admin.get("/api/v1/system/suite-configuration-bundle")
    assert r0.status_code == 200, r0.text
    bundle = r0.json()
    assert bundle["format_version"] == 1
    assert "suite_settings" in bundle
    assert "fetcher_arr_operator_settings" in bundle

    b2 = deepcopy(bundle)
    b2["suite_settings"] = dict(bundle["suite_settings"])
    b2["suite_settings"]["product_display_name"] = "Bundle Restore Test"

    tok = fetch_csrf(client_with_admin)
    r_put = client_with_admin.put(
        "/api/v1/system/suite-configuration-bundle",
        json={"csrf_token": tok, "bundle": b2},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["suite_settings"]["product_display_name"] == "Bundle Restore Test"

    tok2 = fetch_csrf(client_with_admin)
    r_restore = client_with_admin.put(
        "/api/v1/system/suite-configuration-bundle",
        json={"csrf_token": tok2, "bundle": bundle},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_restore.status_code == 200, r_restore.text
    assert r_restore.json()["suite_settings"]["product_display_name"] == bundle["suite_settings"]["product_display_name"]


def test_configuration_bundle_put_rejects_bad_version(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r0 = client_with_admin.get("/api/v1/system/suite-configuration-bundle")
    assert r0.status_code == 200
    bundle = r0.json()
    bundle["format_version"] = 999
    tok = fetch_csrf(client_with_admin)
    r_put = client_with_admin.put(
        "/api/v1/system/suite-configuration-bundle",
        json={"csrf_token": tok, "bundle": bundle},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 400


def test_configuration_backup_list_shape(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/system/suite-configuration-backups")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "directory" in body
    assert isinstance(body["items"], list)
