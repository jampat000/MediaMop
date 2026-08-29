"""The standing gate: every capability in the epic reaches the v1 API.

This is not a test of any one feature. It is the guard that makes #346 a *standing*
requirement rather than a box ticked once — the Refiner API drifted from the UI in both
directions before, which is exactly how the gap went unnoticed:

- endpoints with no consumer, reachable and untested from the client side;
- client helpers with no screen;
- capabilities with neither, which is what the five dormant job families were.

A capability that is deliberately API-only is fine. A capability that is *accidentally*
missing is what this catches. Adding a surface to the epic means adding it here, and a
route being renamed without this being updated fails the build.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration_helpers import auth_get, auth_post, csrf

#: Every surface the epic promises, as (method, path). Paths are the route templates
#: FastAPI registers, so a rename is a failure rather than a silent gap.
REQUIRED_SURFACES: tuple[tuple[str, str], ...] = (
    # Libraries — full CRUD, reorder, discovery.
    ("GET", "/api/v1/refiner/libraries"),
    ("POST", "/api/v1/refiner/libraries"),
    ("GET", "/api/v1/refiner/libraries/{library_id}"),
    ("PUT", "/api/v1/refiner/libraries/{library_id}"),
    ("DELETE", "/api/v1/refiner/libraries/{library_id}"),
    ("POST", "/api/v1/refiner/libraries/reorder"),
    # Rule sets — CRUD, carrying sorters, metadata options and original-language options.
    ("GET", "/api/v1/refiner/rule-sets"),
    ("POST", "/api/v1/refiner/rule-sets"),
    ("PUT", "/api/v1/refiner/rule-sets/{rule_set_id}"),
    ("DELETE", "/api/v1/refiner/rule-sets/{rule_set_id}"),
    # Files — list, log, remove, requeue, move to top, bulk requeue, why-held.
    ("GET", "/api/v1/refiner/files"),
    ("DELETE", "/api/v1/refiner/files/{file_id}"),
    ("GET", "/api/v1/refiner/files/{file_id}/log"),
    ("GET", "/api/v1/refiner/files/{file_id}/log/download"),
    ("GET", "/api/v1/refiner/files/{file_id}/why-held"),
    ("POST", "/api/v1/refiner/files/{file_id}/requeue"),
    ("POST", "/api/v1/refiner/files/{file_id}/move-to-top"),
    ("POST", "/api/v1/refiner/files/requeue"),
    # Runtime control.
    ("GET", "/api/v1/suite/pause"),
    ("PUT", "/api/v1/suite/pause"),
    # Capacity and schedules live on the operator settings and the library respectively,
    # both covered above and by the settings surface.
    ("GET", "/api/v1/refiner/operator-settings"),
    ("PUT", "/api/v1/refiner/operator-settings"),
    # Maintenance — trigger and read every promoted family.
    ("GET", "/api/v1/refiner/maintenance"),
    ("POST", "/api/v1/refiner/maintenance/run"),
    # Hardware.
    ("GET", "/api/v1/refiner/hardware"),
    # Metadata provider.
    ("GET", "/api/v1/refiner/metadata-provider"),
    ("PUT", "/api/v1/refiner/metadata-provider"),
    ("POST", "/api/v1/refiner/metadata-provider/test"),
)

#: Prefixes retired during the epic. A route reappearing under one of these means a lane
#: was resurrected without the decision being revisited.
RETIRED_SURFACES: tuple[str, ...] = (
    "/api/v1/refiner/jobs/candidate-gate/enqueue",
    "/api/v1/refiner/jobs/supplied-payload-evaluation/enqueue",
)


def _documented(client: TestClient) -> dict:
    """The generated schema, which is what a generated client actually sees.

    Deliberately the schema rather than a walk of the ASGI route table: a route that is
    registered but undocumented is a route no generated client can call, so the schema is
    the stricter and more useful source of truth.
    """

    return client.get("/openapi.json").json().get("paths", {})


def test_every_capability_in_the_epic_reaches_the_v1_api(client_with_admin: TestClient) -> None:
    """The gate. A missing surface here is a capability that exists only in the UI."""

    documented = _documented(client_with_admin)
    missing = [
        (method, path)
        for method, path in REQUIRED_SURFACES
        if path not in documented or method.lower() not in documented[path]
    ]

    assert not missing, f"Capabilities missing from the v1 API and its OpenAPI schema: {missing}"


def test_retired_lanes_have_not_come_back(client_with_admin: TestClient) -> None:
    """Both were reachable, undocumented and called by nothing. They are not endpoints
    any more, and a route reappearing means a decision was reversed by accident."""

    documented = _documented(client_with_admin)
    resurrected = [path for path in RETIRED_SURFACES if path in documented]

    assert not resurrected, f"Retired endpoints are reachable again: {resurrected}"


# --- auth and CSRF on the new endpoints ----------------------------------------------


def _signed_in(client: TestClient) -> TestClient:
    token = csrf(client)
    response = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": token},
    )
    assert response.status_code == 200, response.text
    return client


def test_maintenance_state_needs_a_session(client_with_admin: TestClient) -> None:
    assert auth_get(client_with_admin, "/api/v1/refiner/maintenance").status_code == 401


def test_maintenance_state_lists_every_promoted_family(client_with_admin: TestClient) -> None:
    body = auth_get(_signed_in(client_with_admin), "/api/v1/refiner/maintenance").json()

    families = {row["family"] for row in body["families"]}
    assert families == {"work_temp_stale_sweep", "failure_cleanup"}
    # The description is the operator-facing part: failure cleanup deletes originals and
    # has to say so where the switch is.
    cleanup = next(row for row in body["families"] if row["family"] == "failure_cleanup")
    assert "deletes the original" in cleanup["description"]


def test_triggering_maintenance_without_a_csrf_token_is_refused(client_with_admin: TestClient) -> None:
    client = _signed_in(client_with_admin)

    response = auth_post(
        client, "/api/v1/refiner/maintenance/run", json={"family": "work_temp_stale_sweep", "media_scope": "movie"}
    )

    assert response.status_code == 422


def test_triggering_maintenance_queues_a_run(client_with_admin: TestClient) -> None:
    client = _signed_in(client_with_admin)

    response = auth_post(
        client,
        "/api/v1/refiner/maintenance/run",
        json={
            "csrf_token": csrf(client),
            "family": "work_temp_stale_sweep",
            "media_scope": "movie",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["queued"] is True


def test_an_unknown_family_is_refused(client_with_admin: TestClient) -> None:
    client = _signed_in(client_with_admin)

    response = auth_post(
        client,
        "/api/v1/refiner/maintenance/run",
        json={"csrf_token": csrf(client), "family": "something_invented", "media_scope": "movie"},
    )

    assert response.status_code == 422


def test_the_hardware_report_needs_a_session_and_then_answers(client_with_admin: TestClient) -> None:
    assert auth_get(client_with_admin, "/api/v1/refiner/hardware").status_code == 401

    body = auth_get(_signed_in(client_with_admin), "/api/v1/refiner/hardware").json()

    assert "available_methods" in body
    assert "selectable_vendors" in body
    assert body["detail"]


def test_the_metadata_provider_never_returns_the_key(client_with_admin: TestClient) -> None:
    """The key is write-only. A screen can say one is configured without being able to leak it."""

    client = _signed_in(client_with_admin)
    auth_get(client, "/api/v1/refiner/metadata-provider")

    from tests.integration_helpers import auth_put

    saved = auth_put(
        client,
        "/api/v1/refiner/metadata-provider",
        json={
            "csrf_token": csrf(client),
            "provider": "tmdb",
            "base_url": "https://metadata.example.workers.dev",
            "api_key": "a-secret-key",
        },
    )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["key_configured"] is True
    assert "a-secret-key" not in saved.text
    assert body["base_url"] == "https://metadata.example.workers.dev"


def test_the_metadata_provider_key_survives_a_save_that_omits_it(client_with_admin: TestClient) -> None:
    """Saving the address must not require re-typing a secret the screen cannot show back."""

    from tests.integration_helpers import auth_put

    client = _signed_in(client_with_admin)
    auth_put(
        client,
        "/api/v1/refiner/metadata-provider",
        json={"csrf_token": csrf(client), "provider": "tmdb", "base_url": "https://one.example.com", "api_key": "k"},
    )

    body = auth_put(
        client,
        "/api/v1/refiner/metadata-provider",
        json={"csrf_token": csrf(client), "provider": "tmdb", "base_url": "https://two.example.com"},
    ).json()

    assert body["key_configured"] is True
    assert body["base_url"] == "https://two.example.com"
