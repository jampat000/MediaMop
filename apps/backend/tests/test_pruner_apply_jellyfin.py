"""Jellyfin-only Pruner apply-from-preview snapshot (Phase 3)."""

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
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_TV,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
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
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_apply")
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


def _jellyfin_preview_run(session_factory: sessionmaker[Session]) -> tuple[int, str]:
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
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
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=2,
                candidates_json=json.dumps(
                    [{"item_id": "a1", "granularity": "episode"}, {"item_id": "a2", "granularity": "episode"}],
                ),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
    return sid, run_uuid


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def test_apply_feature_off_blocks_post(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "0")
    sid, run_uuid = _jellyfin_preview_run(session_factory)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/tv/preview-runs/{run_uuid}/apply",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text
        body = r.json()
        assert "reasons" in body["detail"]


def test_apply_post_ok_when_enabled(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    sid, run_uuid = _jellyfin_preview_run(session_factory)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/tv/preview-runs/{run_uuid}/apply",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text
        assert "pruner_job_id" in r.json()


def test_apply_rejects_emby_instance(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="emby",
                display_name="E",
                base_url="http://em.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json="[{\"item_id\":\"x\"}]",
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/tv/preview-runs/{run_uuid}/apply",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text


def test_apply_rejects_scope_mismatch_in_url(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
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
                base_url="http://jf.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json="[{\"item_id\":\"x\"}]",
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/movies/preview-runs/{run_uuid}/apply",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text


def test_apply_rejects_non_success_preview(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
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
                base_url="http://jf.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json="[{\"item_id\":\"x\"}]",
                truncated=False,
                outcome="failed",
                unsupported_detail=None,
                error_message="x",
            )
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        tok = fetch_csrf(client)
        r = auth_post(
            client,
            f"/api/v1/pruner/instances/{sid}/scopes/tv/preview-runs/{run_uuid}/apply",
            json={"csrf_token": tok},
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422, r.text


def test_apply_activity_title_uses_operator_label(
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
                display_name="JF",
                base_url="http://jf.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json="[{\"item_id\":\"gone\"}]",
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="apply-title-test",
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
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc())).first()
        assert evt is not None
        assert "Remove broken library entries" in (evt.title or "")
        assert "preview snapshot" in (evt.title or "").lower()


def test_get_apply_eligibility_includes_feature_flag(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "0")
    sid, run_uuid = _jellyfin_preview_run(session_factory)
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        r = client.get(f"/api/v1/pruner/instances/{sid}/scopes/tv/preview-runs/{run_uuid}/apply-eligibility")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["eligible"] is False
        assert data["apply_feature_enabled"] is False


def test_no_global_apply_route() -> None:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/v1/pruner/apply", json={})
        assert r.status_code == 404


def test_apply_handler_raises_when_apply_disabled(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "0")
    settings = MediaMopSettings.load()
    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND]
    with pytest.raises(RuntimeError, match="MEDIAMOP_PRUNER_APPLY_ENABLED"):
        fn(
            PrunerJobWorkContext(
                id=1,
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                payload_json=json.dumps(
                    {
                        "preview_run_uuid": str(uuid.uuid4()),
                        "server_instance_id": 1,
                        "media_scope": MEDIA_SCOPE_TV,
                        "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    },
                ),
                lease_owner="pytest",
            ),
        )


def test_apply_handler_respects_snapshot_cap(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
    calls: list[str] = []

    def fake_delete(**kw: object) -> tuple[int, str | None]:
        calls.append(str(kw.get("item_id", "")))
        return 200, None

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.jellyfin_delete_library_item",
        fake_delete,
    )

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
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json=json.dumps(
                    [{"item_id": "only-one"}, {"item_id": "two"}],
                ),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="apply-cap-test",
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND]
    fn(
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
            payload_json=json.dumps(
                {
                    "preview_run_uuid": run_uuid,
                    "server_instance_id": sid,
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )
    assert calls == ["only-one"]


def test_apply_handler_partial_counts(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())

    seq = iter([(200, None), (404, None), (403, "nope")])

    def fake_delete(**_kw: object) -> tuple[int, str | None]:  # noqa: ANN401
        return next(seq)

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.jellyfin_delete_library_item",
        fake_delete,
    )

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
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=3,
                candidates_json=json.dumps(
                    [{"item_id": "r"}, {"item_id": "s"}, {"item_id": "f"}],
                ),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="apply-partial-test",
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
                    "media_scope": MEDIA_SCOPE_TV,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc())).first()
        assert evt is not None
        assert evt.event_type == C.PRUNER_APPLY_LIBRARY_REMOVAL_COMPLETED
        detail = json.loads(evt.detail or "{}")
        assert detail["removed"] == 1
        assert detail["skipped"] == 1
        assert detail["failed"] == 1
        assert "preview snapshot" in (evt.title or "").lower() or "snapshot" in (detail.get("note") or "").lower()
