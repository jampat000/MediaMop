"""HTTP: media manager connections, and the per-connection inbound secret.

The point of the change these cover is that a manager is data, not schema — so the
tests add a kind that never had columns of its own (``deluno``) and drive it through
the same routes Radarr and Sonarr use.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, auth_put, trusted_browser_origin_headers
from tests.integration_helpers import csrf as fetch_csrf


def _login_admin(client: TestClient) -> None:
    token = fetch_csrf(client)
    response = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": token},
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def operator(client_with_admin: TestClient) -> TestClient:
    """A signed-in operator with no media manager connections left over."""

    _login_admin(client_with_admin)
    for row in client_with_admin.get("/api/v1/media-managers/connections").json():
        client_with_admin.request(
            "DELETE",
            f"/api/v1/media-managers/connections/{row['id']}",
            json={"csrf_token": fetch_csrf(client_with_admin)},
            headers=trusted_browser_origin_headers(),
        )
    return client_with_admin


def _create(client: TestClient, **overrides: Any) -> tuple[int, dict[str, Any]]:
    body = {
        "csrf_token": fetch_csrf(client),
        "kind": "deluno",
        "name": "Deluno",
        "base_url": "http://10.1.1.142:5099",
        "api_key": "deluno_secret_key",
    }
    body.update(overrides)
    response = auth_post(client, "/api/v1/media-managers/connections", json=body)
    return response.status_code, response.json()


def _delete(client: TestClient, connection_id: int) -> int:
    return client.request(
        "DELETE",
        f"/api/v1/media-managers/connections/{connection_id}",
        json={"csrf_token": fetch_csrf(client)},
        headers=trusted_browser_origin_headers(),
    ).status_code


def test_a_manager_with_no_columns_of_its_own_can_be_added(operator: TestClient) -> None:
    code, row = _create(operator)
    assert code == 201, row
    assert row["kind"] == "deluno"
    assert row["base_url"] == "http://10.1.1.142:5099"
    assert row["webhook_url_path"] == "/api/v1/intake/webhook/deluno"
    # Both lanes come with the connection, so a settings screen has something to render
    # without a second call.
    assert sorted(lane["lane"] for lane in row["lanes"]) == ["missing", "upgrade"]


def test_the_api_key_is_never_returned_only_whether_it_is_saved(operator: TestClient) -> None:
    _, row = _create(operator)
    assert row["api_key_is_saved"] is True
    assert "api_key" not in row
    assert "deluno_secret_key" not in str(row)


def test_listing_returns_every_configured_manager(operator: TestClient) -> None:
    _create(operator, name="Deluno", kind="deluno")
    _create(operator, name="Radarr", kind="radarr", base_url="http://10.1.1.5:7878")
    listed = operator.get("/api/v1/media-managers/connections").json()
    assert {row["kind"] for row in listed} == {"deluno", "radarr"}


def test_an_unknown_kind_is_refused(operator: TestClient) -> None:
    code, _ = _create(operator, kind="plex")
    assert code in (400, 422)


def test_duplicate_names_are_refused(operator: TestClient) -> None:
    assert _create(operator, name="Same")[0] == 201
    code, body = _create(operator, name="Same", kind="radarr")
    assert code == 400
    assert "already exists" in body["detail"]


def test_an_address_that_cannot_work_is_refused(operator: TestClient) -> None:
    code, body = _create(operator, base_url="not-a-url")
    assert code == 400
    assert "will not work" in body["detail"]


def test_omitting_the_api_key_on_update_leaves_it_alone(operator: TestClient) -> None:
    _, row = _create(operator)
    updated = auth_put(
        operator,
        f"/api/v1/media-managers/connections/{row['id']}",
        json={"csrf_token": fetch_csrf(operator), "name": "Deluno renamed"},
    ).json()
    assert updated["name"] == "Deluno renamed"
    assert updated["api_key_is_saved"] is True


def test_an_empty_api_key_on_update_clears_it(operator: TestClient) -> None:
    _, row = _create(operator)
    updated = auth_put(
        operator,
        f"/api/v1/media-managers/connections/{row['id']}",
        json={"csrf_token": fetch_csrf(operator), "api_key": ""},
    ).json()
    assert updated["api_key_is_saved"] is False


def test_a_connection_can_be_deleted(operator: TestClient) -> None:
    _, row = _create(operator)
    assert _delete(operator, row["id"]) == 204
    assert operator.get("/api/v1/media-managers/connections").json() == []


def test_a_lane_can_be_saved_per_manager(operator: TestClient) -> None:
    _, row = _create(operator)
    saved = auth_put(
        operator,
        f"/api/v1/media-managers/connections/{row['id']}/lanes/missing",
        json={
            "csrf_token": fetch_csrf(operator),
            "enabled": True,
            "max_items_per_run": 25,
            "retry_delay_minutes": 60,
            "schedule_enabled": True,
            "schedule_days": "Mon,Tue",
            "schedule_start": "01:00",
            "schedule_end": "05:00",
            "schedule_interval_seconds": 900,
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["lane"] == "missing"
    assert body["enabled"] is True
    assert body["schedule_days"] == "Mon,Tue"


def test_routes_require_an_operator_session(client_with_viewer: TestClient) -> None:
    token = fetch_csrf(client_with_viewer)
    auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": token},
    )
    assert client_with_viewer.get("/api/v1/media-managers/connections").status_code == 403


# --- the per-connection inbound secret ---------------------------------------


def _generate_secret(client: TestClient, connection_id: int) -> dict[str, Any]:
    return auth_post(
        client,
        f"/api/v1/media-managers/connections/{connection_id}/webhook-secret",
        json={"csrf_token": fetch_csrf(client)},
    ).json()


def test_a_generated_secret_is_shown_once_and_then_only_reported_as_set(operator: TestClient) -> None:
    _, row = _create(operator)
    assert row["webhook_secret_is_set"] is False

    generated = _generate_secret(operator, row["id"])
    secret = generated["webhook_secret"]
    assert secret
    assert generated["webhook_url_path"] == "/api/v1/intake/webhook/deluno"
    assert generated["header_name"] == "X-Webhook-Secret"

    fetched = operator.get(f"/api/v1/media-managers/connections/{row['id']}").json()
    assert fetched["webhook_secret_is_set"] is True
    assert secret not in str(fetched)


def test_the_intake_webhook_enforces_that_managers_own_secret(operator: TestClient) -> None:
    _, row = _create(operator)
    secret = _generate_secret(operator, row["id"])["webhook_secret"]

    body = {"eventType": "deluno.processor-handoff", "mediaType": "movies", "sourcePath": "/x/y.mkv"}
    assert operator.post("/api/v1/intake/webhook/deluno", json=body).status_code == 401
    assert (
        operator.post("/api/v1/intake/webhook/deluno", json=body, headers={"X-Webhook-Secret": "wrong"}).status_code
        == 401
    )
    # The right secret gets past authorisation; the hand-off then fails on its own
    # merits, because no Refiner watched folder is configured here.
    accepted = operator.post("/api/v1/intake/webhook/deluno", json=body, headers={"X-Webhook-Secret": secret})
    assert accepted.status_code == 400
    assert "watched folder" in accepted.json()["detail"]


def test_one_managers_secret_does_not_gate_another(operator: TestClient) -> None:
    """The point of per-connection secrets: revoking one must not lock out the rest."""

    _, deluno = _create(operator, name="Deluno", kind="deluno")
    _create(operator, name="Radarr", kind="radarr", base_url="http://10.1.1.5:7878")
    _generate_secret(operator, deluno["id"])

    # Radarr has no secret of its own, so it still posts freely while Deluno now
    # requires one.
    assert operator.post("/api/v1/intake/webhook/radarr", json={"eventType": "Grab"}).status_code == 200
    assert operator.post("/api/v1/intake/webhook/deluno", json={"eventType": "Grab"}).status_code == 401
