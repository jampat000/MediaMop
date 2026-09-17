"""Basic contract coverage (auth, status codes, shapes) for system endpoints no original HTTP test covered.

Not a port of one backend test file: the logs, metrics, notification channel, configuration backup,
readiness, pause, security overview and update status routes in the retired Python backend's weir/platform/.
"""

from __future__ import annotations

import pytest

from tests.contract.support.client import API
from tests.contract.system import _helpers as h

LOGS = f"{API}/suite/logs"
SUITE_METRICS = f"{API}/suite/metrics"
CHANNELS = f"{API}/suite/notification-channels"
BACKUPS = f"{API}/suite/configuration-backups"
READINESS = f"{API}/system/readiness"
PAUSE = f"{API}/pause"
SECURITY = f"{API}/suite/security-overview"
UPDATE_STATUS = f"{API}/suite/update-status"

# RFC 6761: ``.invalid`` never resolves, so a test notification can never leave the machine.
UNREACHABLE_HOOK = "https://weir-contract-test.invalid/hook"
PUBLIC_LOOKING_HOOK = "https://hooks.weir-contract-test.invalid/other"


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    # The update status route asks GitHub for the latest release; this module's server cannot reach it.
    return dict(h.NO_INTERNET_ENV)


@pytest.fixture(scope="module", autouse=True)
def _users(server) -> None:
    h.seed_users(server)


@pytest.fixture
def viewer(server, client_factory):
    return h.signed_in_viewer(server, client_factory)


# --- /suite/logs ------------------------------------------------------------------------------------


def test_suite_logs_requires_auth(client) -> None:
    assert client.get(LOGS).status_code == 401


def test_suite_logs_shape(admin, viewer) -> None:
    for c in (admin, viewer):
        r = c.get(LOGS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"items", "total", "counts"}
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert set(body["counts"]) == {"error", "warning", "information"}
        for item in body["items"]:
            assert {"timestamp", "level", "component", "message", "logger"}.issubset(item)


def test_suite_logs_level_filter_only_returns_that_level(admin) -> None:
    r = admin.get(LOGS, params={"level": "ERROR", "limit": 50})
    assert r.status_code == 200, r.text
    assert all(item["level"] == "ERROR" for item in r.json()["items"])


# --- /suite/metrics ---------------------------------------------------------------------------------


def test_suite_metrics_requires_auth(client) -> None:
    assert client.get(SUITE_METRICS).status_code == 401


