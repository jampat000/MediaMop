"""Port of the retired Python backend's tests/test_suite_settings_api.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.contract.support import seed
from tests.contract.support.client import ADMIN_PASSWORD, ADMIN_USERNAME, API
from tests.contract.support.polling import wait_until
from tests.contract.system import _helpers as h

SETTINGS = f"{API}/suite/settings"


@pytest.fixture(scope="module", autouse=True)
def _users(server) -> None:
    h.seed_users(server)


def test_suite_settings_get_requires_auth(client) -> None:
    r = client.get(SETTINGS)
    assert r.status_code == 401


def test_suite_settings_get_ok_for_viewer(server, client_factory) -> None:
    viewer = h.signed_in_viewer(server, client_factory)
    r = viewer.get(SETTINGS)
    assert r.status_code == 200, r.text
    assert r.json()["product_display_name"] == "Weir"


def test_suite_settings_get_default_shape(admin) -> None:
    r = admin.get(SETTINGS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_display_name"] == "Weir"
    assert body["signed_in_home_notice"] is None
    # This module's install gained its users by seeding after first start, so the wizard
    # stayed at its first-run value.
    assert body["setup_wizard_state"] == "pending"
    assert body["app_timezone"] in {"UTC", "America/New_York"}
    assert body["log_retention_days"] == 30
    assert body["configuration_backup_enabled"] is False
    assert body["configuration_backup_interval_hours"] == 24
    assert body["configuration_backup_preferred_time"] == "02:00"
    assert body["configuration_backup_last_run_at"] is None
    assert "updated_at" in body


def test_ensure_suite_settings_row_defaults_to_skipped_for_existing_install(server_factory, client_factory) -> None:
    """An install that already has users and loses its settings row does not reopen first-run setup."""

    sut = server_factory()
    with seed.stopped(sut) as conn:
        conn.execute("DELETE FROM suite_settings")
        seed.insert_user(conn, username="existing-admin", password="existing-admin-password", role="admin")
    c = client_factory(sut)
    c.login("existing-admin", "existing-admin-password")
    r = c.get(SETTINGS)
    assert r.status_code == 200, r.text
    assert r.json()["setup_wizard_state"] == "skipped"


def test_bootstrap_explicitly_keeps_setup_wizard_pending_for_true_first_run(server_factory, client_factory) -> None:
    sut = server_factory()
    c = client_factory(sut)
    response = c.bootstrap("fresh-admin", "bootstrap-password-strong")
    assert response.status_code == 200, response.text
    c.login("fresh-admin", "bootstrap-password-strong")

    settings_response = c.get(SETTINGS)
    assert settings_response.status_code == 200, settings_response.text
    assert settings_response.json()["setup_wizard_state"] == "pending"


def test_suite_security_overview_get_ok(admin) -> None:
    r = admin.get(f"{API}/suite/security-overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "restart_required_note" in body
    assert "session_signing_configured" in body
    assert "allowed_browser_origins_count" in body
    assert "standard_session_idle_timeout_plain" in body
    assert "trusted_session_absolute_timeout_plain" in body


def test_suite_settings_put_persists(server_factory, client_factory) -> None:
    sut = server_factory()
    admin = h.signed_in_admin(sut, client_factory)
    r = admin.put_csrf(
        SETTINGS,
        {
            "product_display_name": "House Library",
            "signed_in_home_notice": "Welcome back.",
            "setup_wizard_state": "skipped",
            "app_timezone": "UTC",
            "log_retention_days": 45,
            "configuration_backup_enabled": True,
            "configuration_backup_interval_hours": 12,
            "configuration_backup_preferred_time": "03:30",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["product_display_name"] == "House Library"
    assert r.json()["signed_in_home_notice"] == "Welcome back."
    assert r.json()["setup_wizard_state"] == "skipped"
    assert r.json()["log_retention_days"] == 45
    assert r.json()["configuration_backup_enabled"] is True
    assert r.json()["configuration_backup_interval_hours"] == 12
    assert r.json()["configuration_backup_preferred_time"] == "03:30"

    r2 = admin.get(SETTINGS)
    assert r2.status_code == 200
    assert r2.json()["product_display_name"] == "House Library"

    with seed.stopped(sut, restart=False) as conn:
        rows = seed.rows(conn, "SELECT * FROM suite_settings WHERE id = 1")
    assert len(rows) == 1
    row = rows[0]
    assert row["product_display_name"] == "House Library"
    assert row["setup_wizard_state"] == "skipped"
    assert row["log_retention_days"] == 45
    assert bool(row["configuration_backup_enabled"]) is True
    assert row["configuration_backup_interval_hours"] == 12
    assert row["configuration_backup_preferred_time"] == "03:30"


def test_suite_settings_put_viewer_forbidden(server, client_factory) -> None:
    viewer = h.signed_in_viewer(server, client_factory)
    r = viewer.put_csrf(
        SETTINGS,
        {
            "product_display_name": "X",
            "signed_in_home_notice": None,
            "app_timezone": "UTC",
            "log_retention_days": 30,
        },
    )
    assert r.status_code == 403


def test_apply_suite_settings_put_rejects_blank_name(admin) -> None:
    r = admin.put_csrf(
        SETTINGS,
        {
            "product_display_name": "   ",
            "signed_in_home_notice": None,
            "app_timezone": "UTC",
            "log_retention_days": 30,
        },
    )
    assert r.status_code == 400, r.text
    assert "empty" in r.json()["detail"].lower()


def test_apply_suite_settings_put_rejects_invalid_timezone(admin) -> None:
    r = admin.put_csrf(
        SETTINGS,
        {
            "product_display_name": "Weir",
            "signed_in_home_notice": None,
            "app_timezone": "Not/A_Real_Zone",
            "log_retention_days": 30,
        },
    )
    assert r.status_code == 400, r.text
    assert "timezone" in r.json()["detail"].lower()


def test_log_retention_does_not_prune_activity_history(server_factory, client_factory) -> None:
    sut = server_factory()
    body = {
        "product_display_name": "Weir",
        "signed_in_home_notice": None,
        "app_timezone": "UTC",
        "log_retention_days": 30,
    }
    admin = h.signed_in_admin(sut, client_factory)
    r = admin.put_csrf(SETTINGS, body)
    assert r.status_code == 200, r.text

    with seed.stopped(sut) as conn:
        seed.insert_activity_event(
            conn,
            event_type="auth.login_succeeded",
            module="auth",
            title="old",
            detail="alice",
            created_at=datetime.now(UTC) - timedelta(days=40),
        )

    admin = client_factory(sut)
    admin.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    r = admin.put_csrf(SETTINGS, body)
    assert r.status_code == 200, r.text

    with seed.stopped(sut, restart=False) as conn:
        n_old = seed.scalar(conn, "SELECT COUNT(*) FROM activity_events WHERE title = 'old'")
    assert int(n_old or 0) == 1


def test_suite_configuration_backup_tick_creates_snapshot(server_factory, client_factory) -> None:
    """With automatic backups on and no backup yet, the running server writes one."""

    sut = server_factory()
    admin = h.signed_in_admin(sut, client_factory)
    r = admin.put_csrf(
        SETTINGS,
        {
            "product_display_name": "Weir",
            "signed_in_home_notice": None,
            "setup_wizard_state": "completed",
            "app_timezone": "UTC",
            "log_retention_days": 30,
            "configuration_backup_enabled": True,
            "configuration_backup_interval_hours": 6,
            "configuration_backup_preferred_time": "04:15",
        },
    )
    assert r.status_code == 200, r.text
    before = admin.get(f"{API}/suite/configuration-backups")
    assert before.status_code == 200, before.text
    rows_before = len(before.json()["items"])

    # The backup schedule checks once a minute; a restart makes it check straight away.
    sut.restart()
    admin = client_factory(sut)
    admin.login(ADMIN_USERNAME, ADMIN_PASSWORD)

    def _backups() -> dict | None:
        listing = admin.get(f"{API}/suite/configuration-backups")
        assert listing.status_code == 200, listing.text
        body = listing.json()
        return body if len(body["items"]) >= rows_before + 1 else None

    listing = wait_until(_backups, timeout_s=90, what="an automatic configuration backup")
    assert listing["items"][0]["size_bytes"] > 0
    assert listing["directory"]

    suite = admin.get(SETTINGS).json()
    assert suite["configuration_backup_last_run_at"] is not None
    assert suite["configuration_backup_preferred_time"] == "04:15"
