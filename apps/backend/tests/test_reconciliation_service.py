"""Filesystem/database reconciliation reporting and safe repairs."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete, update
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.platform.reconciliation.service import build_reconciliation_report, repair_reconciliation_issue
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_reconciliation_detects_and_repairs_missing_subtitle_reference(tmp_path: Path) -> None:
    media = tmp_path / "movie.mkv"
    media.write_bytes(b"media")
    missing_subtitle = tmp_path / "movie.en.srt"
    fac = _fac()
    with fac() as db:
        db.execute(delete(SubberSubtitleState))
        db.add(
            SubberSubtitleState(
                media_scope="movies",
                file_path=str(media),
                language_code="en",
                status="found",
                subtitle_path=str(missing_subtitle),
            )
        )
        db.commit()

    try:
        with fac() as db:
            report = build_reconciliation_report(db)
            issue = next(item for item in report["issues"] if item["kind"] == "db_subtitle_file_missing")
            result = repair_reconciliation_issue(
                db,
                action=str(issue["repair_action"]),
                db_id=int(issue["db_id"]),
            )
            db.commit()
        assert result["applied"] is True

        with fac() as db:
            row = db.query(SubberSubtitleState).one()
            assert row.subtitle_path is None
            assert row.status == "missing"
    finally:
        with fac() as db:
            db.execute(delete(SubberSubtitleState))
            db.commit()


def test_reconciliation_temp_artifact_repair_requires_confirmation(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    artifact = work / ".movie.mkv.partial"
    artifact.write_bytes(b"partial")
    fac = _fac()
    with fac() as db:
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(refiner_work_folder=str(work), refiner_tv_work_folder=None)
        )
        db.commit()

    try:
        with fac() as db:
            report = build_reconciliation_report(db)
            issue = next(item for item in report["issues"] if item["kind"] == "partial_temp_artifact")
            with pytest.raises(ValueError, match="confirm=true"):
                repair_reconciliation_issue(
                    db,
                    action=str(issue["repair_action"]),
                    path=str(issue["path"]),
                    confirm=False,
                )
            result = repair_reconciliation_issue(
                db,
                action=str(issue["repair_action"]),
                path=str(issue["path"]),
                confirm=True,
            )
            db.commit()
        assert result["applied"] is True
        assert not artifact.exists()
    finally:
        with fac() as db:
            db.execute(
                update(RefinerPathSettingsRow)
                .where(RefinerPathSettingsRow.id == 1)
                .values(refiner_work_folder=None, refiner_tv_work_folder=None)
            )
            db.commit()


def test_reconciliation_report_rejects_viewer(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    assert client_with_viewer.get("/api/v1/system/reconciliation").status_code == 403


def test_reconciliation_report_allows_admin(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/system/reconciliation")
    assert r.status_code == 200, r.text
    assert "issues" in r.json()
