"""Contract port of the retired Python backend's tests/test_refiner_jobs_inspection_api.py (inspection + cancel-pending)."""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.contract.jobs._helpers import (
    VIEWER_PASSWORD,
    VIEWER_USERNAME,
    ensure_viewer,
    insert_job,
    inspection,
    job_by_id,
    library_for_scope,
    save_library,
)
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until

SWEEP = "refiner.work_temp_stale_sweep.v1"
REMUX = "refiner.file.remux_pass.v1"
SCAN = "refiner.watched_folder.remux_scan_dispatch.v1"


@pytest.fixture
def reseed(server, admin, client_factory) -> Callable[..., WeirClient]:
    """``reseed(write, username=None)``: clear ``refiner_jobs``, run ``write(conn)``, return a signed-in client.

    Rows are written while the server is stopped. A ``leased`` row written that way is recovered to
    ``pending`` at startup (a lease held across a restart belongs to a dead worker), so leased rows
    come from a live worker instead; see :func:`_leased_job`.
    """

    def make(write: Callable[[sqlite3.Connection], object], *, username: str | None = None) -> WeirClient:
        with seed.stopped(server) as conn:
            conn.execute("DELETE FROM refiner_jobs")
            write(conn)
            ensure_viewer(conn)
        client = client_factory(server)
        if username == VIEWER_USERNAME:
            client.login(VIEWER_USERNAME, VIEWER_PASSWORD)
        else:
            client.login()
        return client

    return make


def _seed_mixed_status_rows(conn: sqlite3.Connection) -> dict[str, int]:
    now = datetime.now(UTC)
    t0, t1, t2 = now - timedelta(hours=3), now - timedelta(hours=2), now - timedelta(hours=1)
    return {
        "pending": insert_job(conn, dedupe_key="rinsp-pending", job_kind=SWEEP, status="pending", updated_at=t0),
        "done": insert_job(
            conn, dedupe_key="rinsp-done", job_kind=REMUX, status="completed", attempt_count=1, updated_at=t2
        ),
        "fail": insert_job(
            conn,
            dedupe_key="rinsp-fail",
            job_kind=SCAN,
            status="failed",
            attempt_count=2,
            max_attempts=2,
            last_error="handler boom",
            updated_at=t1,
        ),
        "finalize": insert_job(
            conn,
            dedupe_key="rinsp-finalize",
            job_kind=REMUX,
            status="handler_ok_finalize_failed",
            attempt_count=1,
            last_error="finalize",
            updated_at=t2,
        ),
        "cancelled": insert_job(conn, dedupe_key="rinsp-cancelled", job_kind=SWEEP, status="cancelled", updated_at=t1),
    }


@contextmanager
def _leased_job(server_factory, client_factory, fake_ffmpeg, tmp_path: Path) -> Iterator[tuple[WeirClient, int]]:
    """A server with one worker holding a lease on a slow remux; yields (admin client, job id)."""

    fake_ffmpeg.set_file_rule("*.mkv", remux_delay_seconds=120)
    sut = server_factory(env={**fake_ffmpeg.env, "WEIR_REFINER_WORKER_COUNT": "1"})
    client = client_factory(sut)
    client.ensure_admin()
    watched, output = tmp_path / "leased-watch", tmp_path / "leased-out"
    watched.mkdir()
    output.mkdir()
    media = watched / "film.mkv"
    media.write_bytes(
        fake_media_bytes(
            probe(audio_languages=("eng", "fre", "ger"), subtitle_languages=("eng", "spa")),
            padding=51 * 1024 * 1024,  # above the smallest file Refiner will process
        )
    )
    settled = time.time() - 7200  # old enough for the settling guardrail
    os.utime(media, (settled, settled))
    library = library_for_scope(client, "movie")
    save_library(client, library["id"], watched_folder=str(watched), output_folder=str(output))
    r = client.post_csrf(f"{API}/refiner/jobs/file-remux-pass/enqueue", json={"relative_media_path": "film.mkv"})
    assert r.status_code == 200, r.text
    job_id = int(r.json()["job_id"])
    wait_until(lambda: job_by_id(client, job_id)["status"] == "leased", timeout_s=60, what="a worker to lease the job")
    yield client, job_id


def test_refiner_jobs_inspection_requires_auth(client: WeirClient) -> None:
    r = client.get(f"{API}/refiner/jobs/inspection")
    assert r.status_code == 401


def test_refiner_jobs_inspection_default_includes_pending_and_leased(reseed) -> None:
    client = reseed(_seed_mixed_status_rows)
    r = client.get(f"{API}/refiner/jobs/inspection?limit=20")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_recent_slice"] is True
    kinds = {j["job_kind"] for j in body["jobs"]}
    assert SWEEP in kinds
    statuses = {j["status"] for j in body["jobs"]}
    assert "pending" in statuses
    assert "cancelled" in statuses
    assert "failed" in statuses
    assert "handler_ok_finalize_failed" in statuses
    # Newest ``updated_at`` first.
    stamps = [j["updated_at"] for j in body["jobs"]]
    assert stamps == sorted(stamps, reverse=True)


