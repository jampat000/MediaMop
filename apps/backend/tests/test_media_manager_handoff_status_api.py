"""HTTP: a media manager asking MediaMop about a hand-off it gave us, and cancelling one (#480).

Deluno stops timing hand-offs out and asks instead (Deluno#511). Two wrong answers are the ones
that cost somebody their media: saying "never heard of it" about a hand-off MediaMop finished
(Deluno then imports the unprocessed original), and letting a status read reveal file paths to
anyone who asks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import delete, select
from starlette.testclient import TestClient

from alembic import command
from mediamop.api.factory import create_app
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.jobs.job_rows_retention_periodic import prune_job_rows
from mediamop.platform.media_managers.handoff_ledger import LEDGER_RETENTION_DAYS, prune_ledger
from mediamop.platform.media_managers.handoff_ledger_model import MediaManagerHandoffRow
from mediamop.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)

WATCHED = "/srv/handoff/movies"
SECRET = {"X-Webhook-Secret": "s3cret"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_handoff_status")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MEDIAMOP_MEDIA_MANAGER_WEBHOOK_SECRET", "s3cret")
    with TestClient(create_app()) as c:
        from tests.refiner_library_fixtures import seed_refiner_libraries

        with _factory(c)() as db:
            seed_refiner_libraries(db, watched_folder=WATCHED, tv_watched_folder="/srv/handoff/tv")
            db.commit()
        yield c


def _factory(client: TestClient):
    from mediamop.core.db import create_db_engine, create_session_factory

    return create_session_factory(create_db_engine(client.app.state.settings))


def _hand_off(client: TestClient, handoff_id: str = "h1", name: str = "Film/film.mkv") -> None:
    response = client.post(
        "/api/v1/intake/webhook/deluno",
        headers=SECRET,
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": handoff_id,
            "libraryId": "lib-1",
            "mediaType": "movies",
            "sourcePath": f"{WATCHED}/{name}",
            "callbackPath": "/api/integrations/processors/events",
        },
    )
    assert response.status_code == 200, response.text


def _status(client: TestClient, handoff_id: str = "h1") -> dict:
    response = client.get(f"/api/v1/intake/handoffs/deluno/{handoff_id}", headers=SECRET)
    assert response.status_code == 200, response.text
    return response.json()


def _file_row(client: TestClient, status: RefinerFileStatus, **fields: object) -> None:
    with _factory(client)() as db:
        library_id = db.scalar(select(MediaManagerHandoffRow.library_id))
        db.add(RefinerFileRow(library_id=library_id, relative_path="Film/film.mkv", status=status.value, **fields))
        db.commit()


def _set_job_status(client: TestClient, status: RefinerJobStatus) -> None:
    with _factory(client)() as db:
        job = db.scalars(select(RefinerJob)).one()
        job.status = status.value
        db.commit()


# --- auth --------------------------------------------------------------------------------------


def test_no_configured_secret_is_a_403_that_says_what_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_MEDIA_MANAGER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("MEDIAMOP_SUBBER_WEBHOOK_SECRET", raising=False)
    with TestClient(create_app()) as c:
        for method, path in (
            ("GET", "/api/v1/intake/capabilities"),
            ("GET", "/api/v1/intake/handoffs/deluno/h1"),
            ("DELETE", "/api/v1/intake/handoffs/deluno/h1"),
        ):
            response = c.request(method, path)
            assert response.status_code == 403, (method, path)
            assert "Set a webhook secret" in response.json()["detail"]


def test_a_wrong_or_missing_secret_is_refused(client: TestClient) -> None:
    assert client.get("/api/v1/intake/handoffs/deluno/h1").status_code == 401
    assert client.get("/api/v1/intake/handoffs/deluno/h1", headers={"X-Webhook-Secret": "no"}).status_code == 401
    assert client.get("/api/v1/intake/capabilities", headers={"X-Webhook-Secret": "no"}).status_code == 401


def test_capabilities_name_both_abilities(client: TestClient) -> None:
    response = client.get("/api/v1/intake/capabilities", headers=SECRET)
    assert response.status_code == 200
    assert response.json() == {"capabilities": ["handoff-status", "handoff-cancel"]}


# --- status ------------------------------------------------------------------------------------


def test_an_unknown_hand_off_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/intake/handoffs/deluno/nope", headers=SECRET).status_code == 404


def test_a_new_hand_off_is_queued_with_its_place(client: TestClient) -> None:
    _hand_off(client)
    body = _status(client)
    assert body["handoffId"] == "h1"
    assert body["state"] == "queued"
    assert body["queuePosition"] == 1
    assert body["lastChangedUtc"].endswith("Z")


def test_a_running_pass_is_working(client: TestClient) -> None:
    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.LEASED)
    assert _status(client)["state"] == "working"


def test_a_pending_retry_is_scheduled_for_when_it_will_run(client: TestClient) -> None:
    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.COMPLETED)
    retry_at = datetime.now(UTC) + timedelta(minutes=20)
    _file_row(client, RefinerFileStatus.PROCESSING_FAILED, next_retry_at=retry_at, status_reason="ffmpeg died.")
    body = _status(client)
    assert body["state"] == "scheduled"
    assert body["scheduledFor"].startswith(retry_at.strftime("%Y-%m-%dT%H:%M"))


def test_waiting_for_the_manager_is_queued_not_stalled(client: TestClient) -> None:
    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.COMPLETED)
    _file_row(client, RefinerFileStatus.BLOCKED_UPSTREAM, status_reason="Deluno is still importing this file.")
    body = _status(client)
    assert body["state"] == "queued"
    assert body["message"] == "Deluno is still importing this file."


@pytest.mark.parametrize(
    ("file_status", "state"),
    [
        (RefinerFileStatus.PROCESSED, "completed"),
        (RefinerFileStatus.PASSED_THROUGH, "passed-through"),
        (RefinerFileStatus.REJECTED, "rejected"),
        (RefinerFileStatus.PROCESSING_FAILED, "failed"),
        (RefinerFileStatus.OUT_OF_SCHEDULE, "scheduled"),
    ],
)
def test_the_file_state_maps_to_the_agreed_vocabulary(
    client: TestClient, file_status: RefinerFileStatus, state: str
) -> None:
    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.COMPLETED)
    _file_row(client, file_status)
    assert _status(client)["state"] == state


def test_a_finished_hand_off_still_answers_after_job_rows_are_pruned(client: TestClient) -> None:
    """The reason the ledger exists. "Never heard of it" here would import the unprocessed original."""

    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.COMPLETED)
    _file_row(client, RefinerFileStatus.PROCESSED)
    assert _status(client)["state"] == "completed"

    with _factory(client)() as db:
        prune_job_rows(db, cutoff=datetime.now(UTC) + timedelta(days=1))
        db.execute(delete(RefinerFileRow))
        db.commit()

    assert _status(client)["state"] == "completed"


def test_a_repeated_poll_does_not_move_last_changed(client: TestClient) -> None:
    """Deluno reads an unchanged timestamp as "nothing happened". Polling must not reset it."""

    _hand_off(client)
    first = _status(client)["lastChangedUtc"]
    assert _status(client)["lastChangedUtc"] == first


def test_the_report_records_the_output_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from mediamop.platform.media_managers.completion_callback import report_handoff_completion

    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(202, request=httpx.Request("POST", url)))
    _hand_off(client)
    with _factory(client)() as db:
        job = db.scalars(select(RefinerJob)).one()
        report_handoff_completion(
            db,
            client.app.state.settings,
            payload_json=job.payload_json,
            result={"ok": True, "outcome": "live_output_written", "output_file": "/out/Film/film.mkv"},
        )
        db.execute(delete(RefinerJob))
        db.commit()
    body = _status(client)
    assert body["state"] == "completed"
    assert body["outputPath"] == "/out/Film/film.mkv"


# --- cancel ------------------------------------------------------------------------------------


def test_a_queued_hand_off_can_be_cancelled(client: TestClient, tmp_path: Path) -> None:
    _hand_off(client)
    response = client.delete("/api/v1/intake/handoffs/deluno/h1", headers=SECRET)
    assert response.status_code == 204, response.text
    with _factory(client)() as db:
        assert db.scalars(select(RefinerJob)).one().status == RefinerJobStatus.CANCELLED.value
        events = list(
            db.scalars(
                select(ActivityEvent).where(ActivityEvent.event_type == activity_constants.REFINER_HANDOFF_CANCELLED)
            )
        )
    assert events and "film.mkv" in events[-1].title
    assert _status(client)["state"] == "cancelled"
    # A second cancel is refused: it is already finished.
    assert client.delete("/api/v1/intake/handoffs/deluno/h1", headers=SECRET).status_code == 409


def test_work_that_has_started_is_never_cancelled(client: TestClient) -> None:
    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.LEASED)
    response = client.delete("/api/v1/intake/handoffs/deluno/h1", headers=SECRET)
    assert response.status_code == 409
    assert "working" in response.json()["detail"]
    with _factory(client)() as db:
        assert db.scalars(select(RefinerJob)).one().status == RefinerJobStatus.LEASED.value


def test_cancelling_an_unknown_hand_off_is_404(client: TestClient) -> None:
    assert client.delete("/api/v1/intake/handoffs/deluno/nope", headers=SECRET).status_code == 404


def test_a_manager_resending_a_cancelled_hand_off_starts_it_again(client: TestClient) -> None:
    _hand_off(client)
    assert client.delete("/api/v1/intake/handoffs/deluno/h1", headers=SECRET).status_code == 204
    _hand_off(client)
    assert _status(client)["state"] == "queued"


# --- retention ---------------------------------------------------------------------------------


def test_only_old_finished_hand_offs_are_pruned(client: TestClient) -> None:
    old = datetime.now(UTC) - timedelta(days=LEDGER_RETENTION_DAYS + 1)
    with _factory(client)() as db:
        for handoff_id, state in (("old-done", "completed"), ("old-waiting", "queued")):
            db.add(
                MediaManagerHandoffRow(
                    source_key="deluno",
                    handoff_id=handoff_id,
                    relative_path="x.mkv",
                    state=state,
                    created_at=old,
                    last_changed_at=old,
                )
            )
        db.commit()
        assert prune_ledger(db) == 1
        db.commit()
        remaining = {row.handoff_id for row in db.scalars(select(MediaManagerHandoffRow))}
    assert remaining == {"old-waiting"}


# --- folder hand-offs (Deluno names the completed download's folder) ----------------------------


def _watch(client: TestClient, folder: Path) -> None:
    from mediamop.refiner.refiner_library_model import RefinerLibraryRow

    with _factory(client)() as db:
        library = db.scalars(select(RefinerLibraryRow).where(RefinerLibraryRow.media_type == "movie")).one()
        library.watched_folder = str(folder)
        db.commit()


def _hand_off_folder(client: TestClient, watched: Path, name: str) -> int:
    return client.post(
        "/api/v1/intake/webhook/deluno",
        headers=SECRET,
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "h1",
            "libraryId": "lib-1",
            "mediaType": "movies",
            "sourcePath": str(watched / name),
            "callbackPath": "/api/integrations/processors/events",
        },
    ).status_code


def test_a_folder_hand_off_queues_the_video_inside_it_not_the_folder_or_the_sample(
    client: TestClient, tmp_path: Path
) -> None:
    watched = tmp_path / "watched"
    (watched / "Blade.Runner.2049" / "Sample").mkdir(parents=True)
    (watched / "Blade.Runner.2049" / "Blade.Runner.2049.mkv").write_bytes(b"x")
    (watched / "Blade.Runner.2049" / "Sample" / "sample.mkv").write_bytes(b"x")
    (watched / "Blade.Runner.2049" / "movie.nfo").write_text("x")
    _watch(client, watched)

    assert _hand_off_folder(client, watched, "Blade.Runner.2049") == 200
    with _factory(client)() as db:
        (job,) = db.scalars(select(RefinerJob)).all()
    assert '"relative_media_path":"Blade.Runner.2049/Blade.Runner.2049.mkv"' in (job.payload_json or "")
    # A repeated hand-off returns the same job rather than queueing the file twice.
    assert _hand_off_folder(client, watched, "Blade.Runner.2049") == 200
    with _factory(client)() as db:
        assert len(db.scalars(select(RefinerJob)).all()) == 1


def test_a_folder_with_no_video_is_refused_with_a_reason(client: TestClient, tmp_path: Path) -> None:
    watched = tmp_path / "watched"
    (watched / "Empty.Release").mkdir(parents=True)
    (watched / "Empty.Release" / "readme.txt").write_text("x")
    _watch(client, watched)
    response = client.post(
        "/api/v1/intake/webhook/deluno",
        headers=SECRET,
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "h1",
            "libraryId": "lib-1",
            "mediaType": "movies",
            "sourcePath": str(watched / "Empty.Release"),
            "callbackPath": "/api/integrations/processors/events",
        },
    )
    assert response.status_code == 400
    assert "no video file" in response.json()["detail"]


def test_a_folder_hand_off_answers_for_the_files_inside_it(client: TestClient, tmp_path: Path) -> None:
    watched = tmp_path / "watched"
    (watched / "Film").mkdir(parents=True)
    (watched / "Film" / "film.mkv").write_bytes(b"x")
    _watch(client, watched)
    assert _hand_off_folder(client, watched, "Film") == 200
    _set_job_status(client, RefinerJobStatus.COMPLETED)
    _file_row(client, RefinerFileStatus.PROCESSED)
    assert _status(client)["state"] == "completed"


def test_a_file_held_after_repeated_failures_is_failed_not_queued(client: TestClient) -> None:
    _hand_off(client)
    _set_job_status(client, RefinerJobStatus.COMPLETED)
    _file_row(client, RefinerFileStatus.ON_HOLD, failure_attempts=3)
    assert _status(client)["state"] == "failed"
