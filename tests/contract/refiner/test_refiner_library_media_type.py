"""Port of apps/backend/tests/test_refiner_library_media_type.py (the HTTP parts)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.contract.refiner import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

LIBRARIES = f"{API}/refiner/libraries"


def _create(c: WeirClient, **overrides: object):
    # Disabled so the server's periodic scan never queues work that would block the cleanup delete.
    body: dict[str, Any] = {
        "enabled": False,
        "name": "Films 4K",
        "media_type": "movie",
        "watched_folder": "/srv/films4k/in",
        "output_folder": "/srv/films4k/out",
    }
    body.update(overrides)
    return c.post_csrf(LIBRARIES, body)


@pytest.fixture
def operator(admin: WeirClient) -> WeirClient:
    for row in admin.get(LIBRARIES).json():
        if row["name"] not in ("Movies", "TV"):
            r = h.delete_with_body_csrf(admin, f"{LIBRARIES}/{row['id']}")
            assert r.status_code == 204, r.text
    return admin


def test_the_scope_shaped_routes_are_gone(operator) -> None:
    for path in (f"{API}/refiner/path-settings", f"{API}/refiner/remux-rules-settings"):
        assert operator.get(path).status_code == 404, path


def test_a_library_reports_its_media_type(operator) -> None:
    response = _create(operator)
    assert response.status_code == 201, response.text
    assert response.json()["media_type"] == "movie"
    assert "media_scope" not in response.json()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"output_folder": "/srv/films4k/in/done"}, "watched folder and output folder overlap"),
        ({"work_folder": "/srv/films4k/in"}, "watched folder and work folder overlap"),
        ({"output_folder": ""}, "Set an output folder"),
    ],
)
def test_a_library_whose_own_folders_overlap_is_refused(operator, overrides: dict[str, object], expected: str) -> None:
    response = _create(operator, **overrides)
    assert response.status_code == 400, response.text
    assert expected in response.json()["detail"]


def test_a_library_cannot_share_another_librarys_folders(operator) -> None:
    assert _create(operator).status_code == 201
    response = _create(
        operator, name="Films 1080p", watched_folder="/srv/films4k/in/1080p", output_folder="/srv/films1080/out"
    )
    assert response.status_code == 400, response.text
    assert "overlaps the watched folder of 'Films 4K'" in response.json()["detail"]


def test_a_second_film_library_is_normal(operator) -> None:
    first = _create(operator)
    second = _create(
        operator, name="Films 1080p", watched_folder="/srv/films1080/in", output_folder="/srv/films1080/out"
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    edited = operator.put_csrf(
        f"{LIBRARIES}/{second.json()['id']}",
        {
            "enabled": False,
            "name": "Films 1080p",
            "media_type": "movie",
            "watched_folder": "/srv/films1080/incoming",
            "output_folder": "/srv/films1080/out",
        },
    )
    assert edited.status_code == 200, edited.text


def test_a_hand_off_lands_in_the_library_whose_folder_holds_the_file(server_factory, client_factory) -> None:
    """Resolving by type alone always picked the first film library, whatever folder the file was in."""

    # A fresh install: no media manager connection (so no webhook secret) and no queued jobs.
    sut = server_factory()
    c = h.signed_in_admin(sut, client_factory)
    assert _create(c, enabled=True).status_code == 201  # Films 4K: /srv/films4k/in
    second = _create(
        c, enabled=True, name="Films 1080p", watched_folder="/srv/films1080/in", output_folder="/srv/films1080/out"
    )
    assert second.status_code == 201, second.text
    response = c.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "h-1080",
            "mediaType": "movies",
            "sourcePath": "/srv/films1080/in/Heat.1995/heat.mkv",
        },
    )
    assert response.status_code == 200, response.text

    with seed.stopped(sut, restart=False) as conn:
        jobs = seed.rows(conn, "SELECT payload_json FROM refiner_jobs WHERE dedupe_key LIKE ?", ("%handoff:h-1080",))
    assert len(jobs) == 1
    payload = json.loads(jobs[0]["payload_json"] or "{}")
    assert payload["library_id"] == second.json()["id"]
    assert payload["relative_media_path"] == "Heat.1995/heat.mkv"
    assert payload["media_scope"] == "movie"
