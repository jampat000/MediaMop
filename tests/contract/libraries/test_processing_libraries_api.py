"""Port of the retired Python backend's tests/test_libraries_api.py."""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

LIBRARIES = f"{API}/processing/libraries"
RULE_SETS = f"{API}/processing/rule-sets"


def _reset(c: WeirClient) -> None:
    """Leave only the seeded libraries (and no rule sets) so each test starts the same way."""

    for row in c.get(LIBRARIES).json():
        if row["name"] not in ("Movies", "TV"):
            r = h.delete_with_body_csrf(c, f"{LIBRARIES}/{row['id']}")
            assert r.status_code == 204, r.text
    for row in c.get(RULE_SETS).json():
        if row["used_by_library_count"] == 0:
            h.delete_with_body_csrf(c, f"{RULE_SETS}/{row['id']}")


@pytest.fixture
def operator(admin: WeirClient) -> WeirClient:
    _reset(admin)
    return admin


def _create(c: WeirClient, **overrides: Any):
    # Disabled: the server's own periodic scan (which no env var switches off) queues a scan
    # job for every enabled library with a watched folder, and that job counts as queued work.
    # The originals never started the scheduler; nothing asserted here depends on ``enabled``.
    body: dict[str, Any] = {
        "enabled": False,
        "name": "Movies 4K",
        "media_type": "movie",
        "watched_folder": "/srv/4k/in",
        "output_folder": "/srv/4k/out",
        "media_extensions_csv": ".mkv,.mp4",
    }
    body.update(overrides)
    return c.post_csrf(LIBRARIES, body)


def test_libraries_require_authentication(client) -> None:
    assert client.get(LIBRARIES).status_code == 401


def test_the_seeded_libraries_are_listed(operator) -> None:
    rows = operator.get(LIBRARIES).json()
    by_name = {r["name"]: r for r in rows}
    assert {"Movies", "TV"} <= set(by_name)
    assert by_name["Movies"]["media_type"] == "movie"
    assert by_name["TV"]["media_type"] == "tv"
    # The former module constants arrive as this library's saved data.
    assert ".mkv" in by_name["Movies"]["media_extensions_csv"]


