"""Operator POST for manual Refiner file remux pass enqueue (``refiner_jobs`` only)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from tests.integration_helpers import auth_post, csrf as fetch_csrf, trusted_browser_origin_headers

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _clear_refiner_jobs() -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _put_refiner_path_settings(
    client: TestClient,
    *,
    watched: str | None,
    output: str,
    work: str | None = None,
) -> None:
    tok = fetch_csrf(client)
    r = client.put(
        "/api/v1/refiner/path-settings",
        json={
            "csrf_token": tok,
            "refiner_watched_folder": watched,
            "refiner_work_folder": work,
            "refiner_output_folder": output,
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text


def test_refiner_file_remux_pass_enqueue_writes_live_payload(client_with_admin: TestClient, tmp_path: Path) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    watch = tmp_path / "remux_watch"
    watch.mkdir()
    out = tmp_path / "remux_out"
    out.mkdir()
    _put_refiner_path_settings(
        client_with_admin,
        watched=str(watch.resolve()),
        output=str(out.resolve()),
    )
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        json={
            "csrf_token": tok,
            "relative_media_path": "movies/sample.mkv",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["job_kind"] == REFINER_FILE_REMUX_PASS_JOB_KIND
    fac = _fac()
    with fac() as db:
        row = db.scalars(select(RefinerJob).where(RefinerJob.id == body["job_id"])).first()
        assert row is not None
        assert row.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND
        assert '"dry_run"' not in (row.payload_json or "")
        assert '"relative_media_path":"movies/sample.mkv"' in (row.payload_json or "")


def test_refiner_file_remux_pass_enqueue_rejects_missing_watched_folder(
    client_with_admin: TestClient,
    tmp_path: Path,
) -> None:
    _login_admin(client_with_admin)
    out = tmp_path / "enqueue_out_only"
    out.mkdir()
    _put_refiner_path_settings(
        client_with_admin,
        watched=None,
        output=str(out.resolve()),
    )
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        json={
            "csrf_token": tok,
            "relative_media_path": "movies/sample.mkv",
        },
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "")
    assert isinstance(detail, str)
    assert "watched folder" in detail.lower()
    assert "path settings" in detail.lower()
