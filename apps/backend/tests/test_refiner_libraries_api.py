"""HTTP: Refiner libraries and rule sets.

Adding a library is a POST, not a migration (ADR-0014). The two refusals are the part
worth testing hardest — both exist because the alternative is silent damage.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from tests.integration_helpers import auth_post, auth_put, trusted_browser_origin_headers
from tests.integration_helpers import csrf as fetch_csrf


def _login_admin(client: TestClient) -> None:
    token = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": token},
    )
    assert r.status_code == 200, r.text


def _session_factory():
    from mediamop.core.config import MediaMopSettings
    from mediamop.core.db import create_db_engine, create_session_factory

    return create_session_factory(create_db_engine(MediaMopSettings.load()))


@pytest.fixture
def operator(client_with_admin: TestClient) -> TestClient:
    _login_admin(client_with_admin)
    fac = _session_factory()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()
    # Leave only the seeded libraries so ids are predictable.
    for row in client_with_admin.get("/api/v1/refiner/libraries").json():
        if row["name"] not in ("Movies", "TV"):
            client_with_admin.request(
                "DELETE",
                f"/api/v1/refiner/libraries/{row['id']}",
                json={"csrf_token": fetch_csrf(client_with_admin)},
                headers=trusted_browser_origin_headers(),
            )
    return client_with_admin


def _create(client: TestClient, **overrides: Any):
    body = {
        "csrf_token": fetch_csrf(client),
        "name": "Movies 4K",
        "media_scope": "movie",
        "watched_folder": "/srv/4k/in",
        "output_folder": "/srv/4k/out",
        "media_extensions_csv": ".mkv,.mp4",
    }
    body.update(overrides)
    return auth_post(client, "/api/v1/refiner/libraries", json=body)


def test_libraries_require_authentication(client_with_admin: TestClient) -> None:
    assert client_with_admin.get("/api/v1/refiner/libraries").status_code == 401


def test_the_seeded_libraries_are_listed(operator: TestClient) -> None:
    rows = operator.get("/api/v1/refiner/libraries").json()
    by_name = {r["name"]: r for r in rows}
    assert {"Movies", "TV"} <= set(by_name)
    assert by_name["Movies"]["media_scope"] == "movie"
    assert by_name["TV"]["media_scope"] == "tv"
    # The former module constants arrive as this library's saved data.
    assert ".mkv" in by_name["Movies"]["media_extensions_csv"]


def test_a_third_library_can_be_added_and_edited(operator: TestClient) -> None:
    created = _create(operator)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["name"] == "Movies 4K"
    assert row["media_scope"] == "movie"

    updated = auth_put(
        operator,
        f"/api/v1/refiner/libraries/{row['id']}",
        json={
            "csrf_token": fetch_csrf(operator),
            "name": "Movies 4K",
            "media_scope": "movie",
            "watched_folder": "/srv/4k/in2",
            "output_folder": "/srv/4k/out",
            "min_file_size_mb": 900,
            "top_level_only": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["watched_folder"] == "/srv/4k/in2"
    assert updated.json()["min_file_size_mb"] == 900
    assert updated.json()["top_level_only"] is True


def test_a_duplicate_name_is_refused(operator: TestClient) -> None:
    assert _create(operator).status_code == 201
    again = _create(operator)
    assert again.status_code == 400
    assert "already exists" in again.json()["detail"]


def test_an_unknown_media_scope_is_refused(operator: TestClient) -> None:
    r = _create(operator, media_scope="anime")
    assert r.status_code == 422


def test_linking_a_manager_connection_that_does_not_exist_is_refused(operator: TestClient) -> None:
    r = _create(operator, manager_connection_ids=[4242])
    assert r.status_code == 400
    assert "media manager connection" in r.json()["detail"].lower()


def test_a_library_can_be_deleted_when_nothing_is_queued(operator: TestClient) -> None:
    row = _create(operator).json()
    r = operator.request(
        "DELETE",
        f"/api/v1/refiner/libraries/{row['id']}",
        json={"csrf_token": fetch_csrf(operator)},
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 204
    assert all(x["id"] != row["id"] for x in operator.get("/api/v1/refiner/libraries").json())


def test_deleting_a_library_with_queued_work_is_refused(operator: TestClient) -> None:
    """Those jobs resolve their folders from this library, and Refiner deletes folders."""

    row = _create(operator).json()
    fac = _session_factory()
    with fac() as db:
        refiner_enqueue_or_get_job(
            db,
            dedupe_key="refiner.file.remux_pass.v1:library-guard",
            job_kind="refiner.file.remux_pass.v1",
            payload_json=json.dumps({"relative_media_path": "a.mkv", "library_id": row["id"]}),
        )
        db.commit()

    r = operator.request(
        "DELETE",
        f"/api/v1/refiner/libraries/{row['id']}",
        json={"csrf_token": fetch_csrf(operator)},
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 409
    assert "queued or running" in r.json()["detail"]
    assert any(x["id"] == row["id"] for x in operator.get("/api/v1/refiner/libraries").json())


def test_the_active_job_count_is_reported_so_the_screen_can_explain_the_refusal(
    operator: TestClient,
) -> None:
    row = _create(operator).json()
    assert row["active_job_count"] == 0

    fac = _session_factory()
    with fac() as db:
        refiner_enqueue_or_get_job(
            db,
            dedupe_key="refiner.file.remux_pass.v1:count",
            job_kind="refiner.file.remux_pass.v1",
            payload_json=json.dumps({"relative_media_path": "a.mkv", "library_id": row["id"]}),
        )
        db.commit()

    again = operator.get(f"/api/v1/refiner/libraries/{row['id']}").json()
    assert again["active_job_count"] == 1


def test_a_completed_job_does_not_block_deletion(operator: TestClient) -> None:
    row = _create(operator).json()
    fac = _session_factory()
    with fac() as db:
        job = refiner_enqueue_or_get_job(
            db,
            dedupe_key="refiner.file.remux_pass.v1:done",
            job_kind="refiner.file.remux_pass.v1",
            payload_json=json.dumps({"relative_media_path": "a.mkv", "library_id": row["id"]}),
        )
        job.status = RefinerJobStatus.COMPLETED.value
        db.commit()

    r = operator.request(
        "DELETE",
        f"/api/v1/refiner/libraries/{row['id']}",
        json={"csrf_token": fetch_csrf(operator)},
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 204


def test_reordering_decides_which_library_a_scope_only_payload_resolves_to(operator: TestClient) -> None:
    created = _create(operator).json()
    rows = operator.get("/api/v1/refiner/libraries").json()
    ids = [r["id"] for r in rows]
    reordered = [created["id"], *[i for i in ids if i != created["id"]]]

    r = auth_post(
        operator,
        "/api/v1/refiner/libraries/reorder",
        json={"csrf_token": fetch_csrf(operator), "library_ids_in_order": reordered},
    )
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()] == reordered


def test_reordering_must_list_every_library(operator: TestClient) -> None:
    _create(operator)
    r = auth_post(
        operator,
        "/api/v1/refiner/libraries/reorder",
        json={"csrf_token": fetch_csrf(operator), "library_ids_in_order": [1]},
    )
    assert r.status_code == 400


def test_a_rule_set_in_use_cannot_be_deleted(operator: TestClient) -> None:
    """ADR-0014 §3 makes rule sets shared on purpose; a cascade would strip handling."""

    made = auth_post(
        operator,
        "/api/v1/refiner/rule-sets",
        json={"csrf_token": fetch_csrf(operator), "name": "Anime", "primary_audio_lang": "jpn"},
    )
    assert made.status_code == 201, made.text
    rule_set = made.json()

    _create(operator, name="Anime Movies", rule_set_id=rule_set["id"])

    r = operator.request(
        "DELETE",
        f"/api/v1/refiner/rule-sets/{rule_set['id']}",
        json={"csrf_token": fetch_csrf(operator)},
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 409
    assert "still used by" in r.json()["detail"]

    listed = {x["id"]: x for x in operator.get("/api/v1/refiner/rule-sets").json()}
    assert listed[rule_set["id"]]["used_by_library_count"] == 1


def test_libraries_and_rule_sets_reach_the_generated_openapi_schema() -> None:
    from mediamop.api.factory import create_app

    schema = create_app().openapi()
    for path in (
        "/api/v1/refiner/libraries",
        "/api/v1/refiner/libraries/{library_id}",
        "/api/v1/refiner/libraries/reorder",
        "/api/v1/refiner/rule-sets",
    ):
        assert path in schema["paths"], path
    props = schema["components"]["schemas"]["RefinerLibraryOut"]["properties"]
    assert {"media_extensions_csv", "manager_connection_ids", "active_job_count"} <= set(props)
