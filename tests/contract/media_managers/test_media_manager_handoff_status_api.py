"""Contract port of apps/backend/tests/test_media_manager_handoff_status_api.py."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.contract.media_managers._helpers import (
    CALLBACK_PATH,
    NO_WEBHOOK_SECRET,
    LibraryFolders,
    create_connection,
    create_library,
    ensure_library,
    handoff_dedupe_key,
    payload,
    remux_jobs,
    update_library,
)
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.fake_ffmpeg import FakeFfmpeg, fake_media_bytes, probe
from tests.contract.support.launcher import ServerUnderTest
from tests.contract.support.polling import wait_until

SECRET_VALUE = "s3cret"
SECRET = {"X-Webhook-Secret": SECRET_VALUE}
SECRET_ENV = {**NO_WEBHOOK_SECRET, "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": SECRET_VALUE}
#: Hand-off answers are kept this long once finished (``LEDGER_RETENTION_DAYS`` in the backend).
LEDGER_RETENTION_DAYS = 90


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return dict(SECRET_ENV)


@pytest.fixture(scope="module")
def module_folders(tmp_path_factory: pytest.TempPathFactory) -> tuple[LibraryFolders, LibraryFolders]:
    root = tmp_path_factory.mktemp("handoff_status_libraries")
    return LibraryFolders.make(root / "movies"), LibraryFolders.make(root / "tv")


@pytest.fixture
def movies(admin: WeirClient, module_folders: tuple[LibraryFolders, LibraryFolders]) -> LibraryFolders:
    """The module server's Movies and TV libraries have watched folders; returns the Movies folders."""

    movie_folders, tv_folders = module_folders
    ensure_library(admin, name="Movies", media_type="movie", folders=movie_folders)
    ensure_library(admin, name="TV", media_type="tv", folders=tv_folders)
    return movie_folders


def _new_id() -> str:
    return f"h-{uuid.uuid4().hex[:12]}"


def _hand_off_response(server: ServerUnderTest, handoff_id: str, source_path: Path) -> httpx.Response:
    return httpx.post(
        f"{server.base_url}{API}/intake/webhook/deluno",
        headers=SECRET,
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": handoff_id,
            "libraryId": "lib-1",
            "mediaType": "movies",
            "sourcePath": str(source_path),
            "callbackPath": CALLBACK_PATH,
        },
        timeout=30,
    )


def _hand_off(server: ServerUnderTest, handoff_id: str, source_path: Path) -> None:
    response = _hand_off_response(server, handoff_id, source_path)
    assert response.status_code == 200, response.text


