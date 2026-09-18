"""Contract port of the retired Python backend's tests/test_media_manager_connections_api.py."""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.media_managers._helpers import (
    NO_WEBHOOK_SECRET,
    clear_connections,
    closed_port_url,
    create_connection,
    delete_connection,
)
from tests.contract.support import seed
from tests.contract.support.client import ADMIN_PASSWORD, ADMIN_USERNAME, API, WeirClient
from tests.contract.support.fake_manager import Reply


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return dict(NO_WEBHOOK_SECRET)


@pytest.fixture
def operator(admin: WeirClient) -> WeirClient:
    """A signed-in operator with no media manager connections left over."""

    clear_connections(admin)
    return admin


def _create(client: WeirClient, **overrides: Any) -> tuple[int, dict[str, Any]]:
    response = create_connection(client, **overrides)
    return response.status_code, response.json()


def test_a_manager_with_no_columns_of_its_own_can_be_added(operator: WeirClient) -> None:
    code, row = _create(operator)
    assert code == 201, row
    assert row["kind"] == "deluno"
    assert row["base_url"] == "http://10.1.1.142:5099"
    assert row["webhook_url_path"] == "/api/v1/intake/webhook/deluno"
    assert sorted(lane["lane"] for lane in row["lanes"]) == ["missing", "upgrade"]


def test_the_api_key_is_never_returned_only_whether_it_is_saved(operator: WeirClient) -> None:
    _, row = _create(operator)
    assert row["api_key_is_saved"] is True
    assert "api_key" not in row
    assert "deluno_secret_key" not in str(row)


def test_listing_returns_every_configured_manager(operator: WeirClient) -> None:
    _create(operator, name="Deluno", kind="deluno")
    _create(operator, name="Radarr", kind="radarr", base_url="http://10.1.1.5:7878")
    listed = operator.get(f"{API}/media-managers/connections").json()
    assert {row["kind"] for row in listed} == {"deluno", "radarr"}


def test_an_unknown_kind_is_refused(operator: WeirClient) -> None:
    code, _ = _create(operator, kind="plex")
    assert code in (400, 422)


def test_duplicate_names_are_refused(operator: WeirClient) -> None:
    assert _create(operator, name="Same")[0] == 201
    code, body = _create(operator, name="Same", kind="radarr")
    assert code == 400
    assert "already exists" in body["detail"]


def test_an_address_that_cannot_work_is_refused(operator: WeirClient) -> None:
    code, body = _create(operator, base_url="not-a-url")
    assert code == 400
    assert "will not work" in body["detail"]


def test_omitting_the_api_key_on_update_leaves_it_alone(operator: WeirClient) -> None:
    _, row = _create(operator)
    updated = operator.put_csrf(f"{API}/media-managers/connections/{row['id']}", {"name": "Deluno renamed"}).json()
    assert updated["name"] == "Deluno renamed"
    assert updated["api_key_is_saved"] is True


def test_an_empty_api_key_on_update_clears_it(operator: WeirClient) -> None:
    _, row = _create(operator)
    updated = operator.put_csrf(f"{API}/media-managers/connections/{row['id']}", {"api_key": ""}).json()
    assert updated["api_key_is_saved"] is False


def test_a_connection_can_be_deleted(operator: WeirClient) -> None:
    _, row = _create(operator)
    assert delete_connection(operator, row["id"]).status_code == 204
    assert operator.get(f"{API}/media-managers/connections").json() == []


def test_an_unreachable_connection_is_a_normal_test_result(operator: WeirClient) -> None:
    # The original stubbed the probe; here the address really has nothing listening.
    _, row = _create(operator, base_url=closed_port_url())

    response = operator.post_csrf(f"{API}/media-managers/connections/{row['id']}/test")

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is False
    assert "could not reach" in response.json()["detail"]


