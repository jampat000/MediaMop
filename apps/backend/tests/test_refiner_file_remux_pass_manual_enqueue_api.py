"""Operator POST for manual Refiner file remux pass enqueue (``refiner_jobs`` only)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select
from starlette.testclient import TestClient

import weir.platform.activity.models  # noqa: F401
import weir.platform.auth.models  # noqa: F401
import weir.refiner.jobs_model  # noqa: F401
from tests.integration_helpers import auth_post, trusted_browser_origin_headers
from tests.integration_helpers import csrf as fetch_csrf
from weir.core.config import WeirSettings
from weir.core.db import create_db_engine, create_session_factory
from weir.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from weir.refiner.jobs_model import RefinerJob


def _fac():
    settings = WeirSettings.load()
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
    del client
    # The path-settings route was retired with #460; the Movies library is configured directly.
    from weir.refiner.refiner_library_service import resolve_library

    with create_session_factory(create_db_engine(WeirSettings.load()))() as db:
        # The library scope-only work resolves to (first by display order), not the lowest id.
        library = resolve_library(db, media_scope="movie")
        assert library is not None
        library.watched_folder = watched or ""
        library.work_folder = work or ""
        library.output_folder = output
        db.commit()


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


def test_pass_through_converts_an_existing_pending_job_instead_of_duplicating_it(
    client_with_admin: TestClient,
    tmp_path: Path,
) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    watch = tmp_path / "pass_watch"
    watch.mkdir()
    out = tmp_path / "pass_out"
    out.mkdir()
    _put_refiner_path_settings(
        client_with_admin,
        watched=str(watch.resolve()),
        output=str(out.resolve()),
    )

    first = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        json={
            "csrf_token": fetch_csrf(client_with_admin),
            "relative_media_path": "Foreign/film.mkv",
        },
    )
    assert first.status_code == 200, first.text
    factory = _fac()
    with factory() as db:
        queued = db.get(RefinerJob, first.json()["job_id"])
        assert queued is not None
        queued_payload = json.loads(queued.payload_json or "{}")
        queued_payload["origin"] = {"source_key": "radarr", "handoff_id": "handoff-1"}
        queued.payload_json = json.dumps(queued_payload, separators=(",", ":"))
        db.commit()
    second = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        json={
            "csrf_token": fetch_csrf(client_with_admin),
            "relative_media_path": "Foreign/film.mkv",
            "pass_through_unchanged": True,
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["job_id"] == first.json()["job_id"]

    with factory() as db:
        rows = list(db.scalars(select(RefinerJob)).all())
        assert len(rows) == 1
        payload = json.loads(rows[0].payload_json or "{}")
        assert payload["pass_through_unchanged"] is True
        assert payload["origin"] == {"source_key": "radarr", "handoff_id": "handoff-1"}
