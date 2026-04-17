"""Pruner ``watched_movies_reported`` — Jellyfin/Emby movie items only (preview + snapshot apply)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_apply_eligibility import compute_apply_eligibility
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_media_library import list_watched_movie_candidates, preview_payload_json
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf, seed_admin_user


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_watched_movies")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def _movie_item(mid: str, played: bool = True) -> dict:
    return {
        "Id": mid,
        "Name": "Test Film",
        "ProductionYear": 2020,
        "UserData": {"Played": played, "PlayCount": 1 if played else 0},
    }


def test_preview_payload_jellyfin_watched_movies_lists_watched_movies() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 1}
        return (
            200,
            {"Items": [_movie_item("m-1")], "TotalRecordCount": 1},
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_WATCHED_MOVIES_REPORTED,
            never_played_min_age_days=None,
        )
    assert out == "success"
    assert detail == ""
    assert not trunc
    assert len(cands) == 1
    assert cands[0]["item_id"] == "m-1"
    assert cands[0]["granularity"] == "movie_item"


def test_preview_payload_plex_watched_movies_unsupported() -> None:
    out, detail, cands, trunc = preview_payload_json(
        provider="plex",
        base_url="http://plex:32400",
        media_scope=MEDIA_SCOPE_MOVIES,
        secrets={"auth_token": "t"},
        max_items=50,
        rule_family_id=RULE_FAMILY_WATCHED_MOVIES_REPORTED,
        never_played_min_age_days=None,
    )
    assert out == "unsupported"
    assert "plex" in detail.lower() and "watched" in detail.lower()
    assert cands == [] and trunc is False


def test_preview_payload_tv_scope_watched_movies_unsupported() -> None:
    out, detail, cands, trunc = preview_payload_json(
        provider="jellyfin",
        base_url="http://jf.test",
        media_scope=MEDIA_SCOPE_TV,
        secrets={"api_key": "k"},
        max_items=50,
        rule_family_id=RULE_FAMILY_WATCHED_MOVIES_REPORTED,
        never_played_min_age_days=None,
    )
    assert out == "unsupported"
    assert "movies tab" in detail.lower()
    assert cands == []


def test_list_watched_movie_candidates_rejects_tv_scope() -> None:
    with pytest.raises(ValueError, match="watched_movies_reported requires media_scope"):
        list_watched_movie_candidates(
            base_url="http://jf.test",
            api_key="k",
            media_scope=MEDIA_SCOPE_TV,
            max_items=5,
        )


def test_apply_jellyfin_watched_movies_skips_404(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.jellyfin_delete_library_item",
        lambda **kw: (404, None),
    )
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="JF Movies",
                base_url="http://jf-movies.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_MOVIES,
                rule_family_id=RULE_FAMILY_WATCHED_MOVIES_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json='[{"item_id":"gone-m"}]',
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="apply-watched-movies-jf",
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND](
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
            payload_json=json.dumps(
                {
                    "preview_run_uuid": run_uuid,
                    "server_instance_id": sid,
                    "media_scope": MEDIA_SCOPE_MOVIES,
                    "rule_family_id": RULE_FAMILY_WATCHED_MOVIES_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc())).first()
        assert evt is not None
        d = json.loads(evt.detail or "{}")
        assert d.get("skipped") == 1
        assert d.get("removed") == 0


def test_compute_apply_eligibility_watched_movies_requires_toggle(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="JF",
                base_url="http://jf-elig.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            movies = s.scalars(
                select(PrunerScopeSettings).where(
                    PrunerScopeSettings.server_instance_id == sid,
                    PrunerScopeSettings.media_scope == MEDIA_SCOPE_MOVIES,
                ),
            ).one()
            movies.watched_movies_reported_enabled = False
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_MOVIES,
                rule_family_id=RULE_FAMILY_WATCHED_MOVIES_REPORTED,
                pruner_job_id=None,
                candidate_count=2,
                candidates_json="[]",
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    settings2 = MediaMopSettings.load()
    with session_factory() as s:
        out = compute_apply_eligibility(
            s,
            settings2,
            instance_id=sid,
            media_scope=MEDIA_SCOPE_MOVIES,
            preview_run_uuid=run_uuid,
        )
    assert out.eligible is False
    assert any("watched movies rule toggle" in r for r in out.reasons)


@pytest.fixture
def client_with_admin(_iso) -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_post_preview_watched_movies_rejects_tv_tab(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "WatchedMoviesTab",
            "base_url": "http://wm-tab.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])
    tok2 = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/previews",
        json={
            "media_scope": "tv",
            "rule_family_id": RULE_FAMILY_WATCHED_MOVIES_REPORTED,
            "csrf_token": tok2,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text