def test_a_third_library_can_be_added_and_edited(operator) -> None:
    created = _create(operator)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["name"] == "Movies 4K"
    assert row["media_type"] == "movie"

    updated = operator.put_csrf(
        f"{LIBRARIES}/{row['id']}",
        {
            "enabled": False,
            "name": "Movies 4K",
            "media_type": "movie",
            "watched_folder": "/srv/4k/in2",
            "output_folder": "/srv/4k/out",
            "min_file_size_mb": 900,
            "created_after": "2026-01-01T00:00:00Z",
            "created_before": "2027-01-01T00:00:00Z",
            "modified_after": "2026-02-01T00:00:00Z",
            "modified_before": "2026-12-01T00:00:00Z",
            "top_level_only": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["watched_folder"] == "/srv/4k/in2"
    assert updated.json()["min_file_size_mb"] == 900
    assert updated.json()["created_after"].startswith("2026-01-01T00:00:00")
    assert updated.json()["created_before"].startswith("2027-01-01T00:00:00")
    assert updated.json()["modified_after"].startswith("2026-02-01T00:00:00")
    assert updated.json()["modified_before"].startswith("2026-12-01T00:00:00")
    assert updated.json()["top_level_only"] is True
    fetched = operator.get(f"{LIBRARIES}/{row['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["watched_folder"] == "/srv/4k/in2"


def test_detection_windows_must_be_ordered_and_timezone_aware(operator) -> None:
    reversed_window = _create(
        operator,
        created_after="2027-01-01T00:00:00Z",
        created_before="2026-01-01T00:00:00Z",
    )
    assert reversed_window.status_code == 422
    assert "Created after must be earlier" in reversed_window.text

    timezone_missing = _create(operator, modified_after="2026-01-01T00:00:00")
    assert timezone_missing.status_code == 422
    assert "must include a timezone" in timezone_missing.text


def test_a_duplicate_name_is_refused(operator) -> None:
    assert _create(operator).status_code == 201
    again = _create(operator)
    assert again.status_code == 400
    assert "already exists" in again.json()["detail"]


def test_an_unknown_media_type_is_refused(operator) -> None:
    r = _create(operator, media_type="anime")
    assert r.status_code == 422


def test_linking_a_manager_connection_that_does_not_exist_is_refused(operator) -> None:
    r = _create(operator, manager_connection_ids=[4242])
    assert r.status_code == 400
    assert "media manager connection" in r.json()["detail"].lower()


def test_a_library_can_be_deleted_when_nothing_is_queued(operator) -> None:
    row = _create(operator).json()
    r = h.delete_with_body_csrf(operator, f"{LIBRARIES}/{row['id']}")
    assert r.status_code == 204
    assert all(x["id"] != row["id"] for x in operator.get(LIBRARIES).json())


def _fresh_operator(server_factory, client_factory) -> tuple[Any, WeirClient]:
    sut = server_factory()
    return sut, h.signed_in_admin(sut, client_factory)


def test_deleting_a_library_with_queued_work_is_refused(server_factory, client_factory) -> None:
    """Those jobs resolve their folders from this library, and Processing deletes folders."""

    sut, c = _fresh_operator(server_factory, client_factory)
    row = _create(c).json()
    with seed.stopped(sut) as conn:
        h.insert_job(
            conn,
            dedupe_key="processing.file.remux_pass.v1:library-guard",
            payload={"relative_media_path": "a.mkv", "library_id": row["id"]},
        )

    c = h.signed_in_admin(sut, client_factory)
    r = h.delete_with_body_csrf(c, f"{LIBRARIES}/{row['id']}")
    assert r.status_code == 409
    assert "queued or running" in r.json()["detail"]
    assert any(x["id"] == row["id"] for x in c.get(LIBRARIES).json())


def test_the_active_job_count_is_reported_so_the_screen_can_explain_the_refusal(server_factory, client_factory) -> None:
    sut, c = _fresh_operator(server_factory, client_factory)
    row = _create(c).json()
    assert row["active_job_count"] == 0

    with seed.stopped(sut) as conn:
        h.insert_job(
            conn,
            dedupe_key="processing.file.remux_pass.v1:count",
            payload={"relative_media_path": "a.mkv", "library_id": row["id"]},
        )

    c = h.signed_in_admin(sut, client_factory)
    again = c.get(f"{LIBRARIES}/{row['id']}").json()
    assert again["active_job_count"] == 1


def test_a_completed_job_does_not_block_deletion(server_factory, client_factory) -> None:
    sut, c = _fresh_operator(server_factory, client_factory)
    row = _create(c).json()
    with seed.stopped(sut) as conn:
        h.insert_job(
            conn,
            dedupe_key="processing.file.remux_pass.v1:done",
            status="completed",
            payload={"relative_media_path": "a.mkv", "library_id": row["id"]},
        )

    c = h.signed_in_admin(sut, client_factory)
    r = h.delete_with_body_csrf(c, f"{LIBRARIES}/{row['id']}")
    assert r.status_code == 204


def test_reordering_decides_which_library_a_scope_only_payload_resolves_to(operator) -> None:
    created = _create(operator).json()
    rows = operator.get(LIBRARIES).json()
    ids = [r["id"] for r in rows]
    reordered = [created["id"], *[i for i in ids if i != created["id"]]]

    r = operator.post_csrf(f"{LIBRARIES}/reorder", {"library_ids_in_order": reordered})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()] == reordered
    assert [x["id"] for x in operator.get(LIBRARIES).json()] == reordered

    # Put the seeded order back for the rest of the module.
    restored = [i for i in ids if i != created["id"]] + [created["id"]]
    assert operator.post_csrf(f"{LIBRARIES}/reorder", {"library_ids_in_order": restored}).status_code == 200


def test_reordering_must_list_every_library(operator) -> None:
    _create(operator)
    r = operator.post_csrf(f"{LIBRARIES}/reorder", {"library_ids_in_order": [1]})
    assert r.status_code == 400


def test_a_rule_set_in_use_cannot_be_deleted(operator) -> None:
    """ADR-0014 §3 makes rule sets shared on purpose; a cascade would strip handling."""

    made = operator.post_csrf(RULE_SETS, {"name": "Anime", "primary_audio_lang": "jpn"})
    assert made.status_code == 201, made.text
    rule_set = made.json()

    assert _create(operator, name="Anime Movies", rule_set_id=rule_set["id"]).status_code == 201

    r = h.delete_with_body_csrf(operator, f"{RULE_SETS}/{rule_set['id']}")
    assert r.status_code == 409
    assert "still used by" in r.json()["detail"]

    listed = {x["id"]: x for x in operator.get(RULE_SETS).json()}
    assert listed[rule_set["id"]]["used_by_library_count"] == 1


def test_libraries_and_rule_sets_reach_the_generated_openapi_schema(client) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200, r.text
    schema = r.json()
    for path in (
        "/api/v1/processing/libraries",
        "/api/v1/processing/libraries/{library_id}",
        "/api/v1/processing/libraries/reorder",
        "/api/v1/processing/rule-sets",
    ):
        assert path in schema["paths"], path
    props = schema["components"]["schemas"]["ProcessingLibraryOut"]["properties"]
    assert {"media_extensions_csv", "manager_connection_ids", "active_job_count"} <= set(props)


# --- the reject failure policy (#471) ------------------------------------------------------------


def test_reject_cannot_be_saved_for_a_library_no_manager_can_take_one_for(operator) -> None:
    """Reject deletes downloads, so it is refused rather than saved and silently never used."""

    response = _create(operator, failure_policy="reject")
    assert response.status_code == 400, response.text
    assert "cannot use Reject yet" in response.json()["detail"]
    assert "Link a media manager" in response.json()["detail"]
    names = {row["name"] for row in operator.get(LIBRARIES).json()}
    assert "Movies 4K" not in names


def test_reject_support_explains_itself(operator) -> None:
    response = operator.get(f"{API}/processing/reject-support")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False
    assert "Link a media manager" in body["reason"]


def test_reject_support_needs_a_session(client) -> None:
    assert client.get(f"{API}/processing/reject-support").status_code == 401