def test_suite_metrics_shape(admin, viewer) -> None:
    for c in (admin, viewer):
        r = c.get(SUITE_METRICS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {
            "uptime_seconds",
            "total_requests",
            "average_response_ms",
            "error_log_count",
            "status_counts",
            "busiest_routes",
        }
        assert body["uptime_seconds"] >= 0
        assert body["total_requests"] >= 1
        assert isinstance(body["status_counts"], dict)
        for route in body["busiest_routes"]:
            assert set(route) == {"route", "request_count", "average_response_ms"}


# --- /suite/notification-channels -------------------------------------------------------------------


def test_notification_channels_require_auth(client) -> None:
    assert client.get(CHANNELS).status_code == 401


def test_notification_channels_forbidden_for_viewer(viewer) -> None:
    assert viewer.get(CHANNELS).status_code == 403
    r = viewer.post_csrf(CHANNELS, {"label": "x", "provider": "webhook", "url": UNREACHABLE_HOOK})
    assert r.status_code == 403


def test_notification_channels_list_shape(admin) -> None:
    r = admin.get(CHANNELS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"items", "supported_events", "supported_providers"}
    assert isinstance(body["items"], list)
    assert "job_failed" in body["supported_events"]
    assert set(body["supported_providers"]) >= {"webhook", "discord"}


def test_notification_channel_create_update_test_delete(admin) -> None:
    created = admin.post_csrf(
        CHANNELS,
        {"label": "  Contract hook  ", "provider": "webhook", "url": UNREACHABLE_HOOK, "events": ["job_failed"]},
    )
    assert created.status_code == 201, created.text
    channel = created.json()
    assert set(channel) == {"id", "label", "provider", "url", "events", "enabled", "created_at", "updated_at"}
    assert channel["label"] == "Contract hook"
    assert channel["provider"] == "webhook"
    assert channel["url"] == UNREACHABLE_HOOK
    assert channel["events"] == ["job_failed"]
    assert channel["enabled"] is True
    path = f"{CHANNELS}/{channel['id']}"

    listed = admin.get(CHANNELS).json()["items"]
    assert channel["id"] in {item["id"] for item in listed}

    updated = admin.put_csrf(
        path,
        {
            "label": "Renamed hook",
            "provider": "discord",
            "url": PUBLIC_LOOKING_HOOK,
            "events": ["job_completed", "job_failed"],
            "enabled": False,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["label"] == "Renamed hook"
    assert updated.json()["provider"] == "discord"
    assert updated.json()["url"] == PUBLIC_LOOKING_HOOK
    assert updated.json()["events"] == ["job_completed", "job_failed"]
    assert updated.json()["enabled"] is False

    tested = admin.post_csrf(f"{path}/test", {})
    assert tested.status_code == 200, tested.text
    assert set(tested.json()) == {"ok", "error"}
    assert tested.json()["ok"] is False
    assert isinstance(tested.json()["error"], str) and tested.json()["error"]

    deleted = admin.delete_csrf(path)
    assert deleted.status_code == 204, deleted.text
    assert channel["id"] not in {item["id"] for item in admin.get(CHANNELS).json()["items"]}
    assert admin.delete_csrf(path).status_code == 404


def test_notification_channel_create_rejects_bad_input(admin) -> None:
    good = {"label": "x", "provider": "webhook", "url": UNREACHABLE_HOOK, "events": ["job_failed"]}

    assert admin.post(CHANNELS, json=good).status_code == 422  # no csrf_token
    assert admin.post_csrf(CHANNELS, {**good, "provider": "carrier-pigeon"}).status_code == 400
    assert admin.post_csrf(CHANNELS, {**good, "url": "http://127.0.0.1:8080/hook"}).status_code == 400
    assert admin.post_csrf(CHANNELS, {**good, "url": "ftp://example.invalid/hook"}).status_code == 400
    assert admin.post_csrf(CHANNELS, {**good, "events": ["not_an_event"]}).status_code == 400
    assert admin.post_csrf(CHANNELS, {**good, "events": []}).status_code == 400


def test_notification_channel_missing_ids_are_404(admin) -> None:
    body = {"label": "x", "provider": "webhook", "url": UNREACHABLE_HOOK, "events": ["job_failed"]}
    assert admin.put_csrf(f"{CHANNELS}/999999", body).status_code == 404
    assert admin.post_csrf(f"{CHANNELS}/999999/test", {}).status_code == 404
    assert admin.delete_csrf(f"{CHANNELS}/999999").status_code == 404


def test_notification_channel_delete_without_csrf_header_is_refused(admin) -> None:
    created = admin.post_csrf(
        CHANNELS, {"label": "Keep me", "provider": "webhook", "url": UNREACHABLE_HOOK, "events": ["job_failed"]}
    )
    assert created.status_code == 201, created.text
    path = f"{CHANNELS}/{created.json()['id']}"
    try:
        assert admin.delete(path).status_code == 400
    finally:
        assert admin.delete_csrf(path).status_code == 204


# --- /suite/configuration-backups ---------------------------------------------------------------------


def test_configuration_backups_require_auth(client) -> None:
    assert client.get(BACKUPS).status_code == 401


def test_configuration_backups_forbidden_for_viewer(viewer) -> None:
    assert viewer.get(BACKUPS).status_code == 403


def test_configuration_backups_shape(admin) -> None:
    r = admin.get(BACKUPS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"directory", "items"}
    assert isinstance(body["directory"], str)
    for item in body["items"]:
        assert set(item) == {"id", "created_at", "file_name", "size_bytes"}


def test_configuration_backup_download_missing_is_404(admin) -> None:
    assert admin.get(f"{BACKUPS}/999999/download").status_code == 404


# --- /ready and /system/readiness ---------------------------------------------------------------------


def test_public_ready_needs_no_sign_in(client) -> None:
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    assert r.json() == {"ready": True, "status": "ready"}


def test_system_readiness_requires_auth(client) -> None:
    assert client.get(READINESS).status_code == 401


def test_system_readiness_shape(admin, viewer) -> None:
    for c in (admin, viewer):
        r = c.get(READINESS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"ready", "version", "status", "startup_seconds", "steps", "worker_health"}
        assert body["ready"] is True
        assert body["status"] == "ready"
        assert body["version"]
        assert body["startup_seconds"] >= 0
        names = set()
        for step in body["steps"]:
            assert set(step) == {"name", "status", "detail"}
            assert step["status"] == "ready"
            names.add(step["name"])
        assert {"database", "workers"}.issubset(names)
        for worker in body["worker_health"]:
            assert {"module", "expected_workers", "active_workers", "status", "detail"}.issubset(worker)


# --- /pause ------------------------------------------------------------------------------------------


def test_pause_requires_auth(client) -> None:
    assert client.get(PAUSE).status_code == 401


def test_pause_readable_by_viewer_but_not_changeable(viewer) -> None:
    r = viewer.get(PAUSE)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"paused", "paused_until", "scan_while_paused", "reason", "in_flight_policy"}
    assert viewer.put_csrf(PAUSE, {"paused": True}).status_code == 403


def test_pause_put_rejects_unknown_fields(admin) -> None:
    assert admin.put_csrf(PAUSE, {"paused": False, "not_a_field": 1}).status_code == 422


def test_pause_get_reflects_put(admin) -> None:
    put = admin.put_csrf(PAUSE, {"paused": False, "scan_while_paused": True})
    assert put.status_code == 200, put.text
    assert admin.get(PAUSE).json() == put.json()


# --- /suite/security-overview -----------------------------------------------------------------------


def test_security_overview_requires_auth(client) -> None:
    assert client.get(SECURITY).status_code == 401


def test_security_overview_shape(viewer) -> None:
    r = viewer.get(SECURITY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "session_signing_configured",
        "sign_in_cookie_https_mode",
        "sign_in_cookie_https_plain",
        "sign_in_cookie_same_site",
        "standard_session_idle_timeout_plain",
        "standard_session_absolute_timeout_plain",
        "trusted_session_idle_timeout_plain",
        "trusted_session_absolute_timeout_plain",
        "extra_https_hardening_enabled",
        "sign_in_attempt_limit",
        "sign_in_attempt_window_plain",
        "first_time_setup_attempt_limit",
        "first_time_setup_attempt_window_plain",
        "allowed_browser_origins_count",
        "restart_required_note",
    }
    assert body["session_signing_configured"] is True
    assert body["sign_in_attempt_limit"] >= 1
    assert body["allowed_browser_origins_count"] == 0


# --- /suite/update-status -----------------------------------------------------------------------------


def test_update_status_requires_auth(client) -> None:
    assert client.get(UPDATE_STATUS).status_code == 401
    assert client.get(f"{API}/suite/settings/update-status").status_code == 401


@pytest.mark.parametrize("path", [UPDATE_STATUS, f"{API}/suite/settings/update-status"])
def test_update_status_when_the_release_feed_is_unreachable(admin, path: str) -> None:
    """With no route to the release feed the check says so instead of failing or guessing."""

    r = admin.get(path)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"current_version", "install_type", "status", "summary", "in_app_upgrade_supported"}.issubset(body)
    assert body["current_version"]
    assert body["install_type"] in {"windows", "docker", "source"}
    assert body["status"] == "unavailable"
    assert body["summary"]
    assert body.get("latest_version") is None
