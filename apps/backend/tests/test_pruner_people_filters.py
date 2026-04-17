"""Pruner people filters: normalization, persistence, preview narrowing, apply isolation."""

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
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_TV,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_media_library import preview_payload_json
from mediamop.modules.pruner.pruner_people_filters import (
    item_matches_people_include_filter,
    jellyfin_emby_item_people_names,
    plex_leaf_person_tags,
    preview_people_filters_from_db_column,
    preview_people_filters_to_db_column,
)
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_patch, auth_post, csrf as fetch_csrf, seed_admin_user


def test_preview_people_filters_roundtrip_matches_genre_normalization() -> None:
    col = preview_people_filters_to_db_column([" a ", "A", "Comedy"])
    assert json.loads(col) == ["a", "Comedy"]
    assert preview_people_filters_from_db_column(col) == ["a", "Comedy"]


def test_preview_people_filters_from_db_column_fail_open() -> None:
    assert preview_people_filters_from_db_column("not-json") == []
    assert preview_people_filters_from_db_column('{"x":1}') == []


def test_item_matches_people_include_filter() -> None:
    assert item_matches_people_include_filter(["Alice"], ["alice"]) is True
    assert item_matches_people_include_filter(["Bob"], ["alice"]) is False
    assert item_matches_people_include_filter([], ["x"]) is False


def test_jellyfin_emby_item_people_names_reads_people_list() -> None:
    item = {"People": [{"Name": "Pat"}, {"Name": "  "}, {"Name": "Sam"}]}
    assert jellyfin_emby_item_people_names(item) == ["Pat", "Sam"]


def test_plex_leaf_person_tags_reads_role_writer_director() -> None:
    meta = {
        "Role": [{"tag": "Actor One"}],
        "Writer": [{"Tag": "Writer Two"}],
        "Director": "Sole Director",
    }
    tags = plex_leaf_person_tags(meta)
    assert "Actor One" in tags
    assert "Writer Two" in tags
    assert "Sole Director" in tags


def test_preview_payload_jellyfin_missing_primary_respects_people_filter() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        q = parse_qs(urlparse(url).query)
        assert "Fields" in q, "People filters must request explicit Items Fields"
        si = int(q.get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 2}
        return (
            200,
            {
                "Items": [
                    {
                        "Id": "a",
                        "Name": "E1",
                        "Genres": ["Drama"],
                        "ImageTags": {},
                        "People": [{"Name": "Pat Smith"}],
                    },
                    {
                        "Id": "b",
                        "Name": "E2",
                        "Genres": ["Drama"],
                        "ImageTags": {},
                        "People": [{"Name": "Other"}],
                    },
                ],
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
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            preview_include_people=["pat smith"],
        )
    assert out == "success" and not detail
    assert len(cands) == 1
    assert cands[0]["item_id"] == "a"
    assert trunc is False


def test_preview_payload_jellyfin_missing_primary_genre_and_people_and_semantics() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        q = parse_qs(urlparse(url).query)
        assert "Fields" in q
        si = int(q.get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 2}
        return (
            200,
            {
                "Items": [
                    {
                        "Id": "x",
                        "Name": "E",
                        "Genres": ["Drama"],
                        "ImageTags": {},
                        "People": [{"Name": "Pat"}],
                    },
                    {
                        "Id": "y",
                        "Name": "E2",
                        "Genres": ["Comedy"],
                        "ImageTags": {},
                        "People": [{"Name": "Pat"}],
                    },
                ],
                "TotalRecordCount": 2,
            },
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, _, cands, _ = preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_TV,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            preview_include_genres=["drama"],
            preview_include_people=["pat"],
        )
    assert out == "success"
    assert len(cands) == 1
    assert cands[0]["item_id"] == "x"


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_people_filters")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def test_scope_row_persists_people_filters(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="P",
                base_url="http://p.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            row = s.scalars(
                select(PrunerScopeSettings).where(
                    PrunerScopeSettings.server_instance_id == sid,
                    PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
                ),
            ).one()
            row.preview_include_people_json = preview_people_filters_to_db_column(["Ada Lovelace"])
    with session_factory() as s:
        row2 = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == sid,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
            ),
        ).one()
    assert json.loads(row2.preview_include_people_json) == ["Ada Lovelace"]


@pytest.fixture
def client_with_admin(_iso) -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text


def test_patch_scope_preview_include_people(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "PeoplePatch",
            "base_url": "http://emby-p.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])
    tok4 = fetch_csrf(client_with_admin)
    rpatch = auth_patch(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/scopes/movies",
        json={"preview_include_people": ["  Quincy ", "quincy", "Ada"], "csrf_token": tok4},
        headers={"Content-Type": "application/json"},
    )
    assert rpatch.status_code == 200, rpatch.text
    body = rpatch.json()
    assert body["preview_include_people"] == ["Quincy", "Ada"]


def test_plex_apply_does_not_call_candidate_collector_with_people_filters_on_scope(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
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
            sid = int(inst.id)
            row = s.scalars(
                select(PrunerScopeSettings).where(
                    PrunerScopeSettings.server_instance_id == sid,
                    PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
                ),
            ).one()
            row.preview_include_people_json = preview_people_filters_to_db_column(["Anyone"])
            run_uuid = str(uuid.uuid4())
            from mediamop.modules.pruner.pruner_preview_service import insert_preview_run

            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json=json.dumps([{"item_id": "1", "granularity": "episode"}]),
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
            job_row = PrunerJob(
                dedupe_key="plex-apply-people-scope-test",
                job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    calls: list[str] = []

    def _boom(**_kw: object) -> tuple[list[dict[str, object]], bool]:
        calls.append("list")
        raise AssertionError("apply must not rediscover Plex candidates")

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_plex_missing_thumb_candidates.list_plex_missing_thumb_candidates",
        _boom,
    )
    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_media_library.list_plex_missing_thumb_candidates",
        _boom,
    )

    def _delete(**kw: object) -> tuple[int, str | None]:
        if str(kw.get("rating_key", "")) == "1":
            return 200, None
        return 404, None

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_apply_job_handler.plex_delete_library_metadata",
        _delete,
    )

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
    assert calls == []
