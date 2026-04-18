"""Pruner watched low-rating movies + unwatched stale movies (Jellyfin/Emby) and preview Fields union."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
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
from sqlalchemy import select

from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
    RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_media_library import (
    jf_emby_pruner_preview_items_fields_csv,
    preview_payload_json,
)
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.pruner_schemas import PrunerPreviewEnqueueIn
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_patch, auth_post, csrf as fetch_csrf, seed_admin_user


def test_jf_emby_pruner_preview_items_fields_csv_includes_people_and_rating() -> None:
    csv = jf_emby_pruner_preview_items_fields_csv()
    assert "People" in csv
    assert "CommunityRating" in csv
    assert "UserData" in csv
    assert "DateCreated" in csv


def test_pruner_preview_enqueue_rejects_tv_for_low_rating_rule() -> None:
    with pytest.raises(ValidationError):
        PrunerPreviewEnqueueIn.model_validate(
            {
                "media_scope": "tv",
                "rule_family_id": RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
                "csrf_token": "x",
            },
        )


def test_pruner_preview_enqueue_rejects_tv_for_unwatched_stale_rule() -> None:
    with pytest.raises(ValidationError):
        PrunerPreviewEnqueueIn.model_validate(
            {
                "media_scope": "tv",
                "rule_family_id": RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
                "csrf_token": "x",
            },
        )


def _assert_items_fields_include_preview_union(url: str) -> None:
    q = parse_qs(urlparse(url).query)
    assert "Fields" in q
    got = set(q["Fields"][0].split(","))
    want = set(jf_emby_pruner_preview_items_fields_csv().split(","))
    assert got == want


def test_preview_payload_jellyfin_low_rating_requests_union_fields() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        _assert_items_fields_include_preview_union(url)
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 1}
        return (
            200,
            {
                "Items": [
                    {
                        "Id": "m-low",
                        "Name": "Low",
                        "ProductionYear": 2019,
                        "CommunityRating": 3.0,
                        "UserData": {"Played": True, "PlayCount": 1},
                        "Genres": ["Drama"],
                        "People": [{"Name": "Pat"}],
                    },
                    {
                        "Id": "m-high",
                        "Name": "High",
                        "CommunityRating": 9.0,
                        "UserData": {"Played": True, "PlayCount": 1},
                    },
                ],
                "TotalRecordCount": 2,
            },
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
            watched_movie_low_rating_max_jellyfin_emby_community_rating=4.0,
            watched_movie_low_rating_max_plex_audience_rating=4.0,
        )
    assert out == "success" and detail == ""
    assert not trunc
    assert len(cands) == 1
    assert cands[0]["item_id"] == "m-low"
    assert cands[0]["community_rating"] == 3.0
    assert cands[0]["watched_movie_low_rating_max_jellyfin_emby_community_rating"] == 4.0


def test_preview_payload_jellyfin_unwatched_stale_uses_date_created() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        _assert_items_fields_include_preview_union(url)
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 1}
        return (
            200,
            {
                "Items": [
                    {
                        "Id": "m-old",
                        "Name": "Old unwatched",
                        "DateCreated": "2001-06-15T12:00:00.000Z",
                        "UserData": {"Played": False, "PlayCount": 0},
                    },
                    {
                        "Id": "m-new",
                        "Name": "New unwatched",
                        "DateCreated": "2030-06-15T12:00:00.000Z",
                        "UserData": {"Played": False, "PlayCount": 0},
                    },
                ],
                "TotalRecordCount": 2,
            },
        )

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="emby",
            base_url="http://em.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
            unwatched_movie_stale_min_age_days=90,
        )
    assert out == "success" and detail == ""
    assert not trunc
    assert len(cands) == 1
    assert cands[0]["item_id"] == "m-old"


def test_preview_payload_jellyfin_low_rating_requires_jf_ceiling_param() -> None:
    with pytest.raises(ValueError, match="watched_movie_low_rating_max_jellyfin_emby_community_rating"):
        preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"api_key": "k"},
            max_items=10,
            rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
            watched_movie_low_rating_max_jellyfin_emby_community_rating=None,
            watched_movie_low_rating_max_plex_audience_rating=4.0,
        )


def test_preview_payload_plex_low_rating_requires_plex_ceiling_param() -> None:
    with pytest.raises(ValueError, match="watched_movie_low_rating_max_plex_audience_rating"):
        preview_payload_json(
            provider="plex",
            base_url="http://plex.test",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"auth_token": "t"},
            max_items=10,
            rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
            watched_movie_low_rating_max_jellyfin_emby_community_rating=4.0,
            watched_movie_low_rating_max_plex_audience_rating=None,
        )


def test_preview_payload_tv_scope_low_rating_unsupported() -> None:
    out, detail, cands, trunc = preview_payload_json(
        provider="jellyfin",
        base_url="http://jf.test",
        media_scope=MEDIA_SCOPE_TV,
        secrets={"api_key": "k"},
        max_items=10,
        rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
        watched_movie_low_rating_max_jellyfin_emby_community_rating=5.0,
        watched_movie_low_rating_max_plex_audience_rating=5.0,
    )
    assert out == "unsupported"
    assert "movies tab" in detail.lower()
    assert cands == [] and trunc is False


def test_preview_payload_plex_low_rating_uses_audience_rating() -> None:
    from unittest.mock import patch

    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        if "allLeaves" not in url:
            return 200, {"MediaContainer": {"Directory": [{"type": "movie", "key": "1"}]}}
        return (
            200,
            {
                "MediaContainer": {
                    "Metadata": [
                        {
                            "type": "movie",
                            "ratingKey": "z",
                            "title": "Low",
                            "viewCount": 1,
                            "audienceRating": 3.0,
                        },
                    ],
                    "totalSize": 1,
                },
            },
        )

    with patch("mediamop.modules.pruner.pruner_plex_movie_rule_candidates.http_get_json", fake_get_json):
        out, detail, cands, trunc = preview_payload_json(
            provider="plex",
            base_url="http://plex:32400",
            media_scope=MEDIA_SCOPE_MOVIES,
            secrets={"auth_token": "t"},
            max_items=10,
            rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
            watched_movie_low_rating_max_jellyfin_emby_community_rating=4.0,
            watched_movie_low_rating_max_plex_audience_rating=4.0,
        )
    assert out == "success" and detail == ""
    assert len(cands) == 1 and cands[0]["item_id"] == "z"
    assert cands[0]["plex_audience_rating"] == 3.0
    assert cands[0]["watched_movie_low_rating_max_plex_audience_rating"] == 4.0
    assert not trunc


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
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_movie_low_rating")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


@pytest.fixture
def client_with_admin(_iso) -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_patch_pruner_scope_persists_low_rating_and_unwatched_stale_fields(
    client_with_admin: TestClient,
) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "jellyfin",
            "display_name": "JF",
            "base_url": "http://jf-scope.test",
            "credentials": {"api_key": "k"},
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text
    iid = int(r0.json()["id"])
    tok = fetch_csrf(client_with_admin)
    r1 = auth_patch(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/scopes/movies",
        json={
            "watched_movie_low_rating_reported_enabled": True,
            "watched_movie_low_rating_max_jellyfin_emby_community_rating": 3.5,
            "unwatched_movie_stale_reported_enabled": True,
            "unwatched_movie_stale_min_age_days": 120,
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["watched_movie_low_rating_reported_enabled"] is True
    assert body["watched_movie_low_rating_max_jellyfin_emby_community_rating"] == 3.5
    assert body["watched_movie_low_rating_max_plex_audience_rating"] == 4.0
    assert body["unwatched_movie_stale_reported_enabled"] is True
    assert body["unwatched_movie_stale_min_age_days"] == 120

    tok = fetch_csrf(client_with_admin)
    r2 = auth_patch(
        client_with_admin,
        f"/api/v1/pruner/instances/{iid}/scopes/movies",
        json={
            "watched_movie_low_rating_max_plex_audience_rating": 2.25,
            "csrf_token": tok,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["watched_movie_low_rating_max_jellyfin_emby_community_rating"] == 3.5
    assert body2["watched_movie_low_rating_max_plex_audience_rating"] == 2.25


def test_apply_jellyfin_low_rating_movies_skips_404(
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
                base_url="http://jf-apply.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            insert_preview_run(
                s,
                preview_run_uuid=run_uuid,
                server_instance_id=sid,
                media_scope=MEDIA_SCOPE_MOVIES,
                rule_family_id=RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
                pruner_job_id=None,
                candidate_count=1,
                candidates_json='[{"item_id":"gone"}]',
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="apply-low-rating",
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
                    "rule_family_id": RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
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