def test_refiner_jobs_inspection_default_includes_a_leased_job(
    server_factory, client_factory, fake_ffmpeg, tmp_path: Path
) -> None:
    with _leased_job(server_factory, client_factory, fake_ffmpeg, tmp_path) as (client, job_id):
        body = inspection(client, limit=20)
        assert body["default_recent_slice"] is True
        leased = [j for j in body["jobs"] if j["id"] == job_id]
        assert leased and leased[0]["status"] == "leased"
        assert leased[0]["lease_owner"]
        assert leased[0]["lease_expires_at"] is not None


def test_refiner_jobs_inspection_returns_operator_guidance_and_keeps_lock_detail_secondary(reseed) -> None:
    client = reseed(
        lambda conn: insert_job(
            conn,
            dedupe_key="operator-guidance-lock",
            job_kind=REMUX,
            status="failed",
            last_error="sqlite3.OperationalError: database is locked",
            payload_json='{"relative_media_path":"Movie/Film.mkv"}',
        )
    )

    response = client.get(f"{API}/refiner/jobs/inspection?limit=10")

    assert response.status_code == 200, response.text
    job = next(item for item in response.json()["jobs"] if item["dedupe_key"] == "operator-guidance-lock")
    assert "could not save the Refiner result" in job["operator_message"]
    assert "Files at once" in job["next_action"]
    assert job["technical_detail"] == "sqlite3.OperationalError: database is locked"


def test_refiner_jobs_inspection_status_filter(reseed) -> None:
    client = reseed(_seed_mixed_status_rows)
    r = client.get(f"{API}/refiner/jobs/inspection?status=pending&limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_recent_slice"] is False
    assert body["jobs"]
    assert all(j["status"] == "pending" for j in body["jobs"])


def test_refiner_jobs_default_hides_successful_periodic_scan_noise(reseed) -> None:
    def write(conn: sqlite3.Connection) -> None:
        insert_job(conn, dedupe_key="routine-scan", job_kind=SCAN, status="completed")
        insert_job(conn, dedupe_key="material-file-work", job_kind=REMUX, status="completed")

    client = reseed(write)
    recent = client.get(f"{API}/refiner/jobs/inspection?limit=20")
    completed = client.get(f"{API}/refiner/jobs/inspection?status=completed&limit=20")

    assert recent.status_code == 200, recent.text
    assert [row["dedupe_key"] for row in recent.json()["jobs"]] == ["material-file-work"]
    assert completed.status_code == 200, completed.text
    assert {row["dedupe_key"] for row in completed.json()["jobs"]} == {"routine-scan", "material-file-work"}


def test_refiner_jobs_inspection_invalid_status_422(admin: WeirClient) -> None:
    r = admin.get(f"{API}/refiner/jobs/inspection?status=not_a_real_status")
    assert r.status_code == 422


def test_refiner_job_cancel_pending_ok(reseed) -> None:
    ids: dict[str, int] = {}

    def write(conn: sqlite3.Connection) -> None:
        ids["job"] = insert_job(conn, dedupe_key="to-cancel-contract", job_kind=SWEEP, status="pending")

    client = reseed(write)
    jid = ids["job"]
    r = client.post_csrf(f"{API}/refiner/jobs/{jid}/cancel-pending")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["status"] == "cancelled"

    row = job_by_id(client, jid)
    assert row["status"] == "cancelled"
    assert ":cancelled:" in row["dedupe_key"]


def test_refiner_job_cancel_pending_refuses_leased(server_factory, client_factory, fake_ffmpeg, tmp_path: Path) -> None:
    with _leased_job(server_factory, client_factory, fake_ffmpeg, tmp_path) as (client, job_id):
        r = client.post_csrf(f"{API}/refiner/jobs/{job_id}/cancel-pending")
        assert r.status_code == 409
        assert job_by_id(client, job_id)["status"] == "leased"


def test_refiner_jobs_inspection_viewer_can_read(reseed) -> None:
    client = reseed(_seed_mixed_status_rows, username=VIEWER_USERNAME)
    r = client.get(f"{API}/refiner/jobs/inspection?limit=5")
    assert r.status_code == 200, r.text
    assert "jobs" in r.json()


def test_refiner_job_cancel_pending_viewer_forbidden(reseed) -> None:
    ids: dict[str, int] = {}

    def write(conn: sqlite3.Connection) -> None:
        ids["job"] = insert_job(conn, dedupe_key="viewer-deny", job_kind=SWEEP, status="pending")

    client = reseed(write, username=VIEWER_USERNAME)
    r = client.post_csrf(f"{API}/refiner/jobs/{ids['job']}/cancel-pending")
    assert r.status_code == 403
