"""Pruner ``watched_tv_reported`` — Jellyfin/Emby TV episodes only (preview + snapshot apply)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
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
from alembic import command
from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_WATCHED_TV_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_media_library import preview_payload_json
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, seed_admin_user
from tests.integration_helpers import csrf as fetch_csrf


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
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_watched_tv")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def _episode_item(eid: str, played: bool = True) -> dict:
    return {
        "Id": eid,
        "Name": "Pilot",
        "SeriesName": "Test Show",
        "ParentIndexNumber": 1,
        "IndexNumber": 1,
        "UserData": {"Played": played, "PlayCount": 1 if played else 0},
    }


def test_preview_payload_jellyfin_watched_tv_lists_watched_episodes() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 2}
        return (
            200,
            {
                "Items": [_episode_item("ep-1"), _episode_item("ep-2")],
                "TotalRecordCount": 2,
            },
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_TV,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            never_played_min_age_days=None,
        )
    assert out == "success"
    assert detail == ""
    assert not trunc
    assert len(cands) == 2
    assert {c["item_id"] for c in cands} == {"ep-1", "ep-2"}


def test_preview_payload_emby_watched_tv_same_items_contract() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 1}
        return (
            200,
            {"Items": [_episode_item("e99")], "TotalRecordCount": 1},
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="emby",
            base_url="http://emby.test",
            media_scope=MEDIA_SCOPE_TV,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            never_played_min_age_days=None,
        )
    assert out == "success" and not detail
    assert len(cands) == 1 and cands[0]["item_id"] == "e99"
    assert trunc is False


def test_preview_payload_plex_watched_tv_unsupported() -> None:
    out, detail, cands, trunc = preview_payload_json(
        provider="plex",
        base_url="http://plex:32400",
        media_scope=MEDIA_SCOPE_TV,
        secrets={"auth_token": "t"},
        max_items=50,
        rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
        never_played_min_age_days=None,
    )
    assert out == "unsupported"
    assert "plex" in detail.lower()
    assert cands == [] and trunc is False


def test_preview_payload_movies_scope_watched_tv_unsupported() -> None:
    out, detail, cands, trunc = preview_payload_json(
        provider="jellyfin",
        base_url="http://jf.test",
        media_scope=MEDIA_SCOPE_MOVIES,
        secrets={"api_key": "k"},
        max_items=50,
        rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
        never_played_min_age_days=None,
    )
    assert out == "unsupported"
    assert "tv tab" in detail.lower()
    assert cands == []


def test_list_watched_tv_isolation_two_base_urls() -> None:
    seen: list[str] = []

    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        seen.append(url)
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 0}
        return 200, {"Items": [], "TotalRecordCount": 0}

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        preview_payload_json(
            provider="jellyfin",
            base_url="http://jf-a.test",
            media_scope=MEDIA_SCOPE_TV,
            secrets={"api_key": "a"},
            max_items=5,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            never_played_min_age_days=None,
        )
        preview_payload_json(
            provider="jellyfin",
            base_url="http://jf-b.test",
            media_scope=MEDIA_SCOPE_TV,
            secrets={"api_key": "b"},
            max_items=5,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            never_played_min_age_days=None,
        )
    assert any("jf-a.test" in u for u in seen)
    assert any("jf-b.test" in u for u in seen)


def test_watched_tv_preview_denorm_only_affects_target_instance(
    session_factory: sessionmaker[Session],
) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s, s.begin():
        a = create_server_instance(
            s,
            settings,
            provider="jellyfin",
            display_name="A",
            base_url="http://jf-a-w.test",
            credentials_secrets={"api_key": "a"},
        )
        b = create_server_instance(
            s,
            settings,
            provider="jellyfin",
            display_name="B",
            base_url="http://jf-b-w.test",
            credentials_secrets={"api_key": "b"},
        )
        id_a, id_b = int(a.id), int(b.id)

    uid = str(uuid.uuid4())
    with session_factory() as s, s.begin():
        insert_preview_run(
            s,
            preview_run_uuid=uid,
            server_instance_id=id_a,
            media_scope=MEDIA_SCOPE_TV,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            pruner_job_id=None,
            candidate_count=3,
            candidates_json="[]",
            truncated=False,
            outcome="success",
            unsupported_detail=None,
            error_message=None,
        )

    with session_factory() as s:
        tv_b = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == id_b,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
            ),
        ).one()
    assert tv_b.last_preview_outcome is None


def test_watched_tv_preview_denorm_only_updates_tv_scope_row(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s, s.begin():
        inst = create_server_instance(
            s,
            settings,
            provider="jellyfin",
            display_name="One",
            base_url="http://jf-one.test",
            credentials_secrets={"api_key": "k"},
        )
        sid = int(inst.id)

    uid = str(uuid.uuid4())
    with session_factory() as s, s.begin():
        insert_preview_run(
            s,
            preview_run_uuid=uid,
            server_instance_id=sid,
            media_scope=MEDIA_SCOPE_TV,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            pruner_job_id=None,
            candidate_count=1,
            candidates_json="[]",
            truncated=False,
            outcome="success",
            unsupported_detail=None,
            error_message=None,
        )

    with session_factory() as s:
        tv = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == sid,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
            ),
        ).one()
        movies = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == sid,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_MOVIES,
            ),
        ).one()

    assert tv.last_preview_outcome == "success"
    assert movies.last_preview_outcome is None


def test_apply_jellyfin_watched_tv_activity_wording(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.jellyfin_delete_library_item",
        lambda **kw: (204, None),
    )
    with session_factory() as s, s.begin():
        inst = create_server_instance(
            s,
            settings,
            provider="jellyfin",
            display_name="JF Watch",
            base_url="http://jf-watch.test",
            credentials_secrets={"api_key": "k"},
        )
        sid = int(inst.id)
        insert_preview_run(
            s,
            preview_run_uuid=run_uuid,
            server_instance_id=sid,
            media_scope=MEDIA_SCOPE_TV,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            pruner_job_id=None,
            candidate_count=1,
            candidates_json='[{"item_id":"ep-x","granularity":"episode"}]',
            truncated=False,
            outcome="success",
            unsupported_detail=None,
            error_message=None,
        )
    with session_factory() as s, s.begin():
        job_row = PrunerJob(
            dedupe_key="apply-watched-jf",
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
                    "rule_family_id": RULE_FAMILY_WATCHED_TV_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc())).first()
        assert evt is not None
        title = evt.title or ""
        assert "Remove watched TV entries" in title
        assert "jellyfin" in title.lower()
        assert "tv" in title.lower() or "episodes" in title.lower()
        d = json.loads(evt.detail or "{}")
        assert d.get("phase") == "apply"
        assert d.get("provider") == "jellyfin"
        assert d.get("media_scope") == MEDIA_SCOPE_TV
        assert d.get("rule_family_id") == RULE_FAMILY_WATCHED_TV_REPORTED


def test_apply_emby_watched_tv_activity_names_emby(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = MediaMopSettings.load()
    run_uuid = str(uuid.uuid4())
    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.emby_delete_library_item",
        lambda **kw: (204, None),
    )
    with session_factory() as s, s.begin():
        inst = create_server_instance(
            s,
            settings,
            provider="emby",
            display_name="Emby Watch",
            base_url="http://emby-watch.test",
            credentials_secrets={"api_key": "k"},
        )
        sid = int(inst.id)
        insert_preview_run(
            s,
            preview_run_uuid=run_uuid,
            server_instance_id=sid,
            media_scope=MEDIA_SCOPE_TV,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            pruner_job_id=None,
            candidate_count=1,
            candidates_json='[{"item_id":"e1"}]',
            truncated=False,
            outcome="success",
            unsupported_detail=None,
            error_message=None,
        )
    with session_factory() as s, s.begin():
        job_row = PrunerJob(
            dedupe_key="apply-watched-emby",
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
                    "rule_family_id": RULE_FAMILY_WATCHED_TV_REPORTED,
                },
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.desc())).first()
        assert evt is not None
        assert "Remove watched TV entries" in (evt.title or "")
        assert "(emby)" in (evt.title or "").lower()
        assert json.loads(evt.detail or "{}").get("provider") == "emby"


@pytest.fixture
def client_with_admin(_iso) -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_post_preview_watched_tv_rejects_movies_tab(client_with_admin: TestClient) -> None:
    """HTTP rejects Movies + watched_tv before enqueue (no cross-scope bleed)."""

    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "WatchedTab",
            "base_url": "http://watched-tab.test",
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
            "media_scope": "movies",
            "rule_family_id": RULE_FAMILY_WATCHED_TV_REPORTED,
            "csrf_token": tok2,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text
