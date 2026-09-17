"""Contract port of apps/backend/tests/test_media_manager_intake_api.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.media_managers._helpers import (
    CALLBACK_PATH,
    NO_WEBHOOK_SECRET,
    REMUX_KIND,
    LibraryFolders,
    ensure_library,
    handoff_dedupe_key,
    payload,
    remux_jobs,
)
from tests.contract.support.client import API, WeirClient


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return dict(NO_WEBHOOK_SECRET)


@pytest.fixture(scope="module")
def watched(tmp_path_factory: pytest.TempPathFactory) -> tuple[LibraryFolders, LibraryFolders]:
    root = tmp_path_factory.mktemp("intake_libraries")
    return LibraryFolders.make(root / "movies"), LibraryFolders.make(root / "tv")


@pytest.fixture
def with_watched_folders(admin: WeirClient, watched: tuple[LibraryFolders, LibraryFolders]) -> WeirClient:
    """The admin client, on a server whose Movies and TV libraries have watched folders."""

    movies, tv = watched
    ensure_library(admin, name="Movies", media_type="movie", folders=movies)
    ensure_library(admin, name="TV", media_type="tv", folders=tv)
    return admin


# --- the dialects that replaced the per-vendor webhook routes -----------------


def test_sonarr_non_download_is_ignored(client: WeirClient) -> None:
    r = client.post(f"{API}/intake/webhook/sonarr", json={"eventType": "Grab", "episodes": [{"id": 1}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ignored", "source": "sonarr"}


def test_sonarr_download_is_accepted_and_ignored(admin: WeirClient) -> None:
    before = len(remux_jobs(admin))
    r = admin.post(
        f"{API}/intake/webhook/sonarr",
        json={
            "eventType": "Download",
            "series": {"title": "Test Show"},
            "episodes": [{"id": 9, "seasonNumber": 1, "episodeNumber": 2, "title": "Hello"}],
            "episodeFile": {"path": "/media/t/x.mkv"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ignored"
    assert body["event"] == "imported"
    assert len(remux_jobs(admin)) == before


def test_radarr_non_download_is_ignored(client: WeirClient) -> None:
    r = client.post(f"{API}/intake/webhook/radarr", json={"eventType": "Grab", "movie": {"id": 1}})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ignored"


def test_radarr_download_is_accepted_and_ignored(admin: WeirClient) -> None:
    before = len(remux_jobs(admin))
    r = admin.post(
        f"{API}/intake/webhook/radarr",
        json={
            "eventType": "Download",
            "movie": {"id": 3, "title": "Film", "year": 2010},
            "movieFile": {"path": "/media/m/f.mkv"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ignored"
    assert len(remux_jobs(admin)) == before


# --- the hand-off path, which is what a manager like Deluno needs -------------


def _jobs_for_handoff(client: WeirClient, handoff_id: str) -> list[dict]:
    key = handoff_dedupe_key(handoff_id)
    return [job for job in remux_jobs(client) if job["dedupe_key"] == key]


def test_deluno_handoff_enqueues_a_refiner_pass_with_a_relative_path(
    with_watched_folders: WeirClient, watched: tuple[LibraryFolders, LibraryFolders]
) -> None:
    client = with_watched_folders
    movies, _ = watched
    r = client.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-1",
            "libraryId": "lib-1",
            "mediaType": "movies",
            "sourcePath": str(movies.watched / "Blade.Runner.2049" / "film.mkv"),
            "releaseName": "Blade.Runner.2049",
            "callbackPath": CALLBACK_PATH,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event"] == "handoff"
    assert body["enqueued"] == REMUX_KIND

    jobs = _jobs_for_handoff(client, "handoff-1")
    assert len(jobs) == 1
    job_payload = payload(jobs[0])
    assert job_payload["relative_media_path"] == "Blade.Runner.2049/film.mkv"
    assert job_payload["media_scope"] == "movie"
    assert job_payload["origin"]["handoff_id"] == "handoff-1"
    assert job_payload["origin"]["callback_path"] == CALLBACK_PATH
    # Deluno refuses a processor event that does not name its library, so the id has to
    # survive from the hand-off to the report.
    assert job_payload["origin"]["library_id"] == "lib-1"
    assert job_payload["trigger"] == "webhook"


def test_repeated_handoff_id_does_not_remux_the_file_twice(
    with_watched_folders: WeirClient, watched: tuple[LibraryFolders, LibraryFolders]
) -> None:
    client = with_watched_folders
    movies, _ = watched
    body = {
        "eventType": "deluno.processor-handoff",
        "handoffId": "handoff-same",
        "mediaType": "movies",
        "sourcePath": str(movies.watched / "Repeat" / "film.mkv"),
    }
    before = len(remux_jobs(client))
    assert client.post(f"{API}/intake/webhook/deluno", json=body).status_code == 200
    assert client.post(f"{API}/intake/webhook/deluno", json=body).status_code == 200
    assert len(_jobs_for_handoff(client, "handoff-same")) == 1
    assert len(remux_jobs(client)) == before + 1


def test_handoff_outside_the_watched_folder_is_refused_with_a_plain_reason(
    with_watched_folders: WeirClient, tmp_path: Path
) -> None:
    client = with_watched_folders
    before = len(remux_jobs(client))
    r = client.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-2",
            "mediaType": "movies",
            "sourcePath": str(tmp_path / "somewhere" / "else" / "film.mkv"),
        },
    )
    assert r.status_code == 400, r.text
    assert "not inside Refiner's watched folder" in r.json()["detail"]
    assert len(remux_jobs(client)) == before


def test_handoff_without_a_configured_watched_folder_says_so(server_factory, client_factory, tmp_path: Path) -> None:
    # A server of its own: the module server has watched folders once any hand-off test has run.
    fresh = server_factory(dict(NO_WEBHOOK_SECRET))
    client = client_factory(fresh)
    r = client.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-3",
            "mediaType": "tv",
            "sourcePath": str(tmp_path / "handoff" / "tv" / "Show" / "ep.mkv"),
        },
    )
    assert r.status_code == 400, r.text
    assert "watched folder is not set" in r.json()["detail"]


def test_deluno_tv_handoff_uses_the_tv_watched_folder(
    with_watched_folders: WeirClient, watched: tuple[LibraryFolders, LibraryFolders]
) -> None:
    client = with_watched_folders
    _, tv = watched
    r = client.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "handoff-tv",
            "mediaType": "tv",
            "sourcePath": str(tv.watched / "Show" / "S01E01.mkv"),
        },
    )
    assert r.status_code == 200, r.text
    (job,) = _jobs_for_handoff(client, "handoff-tv")
    job_payload = payload(job)
    assert job_payload["relative_media_path"] == "Show/S01E01.mkv"
    assert job_payload["media_scope"] == "tv"


# --- the native shape, for a manager with no dialect of its own ---------------


def test_native_imported_event_is_accepted_and_ignored(admin: WeirClient) -> None:
    before = len(remux_jobs(admin))
    r = admin.post(
        f"{API}/intake/webhook/native",
        json={"event": "imported", "mediaScope": "movie", "filePath": "/media/m/x.mkv", "title": "X", "year": 1999},
    )
    assert r.status_code == 200, r.text
    assert r.json()["event"] == "imported"
    assert r.json()["status"] == "ignored"
    assert len(remux_jobs(admin)) == before


def test_native_handoff_event_enqueues_a_refiner_pass(
    with_watched_folders: WeirClient, watched: tuple[LibraryFolders, LibraryFolders]
) -> None:
    client = with_watched_folders
    movies, _ = watched
    r = client.post(
        f"{API}/intake/webhook/native",
        json={
            "event": "handoff",
            "mediaScope": "movie",
            "filePath": str(movies.watched / "Native" / "x.mkv"),
            "handoffId": "native-1",
        },
    )
    assert r.status_code == 200, r.text
    key = handoff_dedupe_key("native-1", source_key="native")
    assert len([job for job in remux_jobs(client) if job["dedupe_key"] == key]) == 1


def test_native_event_missing_required_fields_is_ignored(client: WeirClient) -> None:
    r = client.post(f"{API}/intake/webhook/native", json={"event": "imported", "title": "no path"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ignored"


# --- the endpoint itself -----------------------------------------------------


def test_unknown_source_names_the_ones_that_exist(client: WeirClient) -> None:
    r = client.post(f"{API}/intake/webhook/plex", json={})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "plex" in detail
    for known in ("deluno", "native", "radarr", "sonarr"):
        assert known in detail


def test_source_key_is_case_insensitive(client: WeirClient) -> None:
    r = client.post(f"{API}/intake/webhook/RADARR", json={"eventType": "Grab"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ignored"


def test_configured_secret_is_required(server_factory, client_factory) -> None:
    sut = server_factory({**NO_WEBHOOK_SECRET, "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": "s3cret"})
    c = client_factory(sut)
    body = {"eventType": "Grab"}
    assert c.post(f"{API}/intake/webhook/radarr", json=body).status_code == 401
    assert c.post(f"{API}/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": "wrong"}).status_code == 401
    ok = c.post(f"{API}/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": "s3cret"})
    assert ok.status_code == 200


def test_the_old_subber_env_name_still_configures_the_secret(server_factory, client_factory) -> None:
    """The setting was named for Subber; the endpoint it guards outlived the name.

    An install that set WEIR_SUBBER_WEBHOOK_SECRET and never renamed it must keep
    authenticating, because the alternative is a webhook that quietly stops checking.
    """

    sut = server_factory({**NO_WEBHOOK_SECRET, "WEIR_SUBBER_WEBHOOK_SECRET": "s3cret"})
    c = client_factory(sut)
    body = {"eventType": "Grab"}
    assert c.post(f"{API}/intake/webhook/radarr", json=body).status_code == 401
    ok = c.post(f"{API}/intake/webhook/radarr", json=body, headers={"X-Webhook-Secret": "s3cret"})
    assert ok.status_code == 200
