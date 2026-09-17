"""Contract port of the retired Python backend's tests/test_refiner_watched_folder_remux_scan_dispatch_manual_enqueue_api.py."""

from __future__ import annotations

from pathlib import Path

from tests.contract.jobs._helpers import job_by_id, set_movie_folders
from tests.contract.support.client import API, WeirClient

SCAN = "refiner.watched_folder.remux_scan_dispatch.v1"
ENQUEUE = f"{API}/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue"


def test_watched_folder_scan_enqueue_requires_watched_folder(admin: WeirClient, tmp_path: Path) -> None:
    out = tmp_path / "out_scan_api"
    out.mkdir()
    set_movie_folders(admin, watched=None, output=str(out.resolve()))
    r = admin.post_csrf(ENQUEUE, json={})
    assert r.status_code == 400
    assert "watched folder" in r.json()["detail"].lower()


def test_watched_folder_scan_enqueue_ok(admin: WeirClient, tmp_path: Path) -> None:
    w = tmp_path / "w_scan_api"
    w.mkdir()
    out = tmp_path / "out_scan_api2"
    out.mkdir()
    set_movie_folders(admin, watched=str(w.resolve()), output=str(out.resolve()))
    r = admin.post_csrf(ENQUEUE, json={"enqueue_remux_jobs": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_kind"] == SCAN


def test_watched_folder_scan_enqueue_defaults_to_processing_files(admin: WeirClient, tmp_path: Path) -> None:
    w = tmp_path / "w_scan_api_default"
    w.mkdir()
    out = tmp_path / "out_scan_api_default"
    out.mkdir()
    set_movie_folders(admin, watched=str(w.resolve()), output=str(out.resolve()))
    r = admin.post_csrf(ENQUEUE, json={})
    assert r.status_code == 200, r.text
    job = job_by_id(admin, r.json()["job_id"])
    assert '"enqueue_remux_jobs":true' in (job["payload_json"] or "")
