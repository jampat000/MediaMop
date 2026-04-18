"""HTTP: ``/api/v1/subber/settings`` and connection tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import urllib.error
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, csrf, seed_admin_user, seed_viewer_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _isolated_subber_settings_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_subber_settings_api")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_viewer() -> TestClient:
    seed_viewer_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _login_admin(c: TestClient) -> None:
    tok = csrf(c)
    r = auth_post(
        c,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _login_viewer(c: TestClient) -> None:
    tok = csrf(c)
    r = auth_post(
        c,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_get_settings_requires_auth(client_admin: TestClient) -> None:
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 401


def test_get_settings_requires_operator(client_viewer: TestClient) -> None:
    _login_viewer(client_viewer)
    r = client_viewer.get("/api/v1/subber/settings")
    assert r.status_code == 403


def test_get_settings_admin_ok(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    body = r.json()
    assert "opensubtitles_username" in body
    assert body.get("opensubtitles_password_set") is False
    assert "adaptive_searching_enabled" in body
    assert "upgrade_enabled" in body


def test_get_providers_admin_ok(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/providers")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    keys = {x.get("provider_key") for x in rows}
    assert "opensubtitles_org" in keys
    assert "podnapisi" in keys


def test_put_settings_roundtrip_enabled(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r_put = client_admin.put(
        "/api/v1/subber/settings",
        json={"enabled": True, "csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json().get("enabled") is True


def test_test_opensubtitles_requires_operator(client_viewer: TestClient) -> None:
    _login_viewer(client_viewer)
    tok = csrf(client_viewer)
    r = auth_post(
        client_viewer,
        "/api/v1/subber/settings/test-opensubtitles",
        json={"csrf_token": tok},
    )
    assert r.status_code == 403


def test_test_opensubtitles_missing_creds(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/subber/settings/test-opensubtitles",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out.get("ok") is False


def _put_settings(client_admin: TestClient, payload: dict) -> dict:
    tok = csrf(client_admin)
    r = client_admin.put(
        "/api/v1/subber/settings",
        json={**payload, "csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_put_settings_language_preferences(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    langs = ["fr", "en"]
    _put_settings(client_admin, {"language_preferences": langs})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    assert r.json().get("language_preferences") == langs


def test_put_settings_subtitle_folder(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    folder = "/custom/subs"
    _put_settings(client_admin, {"subtitle_folder": folder})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    assert r.json().get("subtitle_folder") == folder


def test_put_settings_sonarr_url(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    url = "http://localhost:8989"
    _put_settings(client_admin, {"sonarr_base_url": url})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    assert r.json().get("sonarr_base_url") == url


def test_put_settings_radarr_url(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    url = "http://localhost:7878"
    _put_settings(client_admin, {"radarr_base_url": url})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    assert r.json().get("radarr_base_url") == url


def test_put_settings_sonarr_api_key_sets_flag(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(client_admin, {"sonarr_api_key": "abc123"})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    body = r.json()
    assert body.get("sonarr_api_key_set") is True


def test_put_settings_opensubtitles_credentials_set_flag(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "opensubtitles_username": "user",
            "opensubtitles_password": "pass",
            "opensubtitles_api_key": "key",
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    body = r.json()
    assert body.get("opensubtitles_username") == "user"
    assert body.get("opensubtitles_password_set") is True
    assert body.get("opensubtitles_api_key_set") is True


def test_put_settings_blank_password_keeps_existing(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "opensubtitles_username": "u1",
            "opensubtitles_password": "secret",
            "opensubtitles_api_key": "k1",
        },
    )
    _put_settings(client_admin, {"opensubtitles_password": ""})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    assert r.json().get("opensubtitles_password_set") is True


def test_put_settings_adaptive_searching_fields(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "adaptive_searching_enabled": False,
            "adaptive_searching_delay_hours": 72,
            "adaptive_searching_max_attempts": 5,
            "permanent_skip_after_attempts": 15,
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    b = r.json()
    assert b.get("adaptive_searching_enabled") is False
    assert b.get("adaptive_searching_delay_hours") == 72
    assert b.get("adaptive_searching_max_attempts") == 5
    assert b.get("permanent_skip_after_attempts") == 15


def test_put_settings_exclude_hearing_impaired(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(client_admin, {"exclude_hearing_impaired": True})
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    assert r.json().get("exclude_hearing_impaired") is True


def test_put_settings_upgrade_fields(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "upgrade_enabled": True,
            "upgrade_schedule_enabled": True,
            "upgrade_schedule_interval_seconds": 86400,
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    b = r.json()
    assert b.get("upgrade_enabled") is True
    assert b.get("upgrade_schedule_enabled") is True
    assert b.get("upgrade_schedule_interval_seconds") == 86400


def test_put_settings_tv_schedule_fields(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "tv_schedule_enabled": True,
            "tv_schedule_interval_seconds": 3600,
            "tv_schedule_hours_limited": True,
            "tv_schedule_days": "Mon,Tue",
            "tv_schedule_start": "08:00",
            "tv_schedule_end": "22:00",
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    b = r.json()
    assert b.get("tv_schedule_enabled") is True
    assert b.get("tv_schedule_interval_seconds") == 3600
    assert b.get("tv_schedule_hours_limited") is True
    assert b.get("tv_schedule_days") == "Mon,Tue"
    assert b.get("tv_schedule_start") == "08:00"
    assert b.get("tv_schedule_end") == "22:00"


def test_put_settings_movies_schedule_fields(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "movies_schedule_enabled": True,
            "movies_schedule_interval_seconds": 3600,
            "movies_schedule_hours_limited": True,
            "movies_schedule_days": "Mon,Tue",
            "movies_schedule_start": "08:00",
            "movies_schedule_end": "22:00",
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    b = r.json()
    assert b.get("movies_schedule_enabled") is True
    assert b.get("movies_schedule_interval_seconds") == 3600
    assert b.get("movies_schedule_hours_limited") is True
    assert b.get("movies_schedule_days") == "Mon,Tue"
    assert b.get("movies_schedule_start") == "08:00"
    assert b.get("movies_schedule_end") == "22:00"


def test_put_settings_path_mapping_sonarr(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "sonarr_path_mapping_enabled": True,
            "sonarr_path_sonarr": "/sonarr/tv",
            "sonarr_path_subber": "/mnt/nas/tv",
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    b = r.json()
    assert b.get("sonarr_path_mapping_enabled") is True
    assert b.get("sonarr_path_sonarr") == "/sonarr/tv"
    assert b.get("sonarr_path_subber") == "/mnt/nas/tv"


def test_put_settings_path_mapping_radarr(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    _put_settings(
        client_admin,
        {
            "radarr_path_mapping_enabled": True,
            "radarr_path_radarr": "/radarr/m",
            "radarr_path_subber": "/mnt/nas/movies",
        },
    )
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    b = r.json()
    assert b.get("radarr_path_mapping_enabled") is True
    assert b.get("radarr_path_radarr") == "/radarr/m"
    assert b.get("radarr_path_subber") == "/mnt/nas/movies"


def test_put_provider_enabled(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    r0 = client_admin.get("/api/v1/subber/providers")
    assert r0.status_code == 200
    pod = next(x for x in r0.json() if x.get("provider_key") == "podnapisi")
    assert pod.get("enabled") is not None
    tok = csrf(client_admin)
    r_put = client_admin.put(
        "/api/v1/subber/providers/podnapisi",
        json={"enabled": True, "csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    r1 = client_admin.get("/api/v1/subber/providers")
    assert r1.status_code == 200
    pod2 = next(x for x in r1.json() if x.get("provider_key") == "podnapisi")
    assert pod2.get("enabled") is True


def test_put_provider_priority(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r_put = client_admin.put(
        "/api/v1/subber/providers/opensubtitles_org",
        json={"priority": 5, "csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    r1 = client_admin.get("/api/v1/subber/providers")
    assert r1.status_code == 200
    row = next(x for x in r1.json() if x.get("provider_key") == "opensubtitles_org")
    assert row.get("priority") == 5


def test_put_provider_unknown_key_404(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.put(
        "/api/v1/subber/providers/nonexistent_provider",
        json={"enabled": True, "csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 404


@patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline"))
def test_test_provider_not_configured(_mock_url: object, client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/subber/providers/podnapisi/test",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is False


def test_test_provider_unknown_key_404(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/subber/providers/nonexistent/test",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 404
