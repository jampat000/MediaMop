"""HTTP: the one media-manager intake webhook (no operator auth, optional shared secret).

Covers the dialects that replaced the per-vendor Subber routes, plus the hand-off path
that Refiner serves for a manager which wants a file cleaned before it imports it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import select
from starlette.testclient import TestClient

from alembic import command
from mediamop.api.factory import create_app
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.subber.subber_jobs_model import SubberJob
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)

WATCHED_MOVIES = "/srv/handoff/movies"
WATCHED_TV = "/srv/handoff/tv"


@pytest.fixture(autouse=True)
def _isolated_intake_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_intake_webhook")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


def _session_factory(client: TestClient):
    from mediamop.core.db import create_db_engine, create_session_factory

    return create_session_factory(create_db_engine(client.app.state.settings))


def _set_watched_folders(client: TestClient) -> None:
    from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow

    with _session_factory(client)() as db:
        row = db.get(RefinerPathSettingsRow, 1)
        assert row is not None
        row.refiner_watched_folder = WATCHED_MOVIES
        row.refiner_tv_watched_folder = WATCHED_TV
        db.commit()


def _subber_jobs(client: TestClient) -> list[SubberJob]:
    with _session_factory(client)() as db:
        return list(db.scalars(select(SubberJob)))


def _refiner_jobs(client: TestClient) -> list[RefinerJob]:
    with _session_factory(client)() as db:
        return list(db.scalars(select(RefinerJob).where(RefinerJob.job_kind == "refiner.file.remux_pass.v1")))


# --- the dialects that replaced /subber/webhook/{radarr,sonarr} ---------------


def test_sonarr_non_download_is_ignored(client: TestClient) -> None:
    r = client.post("/api/v1/intake/webhook/sonarr", json={"eventType": "Grab", "episodes": [{"id": 1}]})
    assert r.status_code == 200
    assert r.json() == {"status": "ignored", "source": "sonarr"}


def test_sonarr_download_enqueues_a_tv_subtitle_import(client: TestClient) -> None:
    r = client.post(
        "/api/v1/intake/webhook/sonarr",
        json={
            "eventType": "Download",
            "series": {"title": "Test Show"},
            "episodes": [{"id": 9, "seasonNumber": 1, "episodeNumber": 2, "title": "Hello"}],
            "episodeFile": {"path": "/media/t/x.mkv"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["event"] == "imported"
    assert body["media_scope"] == "tv"

    jobs = _subber_jobs(client)
    assert len(jobs) == 1
    assert "webhook_import.tv" in jobs[0].job_kind


def test_radarr_non_download_is_ignored(client: TestClient) -> None:
    r = client.post("/api/v1/intake/webhook/radarr", json={"eventType": "Grab", "movie": {"id": 1}})
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_radarr_download_enqueues_a_movie_subtitle_import(client: TestClient) -> None:
    r = client.post(
        "/api/v1/intake/webhook/radarr",
        json={
            "eventType": "Download",
            "movie": {"id": 3, "title": "Film", "year": 2010},
            "movieFile": {"path": "/media/m/f.mkv"},
        },
    )
    assert r.status_code == 200
    assert r.json()["media_scope"] == "movie"

    jobs = _subber_jobs(client)
    assert len(jobs) == 1
    assert "webhook_import.movies" in jobs[0].job_kind


# --- the hand-off path, which is what a manager like Deluno needs -------------


def test_deluno_handoff_enqueues_a_refiner_pass_with_a_relative_path(client: TestClient) -> None:
    _set_watched_folders(client)
    r = client.post(
        "/api/v1/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-1",
            "libraryId": "lib-1",
            "mediaType": "movies",
            "sourcePath": f"{WATCHED_MOVIES}/Blade.Runner.2049/film.mkv",
            "releaseName": "Blade.Runner.2049",
            "callbackPath": "/api/integrations/processors/events",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["event"] == "handoff"
    assert body["enqueued"] == "refiner.file.remux_pass.v1"

    jobs = _refiner_jobs(client)
    assert len(jobs) == 1
    import json

    payload = json.loads(jobs[0].payload_json)
    assert payload["relative_media_path"] == "Blade.Runner.2049/film.mkv"
    assert payload["media_scope"] == "movie"
    assert payload["origin"]["handoff_id"] == "handoff-1"
    assert payload["origin"]["callback_path"] == "/api/integrations/processors/events"


def test_repeated_handoff_id_does_not_remux_the_file_twice(client: TestClient) -> None:
    _set_watched_folders(client)
    body = {
        "eventType": "deluno.processor-handoff",
        "handoffId": "handoff-same",
        "mediaType": "movies",
        "sourcePath": f"{WATCHED_MOVIES}/Repeat/film.mkv",
    }
    assert client.post("/api/v1/intake/webhook/deluno", json=body).status_code == 200
    assert client.post("/api/v1/intake/webhook/deluno", json=body).status_code == 200
    assert len(_refiner_jobs(client)) == 1


def test_handoff_outside_the_watched_folder_is_refused_with_a_plain_reason(client: TestClient) -> None:
    _set_watched_folders(client)
    r = client.post(
        "/api/v1/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-2",
            "mediaType": "movies",
            "sourcePath": "/somewhere/else/film.mkv",
        },
    )
    assert r.status_code == 400
    assert "not inside Refiner's watched folder" in r.json()["detail"]
    assert _refiner_jobs(client) == []


def test_handoff_without_a_configured_watched_folder_says_so(client: TestClient) -> None:
    r = client.post(
        "/api/v1/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-3",
            "mediaType": "tv",
            "sourcePath": "/srv/handoff/tv/Show/ep.mkv",
        },
    )
    assert r.status_code == 400
    assert "watched folder is not set" in r.json()["detail"]


def test_deluno_tv_handoff_uses_the_tv_watched_folder(client: TestClient) -> None:
    _set_watched_folders(client)
    r = client.post(
        "/api/v1/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-tv",
            "mediaType": "tv",
            "sourcePath": f"{WATCHED_TV}/Show/S01E01.mkv",
        },
    )
    assert r.status_code == 200
    import json

    payload = json.loads(_refiner_jobs(client)[0].payload_json)
    assert payload["relative_media_path"] == "Show/S01E01.mkv"
    assert payload["media_scope"] == "tv"


# --- the native shape, for a manager with no dialect of its own ---------------


def test_native_imported_event_enqueues_a_subtitle_import(client: TestClient) -> None:
    r = client.post(
        "/api/v1/intake/webhook/native",
        json={"event": "imported", "mediaScope": "movie", "filePath": "/media/m/x.mkv", "title": "X", "year": 1999},
    )
    assert r.status_code == 200
    assert r.json()["event"] == "imported"
    assert len(_subber_jobs(client)) == 1


def test_native_handoff_event_enqueues_a_refiner_pass(client: TestClient) -> None:
    _set_watched_folders(client)
    r = client.post(
        "/api/v1/intake/webhook/native",
        json={
            "event": "handoff",
            "mediaScope": "movie",
            "filePath": f"{WATCHED_MOVIES}/Native/x.mkv",
            "handoffId": "native-1",
        },
    )
    assert r.status_code == 200
    assert len(_refiner_jobs(client)) == 1


def test_native_event_missing_required_fields_is_ignored(client: TestClient) -> None:
    r = client.post("/api/v1/intake/webhook/native", json={"event": "imported", "title": "no path"})
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


# --- the endpoint itself -----------------------------------------------------


def test_unknown_source_names_the_ones_that_exist(client: TestClient) -> None:
    r = client.post("/api/v1/intake/webhook/plex", json={})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "plex" in detail
    for known in ("deluno", "native", "radarr", "sonarr"):
        assert known in detail


def test_source_key_is_case_insensitive(client: TestClient) -> None:
    r = client.post("/api/v1/intake/webhook/RADARR", json={"eventType": "Grab"})
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_configured_secret_is_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEDIAMOP_SUBBER_WEBHOOK_SECRET", "s3cret")
    app = create_app()
    with TestClient(app) as c:
        body = {"eventType": "Grab"}
        assert c.post("/api/v1/intake/webhook/radarr", json=body).status_code == 401
        assert (
            c.post("/api/v1/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": "wrong"}).status_code == 401
        )
        ok = c.post("/api/v1/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": "s3cret"})
        assert ok.status_code == 200
