"""Pruner multi-instance isolation (same-provider duplicates) + preview denorm contract."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from alembic import command
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_TV, RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_SERVER_CONNECTION_TEST_JOB_KIND
from mediamop.modules.pruner.pruner_preview_service import insert_preview_run
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sessionmaker[Session]:
    home = tmp_path / "mmhome"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_SUBBER_WORKER_COUNT", "0")
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    command.upgrade(cfg, "head")
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def test_two_emby_connection_tests_hit_distinct_base_urls(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s, s.begin():
        a = create_server_instance(
            s,
            settings,
            provider="emby",
            display_name="Emby A",
            base_url="http://emby-a.test",
            credentials_secrets={"api_key": "k-a"},
        )
        b = create_server_instance(
            s,
            settings,
            provider="emby",
            display_name="Emby B",
            base_url="http://emby-b.test",
            credentials_secrets={"api_key": "k-b"},
        )
        id_a, id_b = int(a.id), int(b.id)

    urls: list[str] = []

    def _fake(*, base_url: str, api_key: str = "", **_kw: object) -> tuple[bool, str]:
        del api_key
        urls.append(base_url)
        return True, f"ok:{base_url}"

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_SERVER_CONNECTION_TEST_JOB_KIND]

    with patch(
        "mediamop.modules.pruner.pruner_connection_job_handler.test_emby_jellyfin_connection",
        _fake,
    ):
        for sid in (id_a, id_b):
            fn(
                PrunerJobWorkContext(
                    id=99,
                    job_kind=PRUNER_SERVER_CONNECTION_TEST_JOB_KIND,
                    payload_json=json.dumps({"server_instance_id": sid}),
                    lease_owner="pytest",
                ),
            )

    assert urls == ["http://emby-a.test", "http://emby-b.test"]


def test_two_jellyfin_connection_tests_hit_distinct_base_urls(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s, s.begin():
        a = create_server_instance(
            s,
            settings,
            provider="jellyfin",
            display_name="JF A",
            base_url="http://jf-a.test",
            credentials_secrets={"api_key": "k-a"},
        )
        b = create_server_instance(
            s,
            settings,
            provider="jellyfin",
            display_name="JF B",
            base_url="http://jf-b.test",
            credentials_secrets={"api_key": "k-b"},
        )
        id_a, id_b = int(a.id), int(b.id)

    urls: list[str] = []

    def _fake(*, base_url: str, api_key: str = "", **_kw: object) -> tuple[bool, str]:
        del api_key
        urls.append(base_url)
        return True, f"ok:{base_url}"

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_SERVER_CONNECTION_TEST_JOB_KIND]

    with patch(
        "mediamop.modules.pruner.pruner_connection_job_handler.test_emby_jellyfin_connection",
        _fake,
    ):
        for sid in (id_a, id_b):
            fn(
                PrunerJobWorkContext(
                    id=99,
                    job_kind=PRUNER_SERVER_CONNECTION_TEST_JOB_KIND,
                    payload_json=json.dumps({"server_instance_id": sid}),
                    lease_owner="pytest",
                ),
            )

    assert urls == ["http://jf-a.test", "http://jf-b.test"]


def test_preview_denorm_only_updates_matching_instance_scope(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s, s.begin():
        a = create_server_instance(
            s,
            settings,
            provider="emby",
            display_name="A",
            base_url="http://a.test",
            credentials_secrets={"api_key": "x"},
        )
        b = create_server_instance(
            s,
            settings,
            provider="emby",
            display_name="B",
            base_url="http://b.test",
            credentials_secrets={"api_key": "y"},
        )
        id_a, id_b = int(a.id), int(b.id)

    with session_factory() as s:
        with s.begin():
            run = insert_preview_run(
                s,
                preview_run_uuid="00000000-0000-4000-8000-000000000001",
                server_instance_id=id_a,
                media_scope=MEDIA_SCOPE_TV,
                rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                pruner_job_id=None,
                candidate_count=2,
                candidates_json="[]",
                truncated=False,
                outcome="success",
                unsupported_detail=None,
                error_message=None,
            )
            run_id = int(run.id)

        sc_a = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == id_a,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
            ),
        ).one()
        sc_b = s.scalars(
            select(PrunerScopeSettings).where(
                PrunerScopeSettings.server_instance_id == id_b,
                PrunerScopeSettings.media_scope == MEDIA_SCOPE_TV,
            ),
        ).one()

    assert sc_a.last_preview_run_id == run_id
    assert sc_a.last_preview_outcome == "success"
    assert sc_b.last_preview_run_id is None
    assert sc_b.last_preview_outcome is None
