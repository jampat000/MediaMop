"""GET/PUT ``/api/v1/fetcher/arr-operator-settings`` and connection-test Activity."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings

from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.models import ActivityEvent

from tests.integration_helpers import auth_post, csrf as fetch_csrf, trusted_browser_origin_headers


_LANE_KEYS = (
    "enabled",
    "max_items_per_run",
    "retry_delay_minutes",
    "schedule_enabled",
    "schedule_days",
    "schedule_start",
    "schedule_end",
    "schedule_interval_seconds",
)


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _put_body_from_get(client: TestClient, csrf_token: str) -> dict:
    r = client.get("/api/v1/fetcher/arr-operator-settings")
    assert r.status_code == 200, r.text
    b = r.json()

    def lane(src: dict) -> dict:
        return {k: src[k] for k in _LANE_KEYS}

    return {
        "csrf_token": csrf_token,
        "sonarr_missing": lane(b["sonarr_missing"]),
        "sonarr_upgrade": lane(b["sonarr_upgrade"]),
        "radarr_missing": lane(b["radarr_missing"]),
        "radarr_upgrade": lane(b["radarr_upgrade"]),
    }


def test_arr_operator_settings_get_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r.status_code == 401


def test_arr_operator_settings_get_ok(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("sonarr_missing", "sonarr_upgrade", "radarr_missing", "radarr_upgrade"):
        lane = b[k]
        for field in _LANE_KEYS:
            assert field in lane
    assert "schedule_timezone" in b
    assert "connection_note" in b
    assert "interval_restart_note" in b
    assert isinstance(b["sonarr_server_configured"], bool)
    assert b["sonarr_connection"]["status_headline"] == "Connection status: Not checked yet"
    assert b["radarr_connection"]["status_headline"] == "Connection status: Not checked yet"


def test_arr_operator_settings_schedule_timezone_comes_from_suite_settings(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r_put = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "MediaMop",
            "signed_in_home_notice": None,
            "app_timezone": "America/New_York",
            "log_retention_days": 30,
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    r = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r.status_code == 200, r.text
    assert r.json()["schedule_timezone"] == "America/New_York"


def test_connection_status_headline_variants() -> None:
    from mediamop.modules.fetcher.fetcher_arr_operator_settings_service import _connection_status_headline

    assert _connection_status_headline(last_ok=None, last_at=None, detail=None) == "Connection status: Not checked yet"
    now = datetime.now(timezone.utc)
    assert _connection_status_headline(last_ok=True, last_at=now, detail="x") == "Connection status: OK"
    assert (
        _connection_status_headline(
            last_ok=False,
            last_at=now,
            detail="TV library connection is not set up yet. Add keys.",
        )
        == "Connection status: Not set up yet"
    )
    assert (
        _connection_status_headline(last_ok=False, last_at=now, detail="MediaMop could reach your TV library app")
        == "Connection status: Failed"
    )


def test_arr_connection_put_sonarr_persists_url_and_key(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/fetcher/arr-connection/sonarr",
        json={
            "csrf_token": tok,
            "enabled": True,
            "base_url": "http://sonarr-put-test.example:8989",
            "api_key": "secret-key-put-test-sonarr",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    sc = r.json()["sonarr_connection"]
    assert sc["base_url"] == "http://sonarr-put-test.example:8989"
    assert sc["api_key_is_saved"] is True
    assert sc["status_headline"] == "Connection status: Not checked yet"

    tok2 = fetch_csrf(client_with_admin)
    r2 = client_with_admin.put(
        "/api/v1/fetcher/arr-connection/sonarr",
        json={
            "csrf_token": tok2,
            "enabled": True,
            "base_url": "http://sonarr-put-test.example:8989",
            "api_key": "",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["sonarr_connection"]["api_key_is_saved"] is True


def test_arr_connection_put_radarr_persists(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/fetcher/arr-connection/radarr",
        json={
            "csrf_token": tok,
            "enabled": True,
            "base_url": "http://radarr-put-test.example:7878",
            "api_key": "secret-key-put-test-radarr",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    rc = r.json()["radarr_connection"]
    assert rc["base_url"] == "http://radarr-put-test.example:7878"
    assert rc["api_key_is_saved"] is True


def test_arr_operator_settings_put_bad_days_400(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    body = _put_body_from_get(client_with_admin, tok)
    body["sonarr_missing"]["schedule_days"] = "NotAWeekday"
    r = client_with_admin.put(
        "/api/v1/fetcher/arr-operator-settings",
        json=body,
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 400, r.text
    assert "Mon" in r.json().get("detail", "") or "day" in r.json().get("detail", "").lower()


def test_arr_lane_put_updates_only_that_lane(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r0.status_code == 200, r0.text
    baseline = r0.json()
    upgrade_before = baseline["radarr_upgrade"]
    lane = {k: baseline["sonarr_missing"][k] for k in _LANE_KEYS}
    lane["max_items_per_run"] = 77
    r = client_with_admin.put(
        "/api/v1/fetcher/arr-operator-settings/lanes/sonarr_missing",
        json={"csrf_token": tok, "lane": lane},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sonarr_missing"]["max_items_per_run"] == 77
    assert r.json()["radarr_upgrade"] == upgrade_before


def test_arr_lane_put_bad_days_400(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r0.status_code == 200, r0.text
    lane = {k: r0.json()["sonarr_missing"][k] for k in _LANE_KEYS}
    lane["schedule_days"] = "NotAWeekday"
    r = client_with_admin.put(
        "/api/v1/fetcher/arr-operator-settings/lanes/sonarr_missing",
        json={"csrf_token": tok, "lane": lane},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 400, r.text
    assert "Mon" in r.json().get("detail", "") or "day" in r.json().get("detail", "").lower()


def test_arr_operator_settings_put_persists_interval(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    body = _put_body_from_get(client_with_admin, tok)
    body["radarr_upgrade"]["schedule_interval_seconds"] = 7200
    r = client_with_admin.put(
        "/api/v1/fetcher/arr-operator-settings",
        json=body,
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["radarr_upgrade"]["schedule_interval_seconds"] == 7200
    r2 = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r2.json()["radarr_upgrade"]["schedule_interval_seconds"] == 7200


def test_arr_connection_test_sonarr_records_activity(
    client_with_admin: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OkClient:
        def __init__(self, *_a, **_k) -> None:
            pass

        def health_ok(self) -> None:
            return None

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_operator_settings_api.FetcherArrV3Client",
        _OkClient,
    )
    _login_admin(client_with_admin)
    old = client_with_admin.app.state.settings
    client_with_admin.app.state.settings = replace(
        old,
        fetcher_sonarr_base_url="http://sonarr-arr-test.local",
        fetcher_sonarr_api_key="test-api-key-arr",
    )

    from mediamop.core.db import create_db_engine, create_session_factory

    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        before = db.scalar(select(func.max(ActivityEvent.id)))

    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.post(
        "/api/v1/fetcher/arr-operator-settings/connection-test",
        json={"csrf_token": tok, "app": "sonarr"},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True

    with fac() as db:
        row = db.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.id > (before or 0))
            .where(ActivityEvent.event_type == act_c.FETCHER_ARR_CONNECTION_TEST_SUCCEEDED)
            .order_by(ActivityEvent.id.desc()),
        ).first()
        assert row is not None
        assert row.module == "fetcher"


def test_arr_connection_test_radarr_records_activity(
    client_with_admin: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OkClient:
        def __init__(self, *_a, **_k) -> None:
            pass

        def health_ok(self) -> None:
            return None

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_operator_settings_api.FetcherArrV3Client",
        _OkClient,
    )
    _login_admin(client_with_admin)
    old = client_with_admin.app.state.settings
    client_with_admin.app.state.settings = replace(
        old,
        fetcher_radarr_base_url="http://radarr-arr-test.local",
        fetcher_radarr_api_key="test-api-key-radarr",
    )

    from mediamop.core.db import create_db_engine, create_session_factory

    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        before = db.scalar(select(func.max(ActivityEvent.id)))

    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.post(
        "/api/v1/fetcher/arr-operator-settings/connection-test",
        json={"csrf_token": tok, "app": "radarr"},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    with fac() as db:
        row = db.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.id > (before or 0))
            .where(ActivityEvent.event_type == act_c.FETCHER_ARR_CONNECTION_TEST_SUCCEEDED)
            .order_by(ActivityEvent.id.desc()),
        ).first()
        assert row is not None
        assert row.title == "Movie library connection check succeeded"


def test_arr_connection_test_sonarr_not_configured_sets_status_headline(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    old = client_with_admin.app.state.settings
    client_with_admin.app.state.settings = replace(
        old,
        fetcher_sonarr_base_url="",
        fetcher_sonarr_api_key="",
    )
    tok = fetch_csrf(client_with_admin)
    r_put = client_with_admin.put(
        "/api/v1/fetcher/arr-connection/sonarr",
        json={"csrf_token": tok, "enabled": False, "base_url": "", "api_key": ""},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    tok2 = fetch_csrf(client_with_admin)
    r = client_with_admin.post(
        "/api/v1/fetcher/arr-operator-settings/connection-test",
        json={"csrf_token": tok2, "app": "sonarr"},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False
    r3 = client_with_admin.get("/api/v1/fetcher/arr-operator-settings")
    assert r3.json()["sonarr_connection"]["status_headline"] == "Connection status: Not set up yet"


def test_arr_connection_test_sonarr_draft_without_save(
    client_with_admin: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Draft ``enabled``/URL/key on POST tests unsaved form values (row can be disabled with no env)."""

    seen: list[tuple[str, str]] = []

    class _OkClient:
        def __init__(self, base: str, key: str) -> None:
            seen.append((base, key))

        def health_ok(self) -> None:
            return None

    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_arr_operator_settings_api.FetcherArrV3Client",
        _OkClient,
    )
    _login_admin(client_with_admin)
    old = client_with_admin.app.state.settings
    client_with_admin.app.state.settings = replace(
        old,
        fetcher_sonarr_base_url="",
        fetcher_sonarr_api_key="",
    )
    tok = fetch_csrf(client_with_admin)
    r_put = client_with_admin.put(
        "/api/v1/fetcher/arr-connection/sonarr",
        json={"csrf_token": tok, "enabled": False, "base_url": "", "api_key": ""},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    tok2 = fetch_csrf(client_with_admin)
    r = client_with_admin.post(
        "/api/v1/fetcher/arr-operator-settings/connection-test",
        json={
            "csrf_token": tok2,
            "app": "sonarr",
            "enabled": True,
            "base_url": "http://sonarr-draft.local:8989",
            "api_key": "draft-key-123",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert seen == [("http://sonarr-draft.local:8989", "draft-key-123")]


def test_arr_connection_test_viewer_forbidden(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    tok2 = fetch_csrf(client_with_viewer)
    r = client_with_viewer.post(
        "/api/v1/fetcher/arr-operator-settings/connection-test",
        json={"csrf_token": tok2, "app": "radarr"},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 403
