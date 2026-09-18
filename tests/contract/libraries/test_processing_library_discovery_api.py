"""Media-manager library discovery, import, drift and unlink (#554).

Port of the HTTP-relevant assertions in ``apps/backend/tests/test_processing_library_discovery.py``,
against a real (fake) Deluno manager rather than a monkeypatched ``_descriptors_for``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.contract.media_managers._helpers import create_connection
from tests.contract.libraries import _helpers as h
from tests.contract.support.client import API, WeirClient

LIBRARIES = f"{API}/processing/libraries"


def _reset(c: WeirClient) -> None:
    """Leave only the seeded libraries and no media manager connections, so each test starts the same way.

    A library this file imported is always enabled with a real watched folder — on either backend, the
    server's own periodic scan can queue a scan job for it before this runs, and Processing refuses to
    delete a library with a job queued or running. Deleting it is still attempted (most of the time
    nothing has been queued yet), but best-effort: every manifest name used below is unique to its own
    test, so a library this could not remove never contaminates a later test's assertions.
    """

    for row in c.get(LIBRARIES).json():
        if row["name"] not in ("Movies", "TV"):
            h.delete_with_body_csrf(c, f"{LIBRARIES}/{row['id']}")
    for row in c.get(f"{API}/media-managers/connections").json():
        r = c.request("DELETE", f"{API}/media-managers/connections/{row['id']}", json={"csrf_token": c.csrf()})
        assert r.status_code == 204, r.text


@pytest.fixture
def operator(admin: WeirClient) -> WeirClient:
    _reset(admin)
    return admin


def _connect(operator: WeirClient, fake_managers, libraries: list[dict[str, Any]]) -> tuple[Any, int]:
    fake = fake_managers("deluno", libraries=libraries)
    created = create_connection(operator, base_url=fake.base_url, api_key=fake.api_key)
    assert created.status_code == 201, created.text
    return fake, created.json()["id"]


def _discover(operator: WeirClient, connection_id: int):
    return operator.get(f"{LIBRARIES}/discover/{connection_id}")


def _drift(operator: WeirClient, connection_id: int):
    return operator.get(f"{LIBRARIES}/discover/{connection_id}/drift")


def _import(operator: WeirClient, connection_id: int, keys: list[str]):
    return operator.post_csrf(f"{LIBRARIES}/discover/{connection_id}/import", {"keys": keys})


def _library(operator: WeirClient, library_id: int) -> dict[str, Any]:
    r = operator.get(f"{LIBRARIES}/{library_id}")
    assert r.status_code == 200, r.text
    return r.json()


# --- GET .../discover/{connection_id} ------------------------------------------------------------


def test_discover_requires_authentication(client: WeirClient) -> None:
    assert _discover(client, 1).status_code == 401


def test_discover_lists_libraries_and_marks_what_is_already_imported(
    operator: WeirClient, fake_managers, tmp_path: Path
) -> None:
    movies_root = tmp_path / "movies"
    tv_root = tmp_path / "tv"
    movies_root.mkdir()
    tv_root.mkdir()
    fake, connection_id = _connect(
        operator,
        fake_managers,
        [
            {"id": "7", "name": "Films-Disc", "mediaType": "movies", "rootPath": str(movies_root)},
            {"id": "8", "name": "Shows-Disc", "mediaType": "tv", "rootPath": str(tv_root)},
        ],
    )
    imported = _import(operator, connection_id, ["7"])
    assert imported.status_code == 201, imported.text

    response = _discover(operator, connection_id)

    assert response.status_code == 200, response.text
    found = {row["key"]: row for row in response.json()}
    assert found["7"]["already_imported"] is True
    assert found["8"]["already_imported"] is False
    assert found["8"]["media_type"] == "tv"


def test_discover_shows_the_output_root_before_the_import(operator: WeirClient, fake_managers, tmp_path: Path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    _fake, connection_id = _connect(
        operator,
        fake_managers,
        [
            {
                "id": "7",
                "name": "Movies",
                "mediaType": "movies",
                "rootPath": str(root),
                "importWorkflow": "refine-before-import",
                "processorOutputPath": str(root),
            }
        ],
    )

    row = _discover(operator, connection_id).json()[0]

    assert row["processes_before_import"] is True
    assert row["output_path"] == str(root)
    assert row["output_path_problem"] is None


def test_discover_for_an_unknown_connection_is_404(operator: WeirClient) -> None:
    response = _discover(operator, 999999)
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "That media manager connection does not exist."


def test_discover_for_a_connection_with_no_saved_key_is_502(operator: WeirClient, fake_managers) -> None:
    fake = fake_managers("deluno")
    created = create_connection(operator, base_url=fake.base_url, api_key="")
    assert created.status_code == 201, created.text

    response = _discover(operator, created.json()["id"])

    assert response.status_code == 502, response.text
    assert "address and API key" in response.json()["detail"]


# --- POST .../discover/{connection_id}/import ------------------------------------------------------


def test_import_creates_only_the_chosen_subset_and_adopts_the_visible_root(
    operator: WeirClient, fake_managers, tmp_path: Path
) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _fake, connection_id = _connect(
        operator,
        fake_managers,
        [
            {"id": "7", "name": "Films-Subset", "mediaType": "movies", "rootPath": str(root)},
            {"id": "8", "name": "Shows-Subset", "mediaType": "tv", "rootPath": str(root)},
            {"id": "9", "name": "Kids-Subset", "mediaType": "movies", "rootPath": str(root)},
        ],
    )

    response = _import(operator, connection_id, ["7", "9"])

    assert response.status_code == 201, response.text
    created = response.json()
    assert sorted(row["name"] for row in created) == ["Films-Subset", "Kids-Subset"]
    assert {row["discovered_library_key"] for row in created} == {"7", "9"}
    assert all(row["discovered_from_connection_id"] == connection_id for row in created)
    assert all(row["watched_folder"] == str(root) for row in created)


def test_a_root_weir_cannot_see_imports_without_a_watched_folder(operator: WeirClient, fake_managers) -> None:
    _fake, connection_id = _connect(
        operator,
        fake_managers,
        [{"id": "7", "name": "Films-NoRoot", "mediaType": "movies", "rootPath": "/srv/elsewhere"}],
    )

    created = _import(operator, connection_id, ["7"]).json()[0]

    assert created["watched_folder"] == ""
    assert created["discovered_library_key"] == "7"


def test_a_duplicate_name_is_disambiguated_rather_than_refused(
    operator: WeirClient, fake_managers, tmp_path: Path
) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    manual = operator.post_csrf(LIBRARIES, {"name": "Films", "media_type": "movie"})
    assert manual.status_code == 201, manual.text
    _fake, connection_id = _connect(
        operator, fake_managers, [{"id": "7", "name": "Films", "mediaType": "movies", "rootPath": str(root)}]
    )

    created = _import(operator, connection_id, ["7"]).json()[0]

    assert created["name"] == "Films (2)"


def test_importing_no_keys_is_a_422(operator: WeirClient, fake_managers) -> None:
    _fake, connection_id = _connect(operator, fake_managers, [])

    response = _import(operator, connection_id, [])

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "too_short"


def test_importing_an_unknown_key_is_a_400(operator: WeirClient, fake_managers, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _fake, connection_id = _connect(
        operator, fake_managers, [{"id": "7", "name": "Films-Unknown", "mediaType": "movies", "rootPath": str(root)}]
    )

    response = _import(operator, connection_id, ["missing"])

    assert response.status_code == 400, response.text
    assert "no longer reports a library with id missing" in response.json()["detail"]


def test_importing_a_refine_before_import_library_seeds_its_output_folder(
    operator: WeirClient, fake_managers, tmp_path: Path
) -> None:
    watched = tmp_path / "watched"
    output = tmp_path / "output"
    watched.mkdir()
    output.mkdir()
    _fake, connection_id = _connect(
        operator,
        fake_managers,
        [
            {
                "id": "7",
                "name": "Movies-Refine",
                "mediaType": "movies",
                "rootPath": str(watched),
                "importWorkflow": "refine-before-import",
                "processorOutputPath": str(output),
            }
        ],
    )

    created = _import(operator, connection_id, ["7"]).json()[0]

    assert created["watched_folder"] == str(watched)
    assert created["output_folder"] == str(output)


# --- GET .../discover/{connection_id}/drift --------------------------------------------------------


def test_drift_reports_a_moved_root_and_changes_nothing(operator: WeirClient, fake_managers, tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    new_root.mkdir()
    fake, connection_id = _connect(
        operator, fake_managers, [{"id": "7", "name": "Films-Moved", "mediaType": "movies", "rootPath": str(old_root)}]
    )
    library_id = _import(operator, connection_id, ["7"]).json()[0]["id"]
    fake.libraries[:] = [{"id": "7", "name": "Films-Moved", "mediaType": "movies", "rootPath": str(new_root)}]

    response = _drift(operator, connection_id)

    assert response.status_code == 200, response.text
    drift = response.json()
    (moved,) = [d for d in drift if d["kind"] == "root_moved"]
    assert moved["manager_value"] == str(new_root)
    assert moved["weir_value"] == str(old_root)
    # Nothing applied.
    assert _library(operator, library_id)["watched_folder"] == str(old_root)


def test_drift_reports_a_library_the_manager_no_longer_has(operator: WeirClient, fake_managers, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    fake, connection_id = _connect(
        operator, fake_managers, [{"id": "7", "name": "Gone", "mediaType": "movies", "rootPath": str(root)}]
    )
    library_id = _import(operator, connection_id, ["7"]).json()[0]["id"]
    fake.libraries[:] = []

    drift = _drift(operator, connection_id).json()

    assert [d["kind"] for d in drift] == ["library_removed"]
    assert drift[0]["library_id"] == library_id
    assert _library(operator, library_id)["watched_folder"] == str(root)


def test_drift_reports_a_library_that_appeared(operator: WeirClient, fake_managers, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _fake, connection_id = _connect(
        operator, fake_managers, [{"id": "9", "name": "New", "mediaType": "movies", "rootPath": str(root)}]
    )

    drift = _drift(operator, connection_id).json()

    assert [d["kind"] for d in drift] == ["library_added"]
    assert drift[0]["library_name"] == "New"
    assert all(row["name"] != "New" for row in operator.get(LIBRARIES).json())


def test_drift_is_quiet_when_nothing_has_changed(operator: WeirClient, fake_managers, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _fake, connection_id = _connect(
        operator, fake_managers, [{"id": "7", "name": "Films-Quiet", "mediaType": "movies", "rootPath": str(root)}]
    )
    _import(operator, connection_id, ["7"])

    assert _drift(operator, connection_id).json() == []


# --- POST .../libraries/{library_id}/unlink --------------------------------------------------------


def test_unlink_keeps_the_library_but_forgets_where_it_came_from(
    operator: WeirClient, fake_managers, tmp_path: Path
) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    _fake, connection_id = _connect(
        operator, fake_managers, [{"id": "7", "name": "Films-Unlink", "mediaType": "movies", "rootPath": str(root)}]
    )
    library_id = _import(operator, connection_id, ["7"]).json()[0]["id"]

    response = operator.post_csrf(f"{LIBRARIES}/{library_id}/unlink", {})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Films-Unlink"
    assert body["watched_folder"] == str(root)
    assert body["discovered_from_connection_id"] is None
    assert body["discovered_library_key"] is None
    assert _library(operator, library_id)["discovered_library_key"] is None


def test_unlink_of_an_unknown_library_is_404(operator: WeirClient) -> None:
    response = operator.post_csrf(f"{LIBRARIES}/999999/unlink", {})
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "That library does not exist."


# --- openapi ------------------------------------------------------------------------------------


def test_discovery_operations_are_in_the_generated_openapi_schema(client: WeirClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    for path in (
        "/api/v1/processing/libraries/discover/{connection_id}",
        "/api/v1/processing/libraries/discover/{connection_id}/drift",
        "/api/v1/processing/libraries/discover/{connection_id}/import",
        "/api/v1/processing/libraries/{library_id}/unlink",
    ):
        assert path in paths, path
