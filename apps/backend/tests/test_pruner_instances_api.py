"""HTTP integration: ``/api/v1/pruner/instances`` (Phase 2A instance-primary surface)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
)
from mediamop.modules.pruner.pruner_job_kinds import (
    PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
    PRUNER_SERVER_CONNECTION_TEST_JOB_KIND,
)
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob
from mediamop.modules.pruner.pruner_instances_service import get_scope_settings
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import (
    auth_patch,
    auth_post,
    csrf as fetch_csrf,
    seed_admin_user,
    seed_viewer_user,
)

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture(autouse=True)
def _isolated_pruner_instances_api_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_api")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)

    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture
def client_with_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_viewer() -> TestClient:
    seed_viewer_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


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


def _login_viewer(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_get_pruner_instances_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/pruner/instances")
    assert r.status_code == 401


def test_post_pruner_instances_requires_operator(client_with_viewer: TestClient) -> None:
    _login_viewer(client_with_viewer)
    tok = fetch_csrf(client_with_viewer)
    r = auth_post(
        client_with_viewer,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "X",
            "base_url": "http://x.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 403, r.text


def test_post_pruner_instances_creates_row_seeds_scopes_and_hides_secrets(client_with_admin: TestClient) -> None:
    """``POST /api/v1/pruner/instances`` — instance-primary JSON; no credential material in response."""

    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    secret_key = "super-secret-api-key-99"
    r = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "Home Emby",
            "base_url": "http://emby-instance.test",
            "credentials": {"api_key": secret_key},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_name"] == "Home Emby"
    assert body["provider"] == "emby"
    assert body["base_url"] == "http://emby-instance.test"
    assert "id" in body and isinstance(body["id"], int)
    assert "scopes" in body and isinstance(body["scopes"], list)
    assert len(body["scopes"]) == 2
    scopes_sorted = sorted(body["scopes"], key=lambda s: s["media_scope"])
    assert [s["media_scope"] for s in scopes_sorted] == [MEDIA_SCOPE_MOVIES, MEDIA_SCOPE_TV]
    for s in body["scopes"]:
        assert s["preview_max_items"] == 500
        assert s["missing_primary_media_reported_enabled"] is True
        assert s["never_played_stale_reported_enabled"] is False
        assert s["never_played_min_age_days"] == 90
        assert s["watched_tv_reported_enabled"] is False
        assert s["watched_movies_reported_enabled"] is False
        assert s["watched_movie_low_rating_reported_enabled"] is False
        assert s["watched_movie_low_rating_max_community_rating"] == 4.0
        assert s["unwatched_movie_stale_reported_enabled"] is False
        assert s["unwatched_movie_stale_min_age_days"] == 90
        assert s["preview_include_genres"] == []
        assert s["preview_include_people"] == []

    raw = json.dumps(body)
    assert secret_key not in raw
    assert "api_key" not in raw
    assert "credentials" not in raw
    assert "ciphertext" not in raw.lower()

    iid = int(body["id"])
    fac = _fac()
    with fac() as db:
        inst = db.scalars(select(PrunerServerInstance).where(PrunerServerInstance.id == iid)).one()
        assert "secret" not in inst.credentials_ciphertext
        rows = db.scalars(
            select(PrunerScopeSettings).where(PrunerScopeSettings.server_instance_id == iid),
        ).all()
        assert len(rows) == 2
        assert {r.media_scope for r in rows} == {MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES}


def test_post_pruner_preview_enqueue_payload_is_per_instance_and_scope(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "JF-A",
            "base_url": "http://jf-a.test",
            "credentials": {"api_key": "a"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid_a = int(r0.json()["id"])
    tok = fetch_csrf(client_with_admin)
    r1 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "JF-B",
            "base_url": "http://jf-b.test",
            "credentials": {"api_key": "b"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r1.status_code == 200, r1.text
    iid_b = int(r1.json()["id"])

    tok = fetch_csrf(client_with_admin)
    rp = auth_post(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid_a}/previews",
        json={"media_scope": "tv", "csrf_token": tok},
        headers={"Content-Type": "application/json"},
    )
    assert rp.status_code == 200, rp.text
    assert "pruner_job_id" in rp.json()

    tok = fetch_csrf(client_with_admin)
    rp2 = auth_post(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid_b}/previews",
        json={"media_scope": "movies", "csrf_token": tok},
        headers={"Content-Type": "application/json"},
    )
    assert rp2.status_code == 200, rp2.text

    fac = _fac()
    with fac() as db:
        jobs = db.scalars(select(PrunerJob).order_by(PrunerJob.id.asc())).all()
        preview_jobs = [j for j in jobs if j.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND]
        assert len(preview_jobs) == 2
        p0 = json.loads(preview_jobs[0].payload_json or "{}")
        p1 = json.loads(preview_jobs[1].payload_json or "{}")
        by_id = {p["server_instance_id"]: p for p in (p0, p1)}
        assert by_id[iid_a]["media_scope"] == "tv"
        assert by_id[iid_b]["media_scope"] == "movies"
        assert set(by_id[iid_a]) == {"server_instance_id", "media_scope", "rule_family_id"}
        assert by_id[iid_a]["rule_family_id"] == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
        assert by_id[iid_b]["rule_family_id"] == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED


def test_post_pruner_preview_never_played_rule_in_job_payload(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "JF-never",
            "base_url": "http://jf-never.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])
    tok = fetch_csrf(client_with_admin)
    rp = auth_post(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/previews",
        json={
            "media_scope": MEDIA_SCOPE_TV,
            "csrf_token": tok,
            "rule_family_id": RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
        },
        headers={"Content-Type": "application/json"},
    )
    assert rp.status_code == 200, rp.text
    fac = _fac()
    with fac() as db:
        job = db.scalars(
            select(PrunerJob).where(PrunerJob.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND),
        ).one()
        payload = json.loads(job.payload_json or "{}")
        assert payload["server_instance_id"] == iid
        assert payload["media_scope"] == MEDIA_SCOPE_TV
        assert payload["rule_family_id"] == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED


def test_post_pruner_connection_test_enqueue_job_kind_and_instance_payload(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "E-conn",
            "base_url": "http://e-conn.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])

    tok = fetch_csrf(client_with_admin)
    rc = auth_post(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/connection-test",
        json={"csrf_token": tok},
        headers={"Content-Type": "application/json"},
    )
    assert rc.status_code == 200, rc.text

    fac = _fac()
    with fac() as db:
        job = db.scalars(
            select(PrunerJob).where(PrunerJob.job_kind == PRUNER_SERVER_CONNECTION_TEST_JOB_KIND),
        ).one()
        assert job.job_kind == PRUNER_SERVER_CONNECTION_TEST_JOB_KIND
        payload = json.loads(job.payload_json or "{}")
        assert payload == {"server_instance_id": iid}
        assert "media_scope" not in payload


def test_get_pruner_instances_lists_two_emby_without_shared_state(client_with_admin: TestClient) -> None:
    """Two same-provider instances remain distinct rows (no collapsed global server)."""

    _login_admin(client_with_admin)
    for name, base in (("Emby-1", "http://emby-1.test"), ("Emby-2", "http://emby-2.test")):
        tok = fetch_csrf(client_with_admin)
        r = auth_post(
            client_with_admin,
            "/api/v1/pruner/instances",
            json={
                "provider": "emby",
                "display_name": name,
                "base_url": base,
                "credentials": {"api_key": f"key-{name}"},
                "csrf_token": tok,
            },
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text

    rlist = client_with_admin.get("/api/v1/pruner/instances")
    assert rlist.status_code == 200, rlist.text
    arr = rlist.json()
    assert len(arr) == 2
    bases = {x["base_url"] for x in arr}
    assert bases == {"http://emby-1.test", "http://emby-2.test"}
    for x in arr:
        assert len(x["scopes"]) == 2
        assert x["last_connection_test_detail"] is None
        for s in x["scopes"]:
            assert s["last_preview_outcome"] is None
            assert s["last_preview_run_uuid"] is None


def test_get_pruner_preview_runs_list_scoped_and_omits_candidates_json(client_with_admin: TestClient) -> None:
    """``GET …/preview-runs`` — per-instance history; optional ``media_scope``; no candidate payloads in list."""

    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "Preview-List",
            "base_url": "http://preview-list.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])
    uid_tv = str(uuid.uuid4())
    uid_movies = str(uuid.uuid4())
    fac = _fac()
    with fac() as db:
        insert_preview_run(
            db,
            preview_run_uuid=uid_tv,
            server_instance_id=iid,
            media_scope=MEDIA_SCOPE_TV,
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            pruner_job_id=None,
            candidate_count=2,
            candidates_json='[{"x":1}]',
            truncated=False,
            outcome="ok",
            unsupported_detail=None,
            error_message=None,
        )
        insert_preview_run(
            db,
            preview_run_uuid=uid_movies,
            server_instance_id=iid,
            media_scope=MEDIA_SCOPE_MOVIES,
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            pruner_job_id=None,
            candidate_count=0,
            candidates_json="[]",
            truncated=False,
            outcome="unsupported",
            unsupported_detail="plex only",
            error_message=None,
        )
        db.commit()

    r_tv = client_with_admin.get(f"/api/v1/pruner/instances/{iid}/preview-runs?media_scope=tv&limit=10")
    assert r_tv.status_code == 200, r_tv.text
    tv_rows = r_tv.json()
    assert len(tv_rows) == 1
    assert tv_rows[0]["preview_run_id"] == uid_tv
    assert tv_rows[0]["media_scope"] == MEDIA_SCOPE_TV
    assert tv_rows[0]["candidate_count"] == 2
    assert "candidates_json" not in tv_rows[0]

    r_all = client_with_admin.get(f"/api/v1/pruner/instances/{iid}/preview-runs?limit=10")
    assert r_all.status_code == 200, r_all.text
    all_rows = r_all.json()
    assert len(all_rows) == 2
    assert all_rows[0]["preview_run_id"] == uid_movies
    assert all_rows[1]["preview_run_id"] == uid_tv

    r_bad = client_with_admin.get(f"/api/v1/pruner/instances/{iid}/preview-runs?media_scope=radio")
    assert r_bad.status_code == 422

    r_404 = client_with_admin.get("/api/v1/pruner/instances/99999/preview-runs")
    assert r_404.status_code == 404


def test_post_pruner_preview_does_not_touch_last_scheduled_preview_enqueued_at(
    client_with_admin: TestClient,
) -> None:
    """Manual enqueue must not overwrite scheduler-owned ``last_scheduled_preview_enqueued_at``."""

    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "Sched-Sticky",
            "base_url": "http://sched-sticky.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])
    t0 = datetime(2026, 4, 10, 8, 0, 0, tzinfo=timezone.utc)
    fac = _fac()
    with fac() as db:
        sc = get_scope_settings(db, server_instance_id=iid, media_scope=MEDIA_SCOPE_TV)
        assert sc is not None
        sc.scheduled_preview_enabled = True
        sc.last_scheduled_preview_enqueued_at = t0
        db.commit()

    tok = fetch_csrf(client_with_admin)
    rp = auth_post(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/previews",
        json={"media_scope": MEDIA_SCOPE_TV, "csrf_token": tok},
        headers={"Content-Type": "application/json"},
    )
    assert rp.status_code == 200, rp.text

    with fac() as db:
        sc2 = get_scope_settings(db, server_instance_id=iid, media_scope=MEDIA_SCOPE_TV)
        assert sc2 is not None
        last = sc2.last_scheduled_preview_enqueued_at
        assert last is not None
        last_utc = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        assert last_utc == t0


def test_patch_pruner_scope_scheduled_fields_are_per_scope(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "Scope-Sched",
            "base_url": "http://scope-sched.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])

    tok = fetch_csrf(client_with_admin)
    r_tv = auth_patch(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/scopes/tv",
        json={
            "scheduled_preview_enabled": True,
            "scheduled_preview_interval_seconds": 120,
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r_tv.status_code == 200, r_tv.text
    tv_body = r_tv.json()
    assert tv_body["scheduled_preview_enabled"] is True
    assert tv_body["scheduled_preview_interval_seconds"] == 120

    tok = fetch_csrf(client_with_admin)
    r_m = auth_patch(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/scopes/movies",
        json={
            "scheduled_preview_enabled": True,
            "scheduled_preview_interval_seconds": 600,
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r_m.status_code == 200, r_m.text
    assert r_m.json()["scheduled_preview_interval_seconds"] == 600

    r_get_tv = client_with_admin.get(f"/api/v1/pruner/instances/{iid}/scopes/tv")
    assert r_get_tv.status_code == 200, r_get_tv.text
    assert r_get_tv.json()["scheduled_preview_interval_seconds"] == 120
