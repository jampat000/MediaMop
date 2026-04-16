"""GET/PUT ``/api/v1/refiner/path-settings``."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_path_settings_service import (
    ensure_refiner_path_settings_row,
    resolve_refiner_path_runtime_for_remux,
    resolved_default_refiner_tv_work_folder,
    resolved_default_refiner_work_folder,
)

from tests.integration_helpers import auth_post, csrf as fetch_csrf, trusted_browser_origin_headers


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_refiner_path_settings_get_viewer_ok(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    r = client_with_viewer.get("/api/v1/refiner/path-settings")
    assert r.status_code == 200, r.text


def test_refiner_path_settings_get_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/path-settings")
    assert r.status_code == 401


def test_refiner_path_settings_get_shape(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/path-settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "refiner_watched_folder" in body
    assert "refiner_work_folder" in body
    assert "refiner_output_folder" in body
    assert "resolved_default_work_folder" in body
    assert "effective_work_folder" in body
    assert "refiner_tv_watched_folder" in body
    assert "refiner_tv_work_folder" in body
    assert "refiner_tv_output_folder" in body
    assert "resolved_default_tv_work_folder" in body
    assert "effective_tv_work_folder" in body
    assert body["movie_watched_folder_check_interval_seconds"] >= 10
    assert body["tv_watched_folder_check_interval_seconds"] >= 10
    assert "updated_at" in body
    settings = MediaMopSettings.load()
    assert body["resolved_default_work_folder"] == resolved_default_refiner_work_folder(
        mediamop_home=settings.mediamop_home,
    )
    assert body["resolved_default_tv_work_folder"] == resolved_default_refiner_tv_work_folder(
        mediamop_home=settings.mediamop_home,
    )


def test_refiner_path_settings_put_blank_work_persists_default(client_with_admin: TestClient, tmp_path: Path) -> None:
    _login_admin(client_with_admin)
    w = tmp_path / "watch"
    w.mkdir()
    o = tmp_path / "out"
    o.mkdir()
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/path-settings",
        json={
            "csrf_token": tok,
            "refiner_watched_folder": str(w.resolve()),
            "refiner_work_folder": None,
            "refiner_output_folder": str(o.resolve()),
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    settings = MediaMopSettings.load()
    expected_work = resolved_default_refiner_work_folder(mediamop_home=settings.mediamop_home)
    assert out["refiner_work_folder"] == expected_work
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = db.scalars(select(RefinerPathSettingsRow).where(RefinerPathSettingsRow.id == 1)).one()
        assert row.refiner_work_folder == expected_work


def test_refiner_path_settings_put_save_without_watched_folder_succeeds(
    client_with_admin: TestClient,
    tmp_path: Path,
) -> None:
    """Watched folder is optional on save; output (and resolved work) are still validated."""
    _login_admin(client_with_admin)
    o = tmp_path / "out_no_watch"
    o.mkdir()
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/path-settings",
        json={
            "csrf_token": tok,
            "refiner_watched_folder": None,
            "refiner_work_folder": None,
            "refiner_output_folder": str(o.resolve()),
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refiner_watched_folder"] is None
    settings = MediaMopSettings.load()
    assert body["refiner_work_folder"] == resolved_default_refiner_work_folder(mediamop_home=settings.mediamop_home)


def test_resolve_refiner_path_runtime_fails_without_watched_folder(client_with_admin: TestClient) -> None:
    """Manual remux (dry or live) requires a saved watched folder — distinct from optional-at-save."""
    _login_admin(client_with_admin)
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    prev: str | None = None
    with fac() as db:
        row = ensure_refiner_path_settings_row(db)
        prev = row.refiner_watched_folder
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(refiner_watched_folder=None),
        )
        db.commit()
    try:
        with fac() as db:
            rt, err = resolve_refiner_path_runtime_for_remux(db, settings, dry_run=True)
        assert rt is None
        assert err is not None
        assert "watched folder is not set" in err.lower()
        assert "save" in err.lower() and "enqueue" in err.lower()
    finally:
        with fac() as db:
            db.execute(
                update(RefinerPathSettingsRow)
                .where(RefinerPathSettingsRow.id == 1)
                .values(refiner_watched_folder=prev),
            )
            db.commit()


def test_refiner_path_settings_put_overlap_400(client_with_admin: TestClient, tmp_path: Path) -> None:
    _login_admin(client_with_admin)
    base = tmp_path / "b"
    w = base / "w"
    o = base / "w" / "nested" / "o"
    w.mkdir(parents=True)
    o.mkdir(parents=True)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/path-settings",
        json={
            "csrf_token": tok,
            "refiner_watched_folder": str(w.resolve()),
            "refiner_work_folder": None,
            "refiner_output_folder": str(o.resolve()),
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert "watched" in r.json()["detail"].lower()


def test_refiner_path_settings_put_viewer_403(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    tok2 = fetch_csrf(client_with_viewer)
    r = client_with_viewer.put(
        "/api/v1/refiner/path-settings",
        json={
            "csrf_token": tok2,
            "refiner_watched_folder": None,
            "refiner_work_folder": None,
            "refiner_output_folder": str(Path(".").resolve()),
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 403
