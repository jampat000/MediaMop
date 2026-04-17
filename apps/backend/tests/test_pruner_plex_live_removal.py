"""Retired Plex live-removal HTTP path and job handler (missing_primary_media_reported)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_TV,
    PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf, seed_admin_user


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_plex_live")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def _plex_sid(session_factory: sessionmaker[Session]) -> int:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="plex",
                display_name="Plex",
                base_url="http://plex.test:32400",
                credentials_secrets={"auth_token": "tok"},
            )
            return int(inst.id)


def test_plex_live_eligibility_is_always_ineligible_with_deprecation_notes(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS", "2")
    sid = _plex_sid(session_factory)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        r = client.get(f"/api/v1/pruner/instances/{sid}/scopes/tv/plex-live-removal-eligibility")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["eligible"] is False
        assert data["apply_feature_enabled"] is True
        assert data["plex_live_feature_enabled"] is True
        assert data["required_confirmation_phrase"] == PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE
        joined = " ".join(data["reasons"])
        assert "retired" in joined.lower() or "deprecated" in joined.lower()
        assert data["live_max_items_cap"] == 2


def test_plex_live_post_rejects_jellyfin_instance(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="JF",
                base_url="http://jf.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/tv/plex-live-removal",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text


def test_plex_live_post_plex_always_422_retired(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
    sid = _plex_sid(session_factory)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/tv/plex-live-removal",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text
        reasons = r.json()["detail"]["reasons"]
        assert any("retired" in x.lower() for x in reasons)


def test_plex_live_handler_raises_retired(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_sid(session_factory)
    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND]
    with pytest.raises(RuntimeError, match="retired"):
        fn(
            PrunerJobWorkContext(
                id=1,
                job_kind=PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND,
                payload_json=json.dumps(
                    {
                        "server_instance_id": sid,
                        "media_scope": MEDIA_SCOPE_TV,
                        "rule_family_id": "missing_primary_media_reported",
                    },
                ),
                lease_owner="pytest",
            ),
        )