def test_removing_a_connection_during_its_test_returns_a_clean_not_found(
    operator: WeirClient, server, client_factory, fake_managers
) -> None:
    fake = fake_managers("deluno")
    _, row = _create(operator, base_url=fake.base_url, api_key=fake.api_key)

    # A second operator session removes the connection while Weir is waiting for the manager.
    other = client_factory(server)
    other.login(ADMIN_USERNAME, ADMIN_PASSWORD)

    def remove_during_probe(_request: Any) -> Reply:
        assert delete_connection(other, row["id"]).status_code == 204
        return Reply(200, {"status": "ok"})

    fake.route("GET", "/api/integrations/external/health", remove_during_probe)
    response = operator.post_csrf(f"{API}/media-managers/connections/{row['id']}/test")

    assert fake.requests_to("GET", "/api/integrations/external/health"), "Weir never probed the manager"
    assert response.status_code == 404, response.text
    assert "removed while its connection test was running" in response.json()["detail"]


def test_a_lane_can_be_saved_per_manager(operator: WeirClient) -> None:
    _, row = _create(operator)
    saved = operator.put_csrf(
        f"{API}/media-managers/connections/{row['id']}/lanes/missing",
        {
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


def test_routes_require_an_operator_session(server, client_factory) -> None:
    probe = client_factory(server)
    if probe.login("bob", "viewer-password-here", expect=None).status_code != 200:
        with seed.stopped(server) as conn:
            seed.insert_user(conn, username="bob", password="viewer-password-here", role="viewer")
    viewer = client_factory(server)
    viewer.login("bob", "viewer-password-here")
    assert viewer.get(f"{API}/media-managers/connections").status_code == 403


# --- the per-connection inbound secret ---------------------------------------


def _generate_secret(client: WeirClient, connection_id: int) -> dict[str, Any]:
    r = client.post_csrf(f"{API}/media-managers/connections/{connection_id}/webhook-secret")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_generated_secret_is_shown_once_and_then_only_reported_as_set(operator: WeirClient) -> None:
    _, row = _create(operator)
    assert row["webhook_secret_is_set"] is False

    generated = _generate_secret(operator, row["id"])
    secret = generated["webhook_secret"]
    assert secret
    assert generated["webhook_url_path"] == "/api/v1/intake/webhook/deluno"
    assert generated["header_name"] == "X-Webhook-Secret"

    fetched = operator.get(f"{API}/media-managers/connections/{row['id']}").json()
    assert fetched["webhook_secret_is_set"] is True
    assert secret not in str(fetched)


def test_the_intake_webhook_enforces_that_managers_own_secret(operator: WeirClient) -> None:
    _, row = _create(operator)
    secret = _generate_secret(operator, row["id"])["webhook_secret"]

    body = {"eventType": "deluno.processor-handoff", "mediaType": "movies", "sourcePath": "/x/y.mkv"}
    assert operator.post(f"{API}/intake/webhook/deluno", json=body).status_code == 401
    assert (
        operator.post(f"{API}/intake/webhook/deluno", json=body, headers={"X-Webhook-Secret": "wrong"}).status_code
        == 401
    )
    # The right secret gets past authorisation; the hand-off then fails on its own merits,
    # because no Processing watched folder is configured on this server.
    accepted = operator.post(f"{API}/intake/webhook/deluno", json=body, headers={"X-Webhook-Secret": secret})
    assert accepted.status_code == 400
    assert "watched folder" in accepted.json()["detail"]


def test_one_managers_secret_does_not_gate_another(operator: WeirClient) -> None:
    """The point of per-connection secrets: revoking one must not lock out the rest."""

    _, deluno = _create(operator, name="Deluno", kind="deluno")
    _create(operator, name="Radarr", kind="radarr", base_url="http://10.1.1.5:7878")
    _generate_secret(operator, deluno["id"])

    assert operator.post(f"{API}/intake/webhook/radarr", json={"eventType": "Grab"}).status_code == 200
    assert operator.post(f"{API}/intake/webhook/deluno", json={"eventType": "Grab"}).status_code == 401
