"""Plex-only live removal path (no preview snapshot dependency)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
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
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf, seed_admin_user


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_plex_live")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


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


def test_plex_live_eligibility_requires_flags(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "0")
    sid = _plex_sid(session_factory)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        r = client.get(f"/api/v1/pruner/instances/{sid}/scopes/tv/plex-live-removal-eligibility")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["eligible"] is False
        assert data["apply_feature_enabled"] is False
        assert data["plex_live_feature_enabled"] is False
        assert data["required_confirmation_phrase"] == PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE


def test_plex_live_post_rejects_jellyfin_instance(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
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
            json={"csrf_token": tok, "live_removal_confirmation": PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text


def test_plex_live_post_requires_exact_phrase(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
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
            json={"csrf_token": tok, "live_removal_confirmation": "wrong"},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text


def test_plex_live_post_ok_when_gates_on(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
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
            json={"csrf_token": tok, "live_removal_confirmation": PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "pruner_job_id" in body
        jid = int(body["pruner_job_id"])
        with session_factory() as s:
            row = s.scalars(select(PrunerJob).where(PrunerJob.id == jid)).one()
            assert row.job_kind == PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND
            payload = json.loads(row.payload_json or "{}")
            assert payload["server_instance_id"] == sid
            assert payload["media_scope"] == MEDIA_SCOPE_TV
            assert payload["rule_family_id"] == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED


def test_plex_live_handler_rejects_non_plex(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
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
    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND]
    with pytest.raises(ValueError, match="non-plex"):
        fn(
            PrunerJobWorkContext(
                id=1,
                job_kind=PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND,
                payload_json=json.dumps(
                    {
                        "server_instance_id": sid,
                        "media_scope": MEDIA_SCOPE_TV,
                        "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    },
                ),
                lease_owner="pytest",
            ),
        )


def test_plex_live_handler_no_preview_dependency(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
    settings = MediaMopSettings.load()
    sid = _plex_sid(session_factory)

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_plex_live_job_handler.list_plex_missing_thumb_candidates",
        lambda **_kw: [{"item_id": "99", "granularity": "episode"}],
    )
    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_plex_live_job_handler.plex_delete_library_metadata",
        lambda **_kw: (200, None),
    )

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="plex-live-test",
                job_kind=PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    handlers[PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND](
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND,
            payload_json=json.dumps(
                {
                    "server_instance_id": sid,
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc()).limit(1)).first()
        assert evt is not None
        assert evt.event_type == C.PRUNER_PLEX_LIVE_LIBRARY_REMOVAL_COMPLETED
        detail = json.loads(evt.detail or "{}")
        assert detail.get("preview_involved") is False
        assert detail.get("provider") == "plex"
        assert detail.get("live_mode") == "plex"
        assert detail.get("removed") == 1


def test_plex_live_handler_requires_apply_gate(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
    settings = MediaMopSettings.load()
    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND]
    with pytest.raises(RuntimeError, match="MEDIAMOP_PRUNER_APPLY_ENABLED"):
        fn(
            PrunerJobWorkContext(
                id=1,
                job_kind=PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND,
                payload_json=json.dumps(
                    {
                        "server_instance_id": 1,
                        "media_scope": MEDIA_SCOPE_TV,
                        "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    },
                ),
                lease_owner="pytest",
            ),
        )


def test_plex_live_effective_cap_respects_abs_max(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS", "2")
    settings = MediaMopSettings.load()
    sid = _plex_sid(session_factory)
    with session_factory() as s:
        from mediamop.modules.pruner.pruner_instances_service import get_scope_settings

        sc = get_scope_settings(s, server_instance_id=sid, media_scope=MEDIA_SCOPE_TV)
        assert sc is not None
        sc.preview_max_items = 500
        s.commit()

    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        r = client.get(f"/api/v1/pruner/instances/{sid}/scopes/tv/plex-live-removal-eligibility")
        assert r.status_code == 200, r.text
        assert r.json()["live_max_items_cap"] == 2
