"""Pruner per-scope preview genre include filters (Jellyfin/Emby + Plex missing-primary)."""

from __future__ import annotations

import json
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
    RULE_FAMILY_WATCHED_TV_REPORTED,
)
from mediamop.modules.pruner.pruner_genre_filters import (
    normalized_genre_filter_tokens,
    preview_genre_filters_to_db_column,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_media_library import preview_payload_json
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_patch, auth_post, csrf as fetch_csrf, seed_admin_user


@pytest.fixture(autouse=True)
def _iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_pruner_genre_filters")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


def test_normalized_genre_filter_tokens_rejects_too_many() -> None:
    with pytest.raises(ValueError, match="at most"):
        normalized_genre_filter_tokens([f"g{i}" for i in range(30)])


def test_preview_payload_jellyfin_missing_primary_ignores_genre_params() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        si = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 2}
        return (
            200,
            {
                "Items": [
                    {"Id": "a", "Name": "E1", "Genres": ["Drama"], "ImageTags": {}},
                    {"Id": "b", "Name": "E2", "Genres": ["Comedy"], "ImageTags": {}},
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
            preview_include_genres=["drama"],
        )
    assert out == "success" and not detail
    assert len(cands) == 2
    assert {c["item_id"] for c in cands} == {"a", "b"}
    assert trunc is False


def test_preview_payload_jellyfin_watched_tv_genre_filter() -> None:
    def fake_get_json(url: str, headers: dict[str, str]) -> tuple[int, dict]:  # noqa: ARG001
        q = parse_qs(urlparse(url).query)
        si = int(q.get("StartIndex", ["0"])[0])
        if q.get("IsPlayed") == ["true"]:
            if si > 0:
                return 200, {"Items": [], "TotalRecordCount": 1}
            return (
                200,
                {
                    "Items": [
                        {
                            "Id": "e1",
                            "Name": "Pilot",
                            "SeriesName": "S",
                            "Genres": ["Sci-Fi"],
                            "UserData": {"Played": True},
                        },
                    ],
                    "TotalRecordCount": 1,
                },
            )
        if si > 0:
            return 200, {"Items": [], "TotalRecordCount": 0}
        return 200, {"Items": [], "TotalRecordCount": 0}

    with patch("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json):
        out, _, cands, _ = preview_payload_json(
            provider="jellyfin",
            base_url="http://jf.test",
            media_scope=MEDIA_SCOPE_TV,
            secrets={"api_key": "k"},
            max_items=50,
            rule_family_id=RULE_FAMILY_WATCHED_TV_REPORTED,
            preview_include_genres=["Horror"],
        )
    assert out == "success"
    assert len(cands) == 1
    assert cands[0]["item_id"] == "e1"


def test_preview_genre_filters_to_db_column_roundtrip() -> None:
    s = preview_genre_filters_to_db_column([" Drama ", "drama", "Comedy"])
    assert json.loads(s) == ["Drama", "Comedy"]


@pytest.fixture
def session_factory(_iso) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def test_scope_row_persists_genre_filters(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="G",
                base_url="http://g.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            row = s.scalars(
                select(PrunerScopeSettings).where(
                    PrunerScopeSettings.server_instance_id == sid,
                    PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
                ),
            ).one()
            row.preview_include_genres_json = preview_genre_filters_to_db_column(["Noir"])
    with session_factory() as s:
        row2 = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == sid,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
            ),
        ).one()
    assert json.loads(row2.preview_include_genres_json) == ["Noir"]


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


def test_patch_scope_preview_include_genres(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = auth_post(
        client_with_admin,
        "/api/v1/pruner/instances",
        json={
            "provider": "emby",
            "display_name": "GenrePatch",
            "base_url": "http://emby-g.test",
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
        json={"preview_include_genres": ["Western", "Action"], "csrf_token": tok4},
        headers={"Content-Type": "application/json"},
    )
    assert rpatch.status_code == 200, rpatch.text
    body = rpatch.json()
    assert body["preview_include_genres"] == ["Western", "Action"]
