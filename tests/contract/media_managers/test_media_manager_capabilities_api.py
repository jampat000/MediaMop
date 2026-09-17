"""Contract port of apps/backend/tests/test_media_manager_capabilities_api.py."""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.media_managers._helpers import NO_WEBHOOK_SECRET, clear_connections, create_connection
from tests.contract.support.client import API, WeirClient


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return dict(NO_WEBHOOK_SECRET)


@pytest.fixture
def operator(admin: WeirClient) -> WeirClient:
    clear_connections(admin)
    return admin


def _create(client: WeirClient, **overrides: Any) -> dict[str, Any]:
    overrides.setdefault("name", "Main")
    response = create_connection(client, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


def test_capabilities_requires_an_operator(client: WeirClient) -> None:
    assert client.get(f"{API}/media-managers/capabilities").status_code == 401


def test_capabilities_reports_what_a_reachable_manager_manages(operator: WeirClient, fake_managers) -> None:
    # The original stubbed the manager port; here a fake Deluno answers its manifest.
    fake = fake_managers(
        "deluno",
        libraries=[
            {"id": "lib-movies", "name": "Movies", "mediaType": "movies", "path": "/media/movies"},
            {"id": "lib-tv", "name": "TV", "mediaType": "tv", "path": "/media/tv"},
        ],
    )
    created = _create(operator, base_url=fake.base_url, api_key=fake.api_key)

    rows = operator.get(f"{API}/media-managers/capabilities").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["connection_id"] == created["id"]
    assert row["label"] == "Deluno (Main)"
    assert row["media_scopes"] == ["movie", "tv"]
    assert row["reports_import_queue"] is True
    # The honest part: Deluno cannot clear a folder for deletion, and says so up front.
    assert row["reports_library_truth"] is False
    assert row["reachable"] is True
    assert row["library_roots"] == ["/media/movies", "/media/tv"]
    assert "Movies and TV episodes" in row["summary"]
    (manifest_request,) = fake.requests_to("GET", "/api/integrations/external/manifest")
    assert manifest_request.header("X-Api-Key") == fake.api_key


def test_capabilities_says_when_a_manager_did_not_answer(operator: WeirClient, fake_managers) -> None:
    fake = fake_managers("deluno")
    base_url = fake.base_url
    fake.stop()
    _create(operator, base_url=base_url)

    row = operator.get(f"{API}/media-managers/capabilities").json()[0]
    assert row["reachable"] is False
    assert row["detail"].startswith("Weir could not reach Deluno (Main)")
    # The static profile still stands, so the page can say what this manager is for.
    assert row["media_scopes"] == ["movie", "tv"]


def test_a_connection_with_no_saved_key_is_not_listed(operator: WeirClient) -> None:
    """Nothing can be asked of it, so claiming a capability for it would be a lie."""

    _create(operator, api_key="")
    assert operator.get(f"{API}/media-managers/capabilities").json() == []


def test_capabilities_is_in_the_generated_openapi_schema(client: WeirClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()
    path = schema["paths"]["/api/v1/media-managers/capabilities"]["get"]
    ref = path["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
    assert ref.endswith("MediaManagerCapabilityOut")
    properties = schema["components"]["schemas"]["MediaManagerCapabilityOut"]["properties"]
    assert {"label", "media_scopes", "reports_import_queue", "reports_library_truth"} <= set(properties)
