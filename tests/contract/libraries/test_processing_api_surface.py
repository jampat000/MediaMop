"""Port of the retired Python backend's tests/test_processing_api_surface.py."""

from __future__ import annotations

from tests.contract.support.client import API

#: Every surface the epic promises, as (method, path), in the generated OpenAPI schema.
REQUIRED_SURFACES: tuple[tuple[str, str], ...] = (
    # Libraries — full CRUD, reorder, discovery.
    ("GET", "/api/v1/processing/libraries"),
    ("POST", "/api/v1/processing/libraries"),
    ("GET", "/api/v1/processing/libraries/{library_id}"),
    ("PUT", "/api/v1/processing/libraries/{library_id}"),
    ("DELETE", "/api/v1/processing/libraries/{library_id}"),
    ("POST", "/api/v1/processing/libraries/reorder"),
    # Whether the reject failure policy can be offered for a library's managers (#471).
    ("GET", "/api/v1/processing/reject-support"),
    # Rule sets — CRUD, carrying sorters, metadata options and original-language options.
    ("GET", "/api/v1/processing/rule-sets"),
    ("POST", "/api/v1/processing/rule-sets"),
    ("PUT", "/api/v1/processing/rule-sets/{rule_set_id}"),
    ("DELETE", "/api/v1/processing/rule-sets/{rule_set_id}"),
    # Files — list, log, remove, requeue, move to top, bulk requeue, why-held.
    ("GET", "/api/v1/processing/files"),
    ("DELETE", "/api/v1/processing/files/{file_id}"),
    ("GET", "/api/v1/processing/files/{file_id}/log"),
    ("GET", "/api/v1/processing/files/{file_id}/log/download"),
    ("GET", "/api/v1/processing/files/{file_id}/why-held"),
    ("POST", "/api/v1/processing/files/{file_id}/requeue"),
    ("POST", "/api/v1/processing/files/{file_id}/move-to-top"),
    ("POST", "/api/v1/processing/files/requeue"),
    # Runtime control.
    ("GET", "/api/v1/pause"),
    ("PUT", "/api/v1/pause"),
    ("GET", "/api/v1/processing/operator-settings"),
    ("PUT", "/api/v1/processing/operator-settings"),
    # Maintenance — trigger and read every promoted family.
    ("GET", "/api/v1/processing/maintenance"),
    ("POST", "/api/v1/processing/maintenance/run"),
    # Hardware.
    ("GET", "/api/v1/processing/hardware"),
    # Metadata provider.
    ("GET", "/api/v1/processing/metadata-provider"),
    ("PUT", "/api/v1/processing/metadata-provider"),
    ("POST", "/api/v1/processing/metadata-provider/test"),
)

#: Prefixes retired during the epic.
RETIRED_SURFACES: tuple[str, ...] = (
    "/api/v1/processing/jobs/candidate-gate/enqueue",
    "/api/v1/processing/jobs/supplied-payload-evaluation/enqueue",
    # Scope-shaped views that resolved "movie" and "tv" to whichever library came first (#460).
    "/api/v1/processing/path-settings",
    "/api/v1/processing/remux-rules-settings",
)


def _documented(client) -> dict:
    r = client.get("/openapi.json")
    assert r.status_code == 200, r.text
    return r.json().get("paths", {})


def test_every_capability_in_the_epic_reaches_the_v1_api(client) -> None:
    documented = _documented(client)
    missing = [
        (method, path)
        for method, path in REQUIRED_SURFACES
        if path not in documented or method.lower() not in documented[path]
    ]
    assert not missing, f"Capabilities missing from the v1 API and its OpenAPI schema: {missing}"


def test_retired_lanes_have_not_come_back(client) -> None:
    documented = _documented(client)
    resurrected = [path for path in RETIRED_SURFACES if path in documented]
    assert not resurrected, f"Retired endpoints are reachable again: {resurrected}"


# --- auth and CSRF on the new endpoints ----------------------------------------------


def test_maintenance_state_needs_a_session(client) -> None:
    assert client.get(f"{API}/processing/maintenance").status_code == 401


def test_maintenance_state_lists_every_promoted_family(admin) -> None:
    body = admin.get(f"{API}/processing/maintenance").json()

    families = {row["family"] for row in body["families"]}
    assert families == {"work_temp_stale_sweep", "failure_cleanup"}
    cleanup = next(row for row in body["families"] if row["family"] == "failure_cleanup")
    assert "deletes the original" in cleanup["description"]


def test_triggering_maintenance_without_a_csrf_token_is_refused(admin) -> None:
    response = admin.post(
        f"{API}/processing/maintenance/run", json={"family": "work_temp_stale_sweep", "media_scope": "movie"}
    )
    assert response.status_code == 422


def test_triggering_maintenance_queues_a_run(admin) -> None:
    response = admin.post_csrf(
        f"{API}/processing/maintenance/run", {"family": "work_temp_stale_sweep", "media_scope": "movie"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["queued"] is True


def test_an_unknown_family_is_refused(admin) -> None:
    response = admin.post_csrf(
        f"{API}/processing/maintenance/run", {"family": "something_invented", "media_scope": "movie"}
    )
    assert response.status_code == 422


def test_the_hardware_report_needs_a_session_and_then_answers(client) -> None:
    assert client.get(f"{API}/processing/hardware").status_code == 401

    client.ensure_admin()
    body = client.get(f"{API}/processing/hardware").json()

    assert "available_methods" in body
    assert "selectable_vendors" in body
    assert body["detail"]


def test_the_metadata_provider_never_returns_the_key(admin) -> None:
    """The key is write-only. A screen can say one is configured without being able to leak it."""

    assert admin.get(f"{API}/processing/metadata-provider").status_code == 200

    saved = admin.put_csrf(
        f"{API}/processing/metadata-provider",
        {"provider": "tmdb", "base_url": "https://metadata.example.workers.dev", "api_key": "a-secret-key"},
    )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["key_configured"] is True
    assert "a-secret-key" not in saved.text
    assert body["base_url"] == "https://metadata.example.workers.dev"
    assert "a-secret-key" not in admin.get(f"{API}/processing/metadata-provider").text


def test_the_metadata_provider_key_survives_a_save_that_omits_it(admin) -> None:
    """Saving the address must not require re-typing a secret the screen cannot show back."""

    admin.put_csrf(
        f"{API}/processing/metadata-provider",
        {"provider": "tmdb", "base_url": "https://one.example.com", "api_key": "k"},
    )

    body = admin.put_csrf(
        f"{API}/processing/metadata-provider",
        {"provider": "tmdb", "base_url": "https://two.example.com"},
    ).json()

    assert body["key_configured"] is True
    assert body["base_url"] == "https://two.example.com"
