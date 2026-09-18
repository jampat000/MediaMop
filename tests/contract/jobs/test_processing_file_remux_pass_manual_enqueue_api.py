"""Contract port of the retired Python backend's tests/test_processing_file_remux_pass_manual_enqueue_api.py."""

from __future__ import annotations

import json
from pathlib import Path

from tests.contract.jobs._helpers import all_jobs, job_by_id, set_movie_folders
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

REMUX = "processing.file.remux_pass.v1"
ENQUEUE = f"{API}/processing/jobs/file-remux-pass/enqueue"


def test_processing_file_remux_pass_enqueue_writes_live_payload(admin: WeirClient, tmp_path: Path) -> None:
    watch = tmp_path / "remux_watch"
    watch.mkdir()
    out = tmp_path / "remux_out"
    out.mkdir()
    set_movie_folders(admin, watched=str(watch.resolve()), output=str(out.resolve()))
    r = admin.post_csrf(ENQUEUE, json={"relative_media_path": "movies/sample.mkv"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["job_kind"] == REMUX
    row = job_by_id(admin, body["job_id"])
    assert row["job_kind"] == REMUX
    assert row["status"] == "pending"
    assert '"dry_run"' not in (row["payload_json"] or "")
    assert '"relative_media_path":"movies/sample.mkv"' in (row["payload_json"] or "")


def test_processing_file_remux_pass_enqueue_rejects_missing_watched_folder(admin: WeirClient, tmp_path: Path) -> None:
    out = tmp_path / "enqueue_out_only"
    out.mkdir()
    set_movie_folders(admin, watched=None, output=str(out.resolve()))
    r = admin.post_csrf(ENQUEUE, json={"relative_media_path": "movies/sample.mkv"})
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "")
    assert isinstance(detail, str)
    assert "watched folder" in detail.lower()
    assert "path settings" in detail.lower()


def test_pass_through_converts_an_existing_pending_job_instead_of_duplicating_it(
    server, admin: WeirClient, client_factory, tmp_path: Path
) -> None:
    watch = tmp_path / "pass_watch"
    watch.mkdir()
    out = tmp_path / "pass_out"
    out.mkdir()
    set_movie_folders(admin, watched=str(watch.resolve()), output=str(out.resolve()))

    first = admin.post_csrf(ENQUEUE, json={"relative_media_path": "Foreign/film.mkv"})
    assert first.status_code == 200, first.text
    job_id = first.json()["job_id"]

    # A hand-off from a media manager adds its origin to the queued job; no API writes that, so
    # it is added to the row while the server is stopped. Other remux jobs are cleared so the count is exact.
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM jobs WHERE id != ? AND job_kind = ?", (job_id, REMUX))
        raw = seed.scalar(conn, "SELECT payload_json FROM jobs WHERE id = ?", (job_id,))
        queued_payload = json.loads(raw or "{}")
        queued_payload["origin"] = {"source_key": "radarr", "handoff_id": "handoff-1"}
        conn.execute(
            "UPDATE jobs SET payload_json = ? WHERE id = ?",
            (json.dumps(queued_payload, separators=(",", ":")), job_id),
        )
    client = client_factory(server)
    client.login()

    second = client.post_csrf(ENQUEUE, json={"relative_media_path": "Foreign/film.mkv", "pass_through_unchanged": True})
    assert second.status_code == 200, second.text
    assert second.json()["job_id"] == job_id

    # Only remux-pass rows: a restart lets the periodic scheduler queue a folder scan for the
    # library's watched folder, which is not what this test is about.
    rows = [row for row in all_jobs(client) if row["job_kind"] == REMUX]
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload_json"] or "{}")
    assert payload["pass_through_unchanged"] is True
    assert payload["origin"] == {"source_key": "radarr", "handoff_id": "handoff-1"}
