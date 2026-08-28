"""HTTP: what each connected media manager can be asked (``/api/v1/media-managers/capabilities``).

Issue #346 keeps the epic honest: a capability Refiner relies on has to be visible in the
v1 API and the generated schema, not just in the code. This is where an operator finds
out that a manager will — or will not — give MediaMop an upstream safety check.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from mediamop.platform.media_managers.manager_port import (
    ManagerConnection,
    ManagerDescription,
    ManagerLibraryTruth,
    ManagerQueueSignal,
)
from tests.integration_helpers import auth_post, trusted_browser_origin_headers
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
    _login_admin(client_with_admin)
    for row in client_with_admin.get("/api/v1/media-managers/connections").json():
        client_with_admin.request(
            "DELETE",
            f"/api/v1/media-managers/connections/{row['id']}",
            json={"csrf_token": fetch_csrf(client_with_admin)},
            headers=trusted_browser_origin_headers(),
        )
    return client_with_admin


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "csrf_token": fetch_csrf(client),
        "kind": "deluno",
        "name": "Main",
        "base_url": "http://10.1.1.142:5099",
        "api_key": "deluno_secret_key",
    }
    body.update(overrides)
    response = auth_post(client, "/api/v1/media-managers/connections", json=body)
    assert response.status_code == 201, response.text
    return response.json()


class _StubPort:
    def __init__(self, *, status: str, detail: str | None = None) -> None:
        self._status = status
        self._detail = detail

    def capabilities(self):
        from mediamop.platform.media_managers.manager_dialects import capabilities_for_kind

        caps = capabilities_for_kind("deluno")
        assert caps is not None
        return caps

    def describe(self, connection: ManagerConnection) -> ManagerDescription:
        return ManagerDescription(
            connection=connection,
            status=self._status,
            capabilities=self.capabilities(),
            library_roots=("/media/movies", "/media/tv") if self._status == "reported" else (),
            detail=self._detail,
        )

    def queue_rows(self, connection: ManagerConnection) -> ManagerQueueSignal:
        return ManagerQueueSignal(connection=connection, status="reported")

    def library_truth(self, connection: ManagerConnection, *, media_scope) -> ManagerLibraryTruth:
        return ManagerLibraryTruth(connection=connection, status="no_signal")


def test_capabilities_requires_an_operator(client_with_admin: TestClient) -> None:
    assert client_with_admin.get("/api/v1/media-managers/capabilities").status_code == 401


def test_capabilities_reports_what_a_reachable_manager_manages(
    operator: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _create(operator)
    monkeypatch.setattr(
        "mediamop.platform.media_managers.manager_binding.port_for_kind",
        lambda _kind: _StubPort(status="reported"),
    )
    rows = operator.get("/api/v1/media-managers/capabilities").json()
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


def test_capabilities_says_when_a_manager_did_not_answer(
    operator: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create(operator)
    monkeypatch.setattr(
        "mediamop.platform.media_managers.manager_binding.port_for_kind",
        lambda _kind: _StubPort(status="unreachable", detail="MediaMop could not reach Deluno (Main)."),
    )
    row = operator.get("/api/v1/media-managers/capabilities").json()[0]
    assert row["reachable"] is False
    assert row["detail"] == "MediaMop could not reach Deluno (Main)."
    # The static profile still stands, so the page can say what this manager is for.
    assert row["media_scopes"] == ["movie", "tv"]


def test_a_connection_with_no_saved_key_is_not_listed(operator: TestClient) -> None:
    """Nothing can be asked of it, so claiming a capability for it would be a lie."""

    _create(operator, api_key="")
    assert operator.get("/api/v1/media-managers/capabilities").json() == []


def test_capabilities_is_in_the_generated_openapi_schema() -> None:
    from mediamop.api.factory import create_app

    schema = create_app().openapi()
    path = schema["paths"]["/api/v1/media-managers/capabilities"]["get"]
    ref = path["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
    assert ref.endswith("MediaManagerCapabilityOut")
    properties = schema["components"]["schemas"]["MediaManagerCapabilityOut"]["properties"]
    assert {"label", "media_scopes", "reports_import_queue", "reports_library_truth"} <= set(properties)
