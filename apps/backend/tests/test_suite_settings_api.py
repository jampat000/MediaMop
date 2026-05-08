"""GET/PUT ``/api/v1/suite/settings`` and GET ``/api/v1/suite/security-overview``."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, func, select
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.activity.service import record_activity_event
from mediamop.platform.suite_settings.release_catalog import (
    GitHubReleaseAsset,
    GitHubReleaseRecord,
)
from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.service import apply_suite_settings_put, ensure_suite_settings_row
from mediamop.platform.auth.models import User
from mediamop.platform.auth.password import hash_password
from mediamop.platform.suite_settings.suite_configuration_backup_periodic import run_suite_configuration_backup_tick
from mediamop.platform.suite_settings.suite_configuration_backup_service import list_suite_configuration_backups
from mediamop.platform.suite_settings.logs_retention_periodic import (
    reset_log_retention_periodic_state_for_tests,
    run_log_retention_tick,
)
from mediamop.platform.suite_settings.update_service import start_suite_update_now

from tests.integration_helpers import (
    auth_post,
    csrf as fetch_csrf,
    reset_user_tables,
    trusted_browser_origin_headers,
)


def _release_record(version: str = "1.2.3") -> GitHubReleaseRecord:
    return GitHubReleaseRecord(
        tag_name=f"v{version}",
        version=version,
        release_name=f"MediaMop {version}",
        html_url="https://example.com/release",
        published_at=datetime(2026, 4, 23, tzinfo=UTC),
        draft=False,
        prerelease=False,
        assets=(
            GitHubReleaseAsset(
                name="MediaMopSetup.exe",
                api_url=f"https://api.github.com/repos/jampat000/MediaMop/releases/assets/{version.replace('.', '')}",
                browser_download_url=f"https://github.com/jampat000/MediaMop/releases/download/v{version}/MediaMopSetup.exe",
                size_bytes=123456789,
                content_type="application/octet-stream",
            ),
        ),
    )


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_suite_settings_get_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/suite/settings")
    assert r.status_code == 401


def test_suite_settings_get_ok_for_viewer(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    r = client_with_viewer.get("/api/v1/suite/settings")
    assert r.status_code == 200, r.text
    assert r.json()["product_display_name"] == "MediaMop"


def test_suite_settings_get_default_shape(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/suite/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_display_name"] == "MediaMop"
    assert body["signed_in_home_notice"] is None
    assert body["setup_wizard_state"] == "pending"
    assert body["app_timezone"] in {"UTC", "America/New_York"}
    assert body["log_retention_days"] == 30
    assert body["configuration_backup_enabled"] is False
    assert body["configuration_backup_interval_hours"] == 24
    assert body["configuration_backup_preferred_time"] == "02:00"
    assert body["configuration_backup_last_run_at"] is None
    assert "updated_at" in body


def test_ensure_suite_settings_row_defaults_to_skipped_for_existing_install() -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        db.execute(delete(SuiteSettingsRow))
        db.add(
            User(
                username="existing-admin",
                password_hash=hash_password("existing-admin-password"),
                role="admin",
                is_active=True,
            )
        )
        db.flush()

        row = ensure_suite_settings_row(db)

        assert row.setup_wizard_state == "skipped"


def test_bootstrap_explicitly_keeps_setup_wizard_pending_for_true_first_run(
) -> None:
    reset_user_tables()
    with TestClient(create_app()) as client:
        bootstrap_csrf = fetch_csrf(client)
        response = auth_post(
            client,
            "/api/v1/auth/bootstrap",
            json={
                "username": "fresh-admin",
                "password": "bootstrap-password-strong",
                "csrf_token": bootstrap_csrf,
            },
        )
        assert response.status_code == 200, response.text

        login_csrf = fetch_csrf(client)
        login_response = auth_post(
            client,
            "/api/v1/auth/login",
            json={
                "username": "fresh-admin",
                "password": "bootstrap-password-strong",
                "csrf_token": login_csrf,
            },
        )
        assert login_response.status_code == 200, login_response.text

        settings_response = client.get("/api/v1/suite/settings")
        assert settings_response.status_code == 200, settings_response.text
        assert settings_response.json()["setup_wizard_state"] == "pending"


def test_log_retention_tick_runs_once_per_day(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_log_retention_periodic_state_for_tests()
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    calls: list[int] = []

    def fake_prune(session, settings) -> None:
        calls.append(1)

    monkeypatch.setattr(
        "mediamop.platform.suite_settings.logs_retention_periodic.prune_logs_for_retention",
        fake_prune,
    )

    t0 = datetime(2026, 4, 29, 0, 0, tzinfo=UTC)
    assert run_log_retention_tick(fac, settings=settings, now=t0) == 1
    assert run_log_retention_tick(fac, settings=settings, now=t0 + timedelta(hours=1)) == 0
    assert run_log_retention_tick(fac, settings=settings, now=t0 + timedelta(days=1, seconds=1)) == 1
    assert len(calls) == 2


def test_suite_security_overview_get_ok(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/suite/security-overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "restart_required_note" in body
    assert "session_signing_configured" in body
    assert "allowed_browser_origins_count" in body
    assert "standard_session_idle_timeout_plain" in body
    assert "trusted_session_absolute_timeout_plain" in body


def test_suite_settings_put_persists(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "House Library",
            "signed_in_home_notice": "Welcome back.",
            "setup_wizard_state": "skipped",
            "app_timezone": "UTC",
            "log_retention_days": 45,
            "configuration_backup_enabled": True,
            "configuration_backup_interval_hours": 12,
            "configuration_backup_preferred_time": "03:30",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["product_display_name"] == "House Library"
    assert r.json()["signed_in_home_notice"] == "Welcome back."
    assert r.json()["setup_wizard_state"] == "skipped"
    assert r.json()["log_retention_days"] == 45
    assert r.json()["configuration_backup_enabled"] is True
    assert r.json()["configuration_backup_interval_hours"] == 12
    assert r.json()["configuration_backup_preferred_time"] == "03:30"

    r2 = client_with_admin.get("/api/v1/suite/settings")
    assert r2.status_code == 200
    assert r2.json()["product_display_name"] == "House Library"

    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = db.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one()
        assert row.product_display_name == "House Library"
        assert row.setup_wizard_state == "skipped"
        assert row.log_retention_days == 45
        assert row.configuration_backup_enabled is True
        assert row.configuration_backup_interval_hours == 12
        assert row.configuration_backup_preferred_time == "03:30"


def test_suite_settings_put_viewer_forbidden(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    tok2 = fetch_csrf(client_with_viewer)
    r = client_with_viewer.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok2,
            "product_display_name": "X",
            "signed_in_home_notice": None,
            "app_timezone": "UTC",
            "log_retention_days": 30,
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_apply_suite_settings_put_rejects_blank_name() -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        try:
            apply_suite_settings_put(
                db,
                product_display_name="   ",
                signed_in_home_notice=None,
                app_timezone="UTC",
                log_retention_days=30,
            )
        except ValueError as exc:
            assert "empty" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError")


def test_apply_suite_settings_put_rejects_invalid_timezone() -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        try:
            apply_suite_settings_put(
                db,
                product_display_name="MediaMop",
                signed_in_home_notice=None,
                app_timezone="Not/A_Real_Zone",
                log_retention_days=30,
            )
        except ValueError as exc:
            assert "timezone" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError")


def test_activity_event_detail_always_persisted() -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = record_activity_event(
            db,
            event_type=act_c.AUTH_LOGIN_SUCCEEDED,
            module="auth",
            title="Sign-in succeeded",
            detail="alice",
        )
        db.commit()
        stored = db.get(ActivityEvent, row.id)
    assert stored is not None
    assert stored.detail == "alice"


def test_log_retention_does_not_prune_activity_history(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "MediaMop",
            "signed_in_home_notice": None,
            "app_timezone": "UTC",
            "log_retention_days": 30,
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = record_activity_event(
            db,
            event_type=act_c.AUTH_LOGIN_SUCCEEDED,
            module="auth",
            title="old",
            detail="alice",
        )
        db.flush()
        old = db.get(ActivityEvent, row.id)
        assert old is not None
        from datetime import datetime, timedelta, timezone

        old.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        db.commit()

    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "MediaMop",
            "signed_in_home_notice": None,
            "app_timezone": "UTC",
            "log_retention_days": 30,
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    with fac() as db:
        record_activity_event(
            db,
            event_type=act_c.AUTH_LOGIN_SUCCEEDED,
            module="auth",
            title="new",
            detail="alice",
        )
        db.commit()
        n_old = db.scalar(select(func.count()).select_from(ActivityEvent).where(ActivityEvent.title == "old"))
    assert int(n_old or 0) == 1


def test_suite_update_status_ok(client_with_admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login_admin(client_with_admin)
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("1.2.3"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "1.0.0")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._fetch_windows_updater_progress",
        lambda _settings=None: (
            True,
            "Remote in-app upgrade is ready on this Windows install.",
            None,
        ),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")

    r = client_with_admin.get("/api/v1/suite/update-status")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_version"] == "1.0.0"
    assert body["latest_version"] == "1.2.3"
    assert body["status"] == "update_available"
    assert body["in_app_upgrade_supported"] is True


def test_suite_update_status_alias_ok(client_with_admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login_admin(client_with_admin)
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("1.2.3"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "1.0.0")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._fetch_windows_updater_progress",
        lambda _settings=None: (
            False,
            "Remote in-app upgrade is unavailable because MediaMop could not reach the local updater service.",
            {
                "phase": "installer_running",
                "message": "Installer is running. MediaMop may temporarily disconnect.",
                "target_version": "1.2.3",
            },
        ),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")

    r = client_with_admin.get("/api/v1/suite/settings/update-status")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "update_available"
    assert body["upgrade"]["phase"] == "installer_running"


def test_suite_update_now_get_redirects_back_to_settings(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)

    r = client_with_admin.get("/api/v1/suite/update-now", follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/settings"


def test_suite_update_diagnostics_requires_operator_and_returns_shape(
    client_with_admin: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(client_with_admin)
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.router.build_suite_update_diagnostics",
        lambda _settings=None: {
            "current_version": "2.0.7",
            "latest_version": "2.0.8",
            "install_type": "windows",
            "install_root": "C:/Program Files/MediaMop",
            "runtime_home": "C:/ProgramData/MediaMop",
            "updater_service_reachable": True,
            "updater_token_path_present": True,
            "installer_log_path": "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
            "service_log_path": "C:/ProgramData/MediaMop/upgrades/updater-service.log",
            "installer_log_tail": [],
            "service_log_tail": [],
            "running_processes": [],
            "installed_files": [],
            "upgrade": None,
        },
    )

    r = client_with_admin.get("/api/v1/suite/update-diagnostics")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["install_type"] == "windows"
    assert body["updater_service_reachable"] is True


def test_suite_update_status_not_published_when_release_missing(
    client_with_admin: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(client_with_admin)

    request = httpx.Request("GET", "https://api.github.com/repos/jampat000/MediaMop/releases/latest")
    response = httpx.Response(404, request=request)

    def _raise_not_found(**_kwargs) -> None:  # noqa: ANN003
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        _raise_not_found,
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "1.0.0")

    r = client_with_admin.get("/api/v1/suite/update-status")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_published"
    assert "no public mediamop release is published yet" in body["summary"].lower()


def test_suite_update_now_returns_unavailable_when_updater_service_is_not_ready(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = replace(MediaMopSettings.load(), mediamop_home=str(tmp_path))
    monkeypatch.setenv("MEDIAMOP_RUNTIME", "windows")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "1.0.0")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("1.2.3"),
    )
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._start_windows_updater_service_apply",
        lambda _settings, target_version: (
            False,
            "Remote in-app upgrade is unavailable because the local updater service token did not match this app install.",
            None,
        ),
    )

    out = start_suite_update_now(settings)

    assert out.status == "unavailable"
    assert "local updater service token did not match" in out.message.lower()
    assert out.installer_path is None
    assert out.log_path == str(tmp_path / "upgrades" / "updater-service.log")


def test_suite_update_now_uses_windows_updater_service_when_available(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = replace(MediaMopSettings.load(), mediamop_home=str(tmp_path))
    monkeypatch.setenv("MEDIAMOP_RUNTIME", "windows")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "1.0.0")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("1.2.3"),
    )
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._start_windows_updater_service_apply",
        lambda _settings, target_version: (
            True,
            "Upgrade request accepted. MediaMop is checking release metadata.",
            "attempt-123",
        ),
    )

    out = start_suite_update_now(settings)

    assert out.status == "started"
    assert out.attempt_id == "attempt-123"
    assert out.target_version == "1.2.3"
    assert out.log_path == str(tmp_path / "upgrades" / "updater-service.log")


def test_suite_configuration_backup_tick_creates_snapshot(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "MediaMop",
            "signed_in_home_notice": None,
            "setup_wizard_state": "completed",
            "app_timezone": "UTC",
            "log_retention_days": 30,
            "configuration_backup_enabled": True,
            "configuration_backup_interval_hours": 6,
            "configuration_backup_preferred_time": "04:15",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text

    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    fac = create_session_factory(engine)
    with fac() as db:
        _directory_before, rows_before = list_suite_configuration_backups(db, settings=settings)
    created = run_suite_configuration_backup_tick(fac, settings=settings, now=datetime.now(UTC).replace(microsecond=0))
    if created == 0:
        created = run_suite_configuration_backup_tick(
            fac,
            settings=settings,
            now=datetime.now(UTC).replace(microsecond=0) + timedelta(hours=7),
        )
    assert created == 1

    with fac() as db:
        directory, rows = list_suite_configuration_backups(db, settings=settings)
        suite = db.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one()
        assert len(rows) >= len(rows_before) + 1
        assert rows[0].size_bytes > 0
        assert suite.configuration_backup_last_run_at is not None
        assert suite.configuration_backup_preferred_time == "04:15"
        assert directory


def test_suite_configuration_backup_tick_waits_for_preferred_time(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "MediaMop",
            "signed_in_home_notice": None,
            "setup_wizard_state": "completed",
            "app_timezone": "Australia/Sydney",
            "log_retention_days": 30,
            "configuration_backup_enabled": True,
            "configuration_backup_interval_hours": 24,
            "configuration_backup_preferred_time": "23:30",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text

    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        suite = db.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one()
        suite.configuration_backup_last_run_at = None
        db.commit()
    before_target = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    after_target = datetime(2026, 4, 24, 13, 45, tzinfo=UTC)

    assert run_suite_configuration_backup_tick(fac, settings=settings, now=before_target) == 0
    assert run_suite_configuration_backup_tick(fac, settings=settings, now=after_target) == 1