def _status_response(server: ServerUnderTest, handoff_id: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.get(
        f"{server.base_url}{API}/intake/handoffs/deluno/{handoff_id}",
        headers=SECRET if headers is None else headers,
        timeout=30,
    )


def _status(server: ServerUnderTest, handoff_id: str) -> dict[str, Any]:
    response = _status_response(server, handoff_id)
    assert response.status_code == 200, response.text
    return response.json()


def _cancel(server: ServerUnderTest, handoff_id: str) -> httpx.Response:
    return httpx.delete(f"{server.base_url}{API}/intake/handoffs/deluno/{handoff_id}", headers=SECRET, timeout=30)


def _seed(
    server: ServerUnderTest,
    handoff_id: str,
    *,
    job_status: str | None = None,
    file_status: str | None = None,
    relative_path: str | None = None,
    **file_fields: Any,
) -> None:
    """While the server is stopped: move the hand-off's job rows, and give its file a Files row.

    ``leased`` cannot be seeded this way: startup treats a leased row as a dead worker's and
    requeues it. The tests that need running work use a real worker instead.
    """

    with seed.stopped(server) as conn:
        key = handoff_dedupe_key(handoff_id)
        if job_status is not None:
            changed = conn.execute(
                "UPDATE refiner_jobs SET status = ? WHERE dedupe_key = ? OR dedupe_key LIKE ?",
                (job_status, key, f"{key}:%"),
            ).rowcount
            assert changed, f"no job rows for {handoff_id}"
        if file_status is not None:
            ledger = seed.rows(
                conn,
                "SELECT library_id, relative_path FROM media_manager_handoffs WHERE source_key = ? AND handoff_id = ?",
                ("deluno", handoff_id),
            )
            assert ledger, f"no ledger row for {handoff_id}"
            columns = {
                "library_id": ledger[0]["library_id"],
                "relative_path": relative_path or ledger[0]["relative_path"],
                "status": file_status,
                **file_fields,
            }
            conn.execute(
                f"INSERT INTO refiner_files ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                tuple(columns.values()),
            )


# --- auth --------------------------------------------------------------------------------------


def test_no_configured_secret_is_a_403_that_says_what_to_set(server_factory) -> None:
    sut = server_factory(dict(NO_WEBHOOK_SECRET))
    for method, path in (
        ("GET", f"{API}/intake/capabilities"),
        ("GET", f"{API}/intake/handoffs/deluno/h1"),
        ("DELETE", f"{API}/intake/handoffs/deluno/h1"),
    ):
        response = httpx.request(method, f"{sut.base_url}{path}", timeout=30)
        assert response.status_code == 403, (method, path)
        assert "Set a webhook secret" in response.json()["detail"]


def test_a_wrong_or_missing_secret_is_refused(server: ServerUnderTest) -> None:
    assert _status_response(server, "h1", headers={}).status_code == 401
    assert _status_response(server, "h1", headers={"X-Webhook-Secret": "no"}).status_code == 401
    wrong = httpx.get(f"{server.base_url}{API}/intake/capabilities", headers={"X-Webhook-Secret": "no"}, timeout=30)
    assert wrong.status_code == 401


def test_capabilities_name_both_abilities(server: ServerUnderTest) -> None:
    response = httpx.get(f"{server.base_url}{API}/intake/capabilities", headers=SECRET, timeout=30)
    assert response.status_code == 200
    assert response.json() == {"capabilities": ["handoff-status", "handoff-cancel"]}


# --- status ------------------------------------------------------------------------------------


def test_an_unknown_hand_off_is_404(server: ServerUnderTest) -> None:
    assert _status_response(server, "nope").status_code == 404


def test_a_new_hand_off_is_queued_with_its_place(server_factory, client_factory, tmp_path: Path) -> None:
    # A server of its own, so no other test's queued work is ahead of this one.
    sut = server_factory(dict(SECRET_ENV))
    admin = client_factory(sut)
    admin.ensure_admin()
    folders = LibraryFolders.make(tmp_path / "movies")
    ensure_library(admin, name="Movies", media_type="movie", folders=folders)

    _hand_off(sut, "h1", folders.watched / "Film" / "film.mkv")
    body = _status(sut, "h1")
    assert body["handoffId"] == "h1"
    assert body["state"] == "queued"
    assert body["queuePosition"] == 1
    assert body["lastChangedUtc"].endswith("Z")


def test_a_pending_retry_is_scheduled_for_when_it_will_run(server: ServerUnderTest, movies: LibraryFolders) -> None:
    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    retry_at = datetime.now(UTC) + timedelta(minutes=20)
    _seed(
        server,
        hid,
        job_status="completed",
        file_status="processing_failed",
        next_retry_at=seed.utc_text(retry_at),
        status_reason="ffmpeg died.",
    )
    body = _status(server, hid)
    assert body["state"] == "scheduled"
    assert body["scheduledFor"].startswith(retry_at.strftime("%Y-%m-%dT%H:%M"))


def test_waiting_for_the_manager_is_queued_not_stalled(server: ServerUnderTest, movies: LibraryFolders) -> None:
    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    _seed(
        server,
        hid,
        job_status="completed",
        file_status="blocked_upstream",
        status_reason="Deluno is still importing this file.",
    )
    body = _status(server, hid)
    assert body["state"] == "queued"
    assert body["message"] == "Deluno is still importing this file."


@pytest.mark.parametrize(
    ("file_status", "state"),
    [
        ("processed", "completed"),
        ("passed_through", "passed-through"),
        ("rejected", "rejected"),
        ("processing_failed", "failed"),
        ("out_of_schedule", "scheduled"),
    ],
)
def test_the_file_state_maps_to_the_agreed_vocabulary(
    server: ServerUnderTest, movies: LibraryFolders, file_status: str, state: str
) -> None:
    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    _seed(server, hid, job_status="completed", file_status=file_status)
    assert _status(server, hid)["state"] == state


def test_a_finished_hand_off_still_answers_after_job_rows_are_pruned(
    server: ServerUnderTest, movies: LibraryFolders
) -> None:
    """The reason the ledger exists. "Never heard of it" here would import the unprocessed original."""

    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    _seed(server, hid, job_status="completed", file_status="processed")
    assert _status(server, hid)["state"] == "completed"

    # What job-row retention and "clear history" leave behind: no job row, no Files row.
    with seed.stopped(server) as conn:
        key = handoff_dedupe_key(hid)
        assert conn.execute("DELETE FROM refiner_jobs WHERE dedupe_key = ?", (key,)).rowcount == 1
        assert conn.execute("DELETE FROM refiner_files WHERE relative_path = ?", (f"{hid}/film.mkv",)).rowcount == 1

    assert _status(server, hid)["state"] == "completed"


def test_a_repeated_poll_does_not_move_last_changed(server: ServerUnderTest, movies: LibraryFolders) -> None:
    """Deluno reads an unchanged timestamp as "nothing happened". Polling must not reset it."""

    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    first = _status(server, hid)["lastChangedUtc"]
    assert _status(server, hid)["lastChangedUtc"] == first


# --- running work: a real worker with a fake ffmpeg ------------------------------------------------


@dataclass
class WorkingServer:
    server: ServerUnderTest
    admin: WeirClient
    folders: LibraryFolders


def _working_server(
    server_factory, client_factory, fake_managers, fake_ffmpeg: FakeFfmpeg, root: Path
) -> tuple[WorkingServer, Any]:
    """One worker, fake tools, a Movies library that takes a fresh file at once, and a fake Deluno."""

    sut = server_factory({**SECRET_ENV, **fake_ffmpeg.env, "WEIR_REFINER_WORKER_COUNT": "1"})
    admin = client_factory(sut)
    admin.ensure_admin()
    relaxed = admin.put_csrf(
        f"{API}/refiner/operator-settings",
        {"min_file_age_seconds": 0, "refiner_min_input_file_size_mb": 0, "minimum_free_disk_space_mb": 0},
    )
    assert relaxed.status_code == 200, relaxed.text
    folders = LibraryFolders.make(root / "library")
    work = root / "library" / "work"
    work.mkdir(parents=True, exist_ok=True)
    listed = admin.get(f"{API}/refiner/libraries").json()
    for row in listed:
        if row["media_type"] == "movie":
            update_library(
                admin,
                row,
                watched_folder=str(folders.watched),
                output_folder=str(folders.output),
                work_folder=str(work),
                min_file_age_seconds=0,
                file_detection_interval_seconds=0,
                skip_access_tests=True,
                min_file_size_mb=0,
            )
            break
    else:
        create_library(
            admin,
            name="Movies",
            media_type="movie",
            folders=folders,
            work_folder=str(work),
            min_file_age_seconds=0,
            file_detection_interval_seconds=0,
            skip_access_tests=True,
            min_file_size_mb=0,
        )
    deluno = fake_managers("deluno")
    created = create_connection(admin, name="Deluno", base_url=deluno.base_url, api_key=deluno.api_key)
    assert created.status_code == 201, created.text
    source = folders.watched / "Film" / "film.mkv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(fake_media_bytes(probe()))
    return WorkingServer(sut, admin, folders), deluno


def _job_status(admin: WeirClient, handoff_id: str) -> str | None:
    """The newest remux job for this hand-off. Matched on the payload: cancelling renames the dedupe key."""

    for job in remux_jobs(admin):
        if (payload(job).get("origin") or {}).get("handoff_id") == handoff_id:
            return job["status"]
    return None


def test_a_running_pass_is_working(server_factory, client_factory, fake_managers, fake_ffmpeg, tmp_path) -> None:
    fake_ffmpeg.set_file_rule("*.mkv", probe=probe(), remux_delay_seconds=20)
    working, _ = _working_server(server_factory, client_factory, fake_managers, fake_ffmpeg, tmp_path)
    _hand_off(working.server, "h1", working.folders.watched / "Film" / "film.mkv")

    wait_until(lambda: _job_status(working.admin, "h1") == "leased", timeout_s=60, what="the worker to take the job")
    assert _status(working.server, "h1")["state"] == "working"


def test_the_report_records_the_output_path(
    server_factory, client_factory, fake_managers, fake_ffmpeg, tmp_path
) -> None:
    # The original called the completion report directly; here a worker finishes the file and reports.
    fake_ffmpeg.set_file_rule("*.mkv", probe=probe())
    working, deluno = _working_server(server_factory, client_factory, fake_managers, fake_ffmpeg, tmp_path)
    _hand_off(working.server, "h1", working.folders.watched / "Film" / "film.mkv")

    body = wait_until(
        lambda: (answer := _status(working.server, "h1"))["state"] not in ("queued", "working") and answer,
        timeout_s=90,
        what="the hand-off to finish",
    )
    deluno.wait_for_request("POST", CALLBACK_PATH)
    assert body["state"] == "completed", body
    assert body["outputPath"]
    output = Path(body["outputPath"])
    assert output.name == "film.mkv"
    assert output.is_file()
    assert working.folders.output.resolve() in output.resolve().parents


# --- cancel ------------------------------------------------------------------------------------


def test_a_queued_hand_off_can_be_cancelled(server: ServerUnderTest, movies: LibraryFolders, client_factory) -> None:
    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    response = _cancel(server, hid)
    assert response.status_code == 204, response.text

    admin = client_factory(server)
    admin.ensure_admin()
    assert _job_status(admin, hid) == "cancelled"
    events = admin.get(f"{API}/activity/recent", params={"event_type": "refiner.handoff_cancelled", "limit": 100})
    assert events.status_code == 200, events.text
    titles = [item["title"] for item in events.json()["items"]]
    assert any("film.mkv" in title for title in titles), titles
    assert _status(server, hid)["state"] == "cancelled"
    # A second cancel is refused: it is already finished.
    assert _cancel(server, hid).status_code == 409


def test_work_that_has_started_is_never_cancelled(
    server_factory, client_factory, fake_managers, fake_ffmpeg, tmp_path
) -> None:
    fake_ffmpeg.set_file_rule("*.mkv", probe=probe(), remux_delay_seconds=20)
    working, _ = _working_server(server_factory, client_factory, fake_managers, fake_ffmpeg, tmp_path)
    _hand_off(working.server, "h1", working.folders.watched / "Film" / "film.mkv")
    wait_until(lambda: _job_status(working.admin, "h1") == "leased", timeout_s=60, what="the worker to take the job")

    response = _cancel(working.server, "h1")
    assert response.status_code == 409
    assert "working" in response.json()["detail"]
    assert _job_status(working.admin, "h1") == "leased"


def test_cancelling_an_unknown_hand_off_is_404(server: ServerUnderTest) -> None:
    assert _cancel(server, "nope").status_code == 404


def test_a_manager_resending_a_cancelled_hand_off_starts_it_again(
    server: ServerUnderTest, movies: LibraryFolders
) -> None:
    hid = _new_id()
    source = movies.watched / hid / "film.mkv"
    _hand_off(server, hid, source)
    assert _cancel(server, hid).status_code == 204
    _hand_off(server, hid, source)
    assert _status(server, hid)["state"] == "queued"


# --- retention ---------------------------------------------------------------------------------


def test_only_old_finished_hand_offs_are_pruned(server: ServerUnderTest) -> None:
    # The original called the prune function; here the retention tick that runs at startup does it.
    old = seed.utc_text(datetime.now(UTC) - timedelta(days=LEDGER_RETENTION_DAYS + 1))
    done, waiting = _new_id(), _new_id()
    with seed.stopped(server) as conn:
        for handoff_id, state in ((done, "completed"), (waiting, "queued")):
            conn.execute(
                "INSERT INTO media_manager_handoffs (source_key, handoff_id, relative_path, state, created_at, "
                "last_changed_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("deluno", handoff_id, "x.mkv", state, old, old),
            )

    wait_until(
        lambda: _status_response(server, done).status_code == 404,
        timeout_s=30,
        what="the old finished hand-off to be pruned",
    )
    assert _status(server, waiting)["state"] == "queued"


# --- folder hand-offs (Deluno names the completed download's folder) ----------------------------


def _folder_library(admin: WeirClient, root: Path) -> LibraryFolders:
    folders = LibraryFolders.make(root)
    create_library(admin, name=f"Folder {uuid.uuid4().hex[:8]}", media_type="movie", folders=folders)
    return folders


def test_a_folder_hand_off_queues_the_video_inside_it_not_the_folder_or_the_sample(
    server: ServerUnderTest, admin: WeirClient, tmp_path: Path
) -> None:
    folders = _folder_library(admin, tmp_path / "folder-library")
    watched = folders.watched
    (watched / "Blade.Runner.2049" / "Sample").mkdir(parents=True)
    (watched / "Blade.Runner.2049" / "Blade.Runner.2049.mkv").write_bytes(b"x")
    (watched / "Blade.Runner.2049" / "Sample" / "sample.mkv").write_bytes(b"x")
    (watched / "Blade.Runner.2049" / "movie.nfo").write_text("x")
    hid = _new_id()
    key = handoff_dedupe_key(hid)

    def jobs() -> list[dict[str, Any]]:
        return [j for j in remux_jobs(admin) if j["dedupe_key"] == key or j["dedupe_key"].startswith(f"{key}:")]

    assert _hand_off_response(server, hid, watched / "Blade.Runner.2049").status_code == 200
    (job,) = jobs()
    assert '"relative_media_path":"Blade.Runner.2049/Blade.Runner.2049.mkv"' in (job["payload_json"] or "")
    assert payload(job)["relative_media_path"] == "Blade.Runner.2049/Blade.Runner.2049.mkv"
    # A repeated hand-off returns the same job rather than queueing the file twice.
    assert _hand_off_response(server, hid, watched / "Blade.Runner.2049").status_code == 200
    assert len(jobs()) == 1


def test_a_folder_with_no_video_is_refused_with_a_reason(
    server: ServerUnderTest, admin: WeirClient, tmp_path: Path
) -> None:
    folders = _folder_library(admin, tmp_path / "folder-library")
    (folders.watched / "Empty.Release").mkdir(parents=True)
    (folders.watched / "Empty.Release" / "readme.txt").write_text("x")
    response = _hand_off_response(server, _new_id(), folders.watched / "Empty.Release")
    assert response.status_code == 400
    assert "no video file" in response.json()["detail"]


def test_a_folder_hand_off_answers_for_the_files_inside_it(
    server: ServerUnderTest, admin: WeirClient, tmp_path: Path
) -> None:
    folders = _folder_library(admin, tmp_path / "folder-library")
    (folders.watched / "Film").mkdir(parents=True)
    (folders.watched / "Film" / "film.mkv").write_bytes(b"x")
    hid = _new_id()
    assert _hand_off_response(server, hid, folders.watched / "Film").status_code == 200
    _seed(server, hid, job_status="completed", file_status="processed", relative_path="Film/film.mkv")
    assert _status(server, hid)["state"] == "completed"


def test_a_file_held_after_repeated_failures_is_failed_not_queued(
    server: ServerUnderTest, movies: LibraryFolders
) -> None:
    hid = _new_id()
    _hand_off(server, hid, movies.watched / hid / "film.mkv")
    _seed(server, hid, job_status="completed", file_status="on_hold", failure_attempts=3)
    assert _status(server, hid)["state"] == "failed"
