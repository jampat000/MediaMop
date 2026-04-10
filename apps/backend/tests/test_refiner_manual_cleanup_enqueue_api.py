"""Operator ``POST`` enqueue for Radarr/Sonarr cleanup-drive jobs (dedupe-aware)."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.radarr_failed_import_cleanup_job import (
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_job import (
    SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf

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


def _login_viewer(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_manual_enqueue_radarr_admin_created_then_already_present(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r1 = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/radarr/enqueue",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["enqueue_outcome"] == "created"
    assert b1["dedupe_key"] == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY
    assert "radarr" in b1["job_kind"]

    tok2 = fetch_csrf(client_with_admin)
    r2 = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/radarr/enqueue",
        json={"confirm": True, "csrf_token": tok2},
    )
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["enqueue_outcome"] == "already_present"
    assert b2["job_id"] == b1["job_id"]

    fac = _fac()
    with fac() as db:
        n = db.scalar(select(func.count()).select_from(RefinerJob)) or 0
        assert n == 1


def test_manual_enqueue_sonarr_admin_created_then_already_present(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r1 = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/sonarr/enqueue",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["enqueue_outcome"] == "created"
    assert b1["dedupe_key"] == SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY

    tok2 = fetch_csrf(client_with_admin)
    r2 = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/sonarr/enqueue",
        json={"confirm": True, "csrf_token": tok2},
    )
    assert r2.status_code == 200
    assert r2.json()["enqueue_outcome"] == "already_present"

    fac = _fac()
    with fac() as db:
        n = db.scalar(select(func.count()).select_from(RefinerJob)) or 0
        assert n == 1


def test_manual_enqueue_radarr_radarr_and_sonarr_independent_rows(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r_rad = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/radarr/enqueue",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r_rad.status_code == 200
    tok2 = fetch_csrf(client_with_admin)
    r_son = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/sonarr/enqueue",
        json={"confirm": True, "csrf_token": tok2},
    )
    assert r_son.status_code == 200
    assert r_rad.json()["job_id"] != r_son.json()["job_id"]

    fac = _fac()
    with fac() as db:
        assert (db.scalar(select(func.count()).select_from(RefinerJob)) or 0) == 2


def test_manual_enqueue_radarr_anonymous_401(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/radarr/enqueue",
        json={"confirm": True, "csrf_token": "x"},
    )
    assert r.status_code == 401


def test_manual_enqueue_radarr_viewer_403(client_with_viewer: TestClient) -> None:
    _clear_refiner_jobs()
    _login_viewer(client_with_viewer)
    tok = fetch_csrf(client_with_viewer)
    r = auth_post(
        client_with_viewer,
        "/api/v1/refiner/cleanup-drive/radarr/enqueue",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r.status_code == 403


def test_manual_enqueue_radarr_rejects_invalid_csrf(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/cleanup-drive/radarr/enqueue",
        json={"confirm": True, "csrf_token": "not-valid"},
    )
    assert r.status_code == 400
