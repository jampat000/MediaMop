"""Unit-style tests for ``broker.sync.*`` handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.broker.broker_job_context import BrokerJobWorkContext
from mediamop.modules.broker.broker_job_handlers import build_broker_job_handlers
from mediamop.modules.broker.broker_job_kinds import (
    BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1,
    BROKER_JOB_KIND_SYNC_RADARR_V1,
    BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
    BROKER_JOB_KIND_SYNC_SONARR_V1,
)
from mediamop.modules.broker.broker_jobs_ops import broker_enqueue_or_get_job
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_broker_sync_handler")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _handlers(session_factory):
    return build_broker_job_handlers(MediaMopSettings.load(), session_factory)


def test_auto_sync_noop_when_fingerprint_unchanged(session_factory) -> None:
    from mediamop.modules.broker.broker_arr_connections_service import get_connection, update_connection
    from mediamop.modules.broker.broker_indexers_service import create_indexer
    from mediamop.modules.broker.broker_schemas import (
        BrokerArrConnectionUpdate,
        BrokerIndexerCreate,
    )
    from mediamop.modules.broker.broker_indexers_service import get_enabled_indexers
    from mediamop.modules.broker.broker_sync_service import compute_indexer_fingerprint

    with session_factory() as db:
        create_indexer(
            db,
            BrokerIndexerCreate(
                name="A",
                slug="s1",
                kind="torznab",
                protocol="torrent",
                enabled=True,
            ),
        )
        en = get_enabled_indexers(db)
        fp = compute_indexer_fingerprint(en)
        update_connection(db, "sonarr", BrokerArrConnectionUpdate(url="http://s", api_key="k"))
        row = get_connection(db, "sonarr")
        row.indexer_fingerprint = fp
        broker_enqueue_or_get_job(
            db,
            dedupe_key="noop:auto:sonarr",
            job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1,
        )
        db.commit()

    h = _handlers(session_factory)["broker.sync.sonarr.v1"]
    with patch(
        "mediamop.modules.broker.broker_sync_job_handler.apply_broker_indexers_to_arr",
        side_effect=AssertionError("should not call arr when noop"),
    ) as m:
        h(BrokerJobWorkContext(id=1, job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1, payload_json=None, lease_owner="x"))
    m.assert_not_called()


def test_auto_sync_runs_when_fingerprint_changed(session_factory) -> None:
    from mediamop.modules.broker.broker_arr_connections_service import update_connection
    from mediamop.modules.broker.broker_indexers_service import create_indexer
    from mediamop.modules.broker.broker_schemas import BrokerArrConnectionUpdate, BrokerIndexerCreate

    with session_factory() as db:
        create_indexer(
            db,
            BrokerIndexerCreate(
                name="A",
                slug="s2",
                kind="torznab",
                protocol="torrent",
                enabled=True,
            ),
        )
        update_connection(db, "sonarr", BrokerArrConnectionUpdate(url="http://s", api_key="k"))
        broker_enqueue_or_get_job(
            db,
            dedupe_key="chg:auto:sonarr",
            job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1,
        )
        db.commit()

    h = _handlers(session_factory)["broker.sync.sonarr.v1"]
    with patch("mediamop.modules.broker.broker_sync_job_handler.apply_broker_indexers_to_arr") as m:
        h(BrokerJobWorkContext(id=1, job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1, payload_json=None, lease_owner="x"))
    m.assert_called_once()


def test_manual_sync_always_calls_arr_even_when_fingerprint_matches(session_factory) -> None:
    from mediamop.modules.broker.broker_arr_connections_service import get_connection, update_connection
    from mediamop.modules.broker.broker_indexers_service import create_indexer
    from mediamop.modules.broker.broker_schemas import (
        BrokerArrConnectionUpdate,
        BrokerIndexerCreate,
    )
    from mediamop.modules.broker.broker_indexers_service import get_enabled_indexers
    from mediamop.modules.broker.broker_sync_service import compute_indexer_fingerprint

    with session_factory() as db:
        create_indexer(
            db,
            BrokerIndexerCreate(
                name="A",
                slug="s3",
                kind="torznab",
                protocol="torrent",
                enabled=True,
            ),
        )
        en = get_enabled_indexers(db)
        fp = compute_indexer_fingerprint(en)
        update_connection(db, "radarr", BrokerArrConnectionUpdate(url="http://r", api_key="k"))
        row = get_connection(db, "radarr")
        row.indexer_fingerprint = fp
        broker_enqueue_or_get_job(
            db,
            dedupe_key="manual:radarr:fp",
            job_kind=BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1,
        )
        db.commit()

    h = _handlers(session_factory)["broker.sync.radarr.manual.v1"]
    with patch("mediamop.modules.broker.broker_sync_job_handler.apply_broker_indexers_to_arr") as m:
        h(BrokerJobWorkContext(id=1, job_kind=BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1, payload_json=None, lease_owner="x"))
    m.assert_called_once()


def test_sonarr_and_radarr_handlers_independent(session_factory) -> None:
    from mediamop.modules.broker.broker_arr_connections_service import update_connection
    from mediamop.modules.broker.broker_schemas import BrokerArrConnectionUpdate

    with session_factory() as db:
        update_connection(db, "sonarr", BrokerArrConnectionUpdate(url="http://s", api_key="k"))
        update_connection(db, "radarr", BrokerArrConnectionUpdate(url="http://r", api_key="k"))
        broker_enqueue_or_get_job(db, dedupe_key="indep:sonarr", job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1)
        broker_enqueue_or_get_job(db, dedupe_key="indep:radarr", job_kind=BROKER_JOB_KIND_SYNC_RADARR_V1)
        db.commit()

    reg = _handlers(session_factory)
    with patch("mediamop.modules.broker.broker_sync_job_handler.apply_broker_indexers_to_arr") as m_sonarr:
        reg["broker.sync.sonarr.v1"](
            BrokerJobWorkContext(id=1, job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1, payload_json=None, lease_owner="a"),
        )
    assert m_sonarr.call_count == 1
    with patch("mediamop.modules.broker.broker_sync_job_handler.apply_broker_indexers_to_arr") as m_radarr:
        reg["broker.sync.radarr.v1"](
            BrokerJobWorkContext(id=2, job_kind=BROKER_JOB_KIND_SYNC_RADARR_V1, payload_json=None, lease_owner="b"),
        )
    assert m_radarr.call_count == 1


def test_not_configured_raises(session_factory) -> None:
    with session_factory() as db:
        broker_enqueue_or_get_job(
            db,
            dedupe_key="nc:sonarr",
            job_kind=BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
        )
        db.commit()

    h = _handlers(session_factory)["broker.sync.sonarr.manual.v1"]
    with pytest.raises(RuntimeError, match="ARR not configured"):
        h(BrokerJobWorkContext(id=1, job_kind=BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1, payload_json=None, lease_owner="x"))
