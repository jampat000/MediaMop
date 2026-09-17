"""POST ``/api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue``."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, trusted_browser_origin_headers
from tests.integration_helpers import csrf as fetch_csrf
from weir.core.config import WeirSettings
from weir.core.db import create_db_engine, create_session_factory
from weir.refiner.jobs_model import RefinerJob
from weir.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _put_paths(client: TestClient, *, watched: str | None, output: str) -> None:
    del client
    # The path-settings route was retired with #460; the Movies library is configured directly.
    from weir.refiner.refiner_library_service import resolve_library

    with create_session_factory(create_db_engine(WeirSettings.load()))() as db:
        # The library scope-only work resolves to (first by display order), not the lowest id.
        library = resolve_library(db, media_scope="movie")
        assert library is not None
        library.watched_folder = watched or ""
        library.work_folder = ""
        library.output_folder = output
        db.commit()


def test_watched_folder_scan_enqueue_requires_watched_folder(client_with_admin: TestClient, tmp_path: Path) -> None:
    _login_admin(client_with_admin)
    out = tmp_path / "out_scan_api"
    out.mkdir()
    _put_paths(client_with_admin, watched=None, output=str(out.resolve()))
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue",
        json={"csrf_token": tok},
    )
    assert r.status_code == 400
    assert "watched folder" in r.json()["detail"].lower()


def test_watched_folder_scan_enqueue_ok(client_with_admin: TestClient, tmp_path: Path) -> None:
    _login_admin(client_with_admin)
    w = tmp_path / "w_scan_api"
    w.mkdir()
    out = tmp_path / "out_scan_api2"
    out.mkdir()
    _put_paths(client_with_admin, watched=str(w.resolve()), output=str(out.resolve()))
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue",
        json={"csrf_token": tok, "enqueue_remux_jobs": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_kind"] == REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND


def test_watched_folder_scan_enqueue_defaults_to_processing_files(
    client_with_admin: TestClient, tmp_path: Path
) -> None:
    _login_admin(client_with_admin)
    w = tmp_path / "w_scan_api_default"
    w.mkdir()
    out = tmp_path / "out_scan_api_default"
    out.mkdir()
    _put_paths(client_with_admin, watched=str(w.resolve()), output=str(out.resolve()))
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue",
        json={"csrf_token": tok},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    engine = create_db_engine(WeirSettings.load())
    with create_session_factory(engine)() as db:
        job = db.get(RefinerJob, job_id)
        assert job is not None
        assert '"enqueue_remux_jobs":true' in (job.payload_json or "")
