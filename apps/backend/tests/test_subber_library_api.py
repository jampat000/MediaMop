"""HTTP: Subber library listing and manual search triggers."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES, SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES
from mediamop.modules.subber.subber_jobs_model import SubberJob
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, csrf, seed_admin_user, seed_viewer_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _isolated_subber_library_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_subber_library_api")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_viewer() -> TestClient:
    seed_viewer_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _login_admin(c: TestClient) -> None:
    tok = csrf(c)
    r = auth_post(
        c,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _login_viewer(c: TestClient) -> None:
    tok = csrf(c)
    r = auth_post(
        c,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _seed_tv_state(settings) -> int:
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = SubberSubtitleState(
            media_scope="tv",
            file_path="/t/p.mkv",
            language_code="en",
            status="missing",
            show_title="Alpha",
            season_number=1,
            episode_number=1,
            episode_title="Pilot",
        )
        db.add(row)
        db.commit()
        return int(row.id)


def _seed_movies_state(settings) -> int:
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = SubberSubtitleState(
            media_scope="movies",
            file_path="/m/x.mkv",
            language_code="en",
            status="missing",
            movie_title="Test Film",
        )
        db.add(row)
        db.commit()
        return int(row.id)


def _seed_tv_status_pair(settings) -> None:
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        db.add(
            SubberSubtitleState(
                media_scope="tv",
                file_path="/t/miss.mkv",
                language_code="en",
                status="missing",
                show_title="StatusShow",
                season_number=1,
                episode_number=1,
                episode_title="A",
            ),
        )
        db.add(
            SubberSubtitleState(
                media_scope="tv",
                file_path="/t/found.mkv",
                language_code="en",
                status="found",
                show_title="StatusShow",
                season_number=1,
                episode_number=2,
                episode_title="B",
                subtitle_path="/tmp/fake.srt",
            ),
        )
        db.commit()


def _seed_tv_search_row(settings) -> None:
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        db.add(
            SubberSubtitleState(
                media_scope="tv",
                file_path="/t/bb.mkv",
                language_code="en",
                status="missing",
                show_title="Breaking Bad",
                season_number=1,
                episode_number=1,
                episode_title="Pilot",
            ),
        )
        db.commit()


def test_get_library_tv_requires_auth(client_admin: TestClient) -> None:
    r = client_admin.get("/api/v1/subber/library/tv")
    assert r.status_code == 401


def test_get_library_tv_ok(client_admin: TestClient) -> None:
    sid = _seed_tv_state(client_admin.app.state.settings)
    _ = sid
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/library/tv")
    assert r.status_code == 200
    data = r.json()
    assert "shows" in data
    assert len(data["shows"]) >= 1


def test_search_now_requires_operator(client_viewer: TestClient) -> None:
    _login_viewer(client_viewer)
    tok = csrf(client_viewer)
    r = client_viewer.post(
        "/api/v1/subber/library/1/search-now",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_search_now_admin_queues_job(client_admin: TestClient) -> None:
    sid = _seed_tv_state(client_admin.app.state.settings)
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        f"/api/v1/subber/library/{sid}/search-now",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    fac = create_session_factory(create_db_engine(client_admin.app.state.settings))
    with fac() as db:
        j = db.scalars(select(SubberJob).order_by(SubberJob.id.desc())).first()
        assert j is not None
        assert "subtitle_search" in j.job_kind


def test_search_all_missing_requires_operator(client_viewer: TestClient) -> None:
    _login_viewer(client_viewer)
    tok = csrf(client_viewer)
    r = client_viewer.post(
        "/api/v1/subber/library/search-all-missing/tv",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_get_library_movies_ok(client_admin: TestClient) -> None:
    _seed_movies_state(client_admin.app.state.settings)
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/library/movies")
    assert r.status_code == 200
    data = r.json()
    assert "movies" in data
    assert len(data["movies"]) >= 1


def test_get_library_movies_requires_auth(client_admin: TestClient) -> None:
    r = client_admin.get("/api/v1/subber/library/movies")
    assert r.status_code == 401


def test_get_library_tv_status_filter_missing(client_admin: TestClient) -> None:
    _seed_tv_status_pair(client_admin.app.state.settings)
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/library/tv", params={"status": "missing"})
    assert r.status_code == 200
    shows = r.json().get("shows") or []
    sh = next(s for s in shows if s.get("show_title") == "StatusShow")
    paths: list[str] = []
    for sea in sh.get("seasons") or []:
        for ep in sea.get("episodes") or []:
            paths.append(str(ep.get("file_path")))
    assert paths == ["/t/miss.mkv"]


def test_get_library_tv_status_filter_found(client_admin: TestClient) -> None:
    """Library uses ``status=complete`` for episodes where all preferred languages are found."""
    _seed_tv_status_pair(client_admin.app.state.settings)
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/library/tv", params={"status": "complete"})
    assert r.status_code == 200
    shows = r.json().get("shows") or []
    sh = next(s for s in shows if s.get("show_title") == "StatusShow")
    paths: list[str] = []
    for sea in sh.get("seasons") or []:
        for ep in sea.get("episodes") or []:
            paths.append(str(ep.get("file_path")))
    assert paths == ["/t/found.mkv"]


def test_get_library_tv_search_filter(client_admin: TestClient) -> None:
    _seed_tv_search_row(client_admin.app.state.settings)
    _login_admin(client_admin)
    r_ok = client_admin.get("/api/v1/subber/library/tv", params={"search": "breaking"})
    assert r_ok.status_code == 200
    titles = {s.get("show_title") for s in (r_ok.json().get("shows") or [])}
    assert "Breaking Bad" in titles
    r_empty = client_admin.get("/api/v1/subber/library/tv", params={"search": "xyz"})
    assert r_empty.status_code == 200
    assert len(r_empty.json().get("shows") or []) == 0


def test_search_all_missing_movies_queues_job(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/subber/library/search-all-missing/movies",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    fac = create_session_factory(create_db_engine(client_admin.app.state.settings))
    with fac() as db:
        j = db.scalars(select(SubberJob).order_by(SubberJob.id.desc())).first()
        assert j is not None
        assert j.job_kind == SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES


def test_search_now_movies_queues_correct_job(client_admin: TestClient) -> None:
    sid = _seed_movies_state(client_admin.app.state.settings)
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        f"/api/v1/subber/library/{sid}/search-now",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    fac = create_session_factory(create_db_engine(client_admin.app.state.settings))
    with fac() as db:
        j = db.scalars(select(SubberJob).order_by(SubberJob.id.desc())).first()
        assert j is not None
        assert j.job_kind == SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES


def test_search_now_unknown_state_404(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/subber/library/99999/search-now",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 404
