"""Handlers for ``broker.sync.*`` — push Broker indexers to Sonarr/Radarr."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import sessionmaker

from mediamop.modules.broker.broker_arr_connections_service import (
    get_connection,
    set_manual_sync_result,
    set_sync_result,
)
from mediamop.modules.broker.broker_arr_http import BrokerArrV3Client
from mediamop.modules.broker.broker_arr_indexer_sync import apply_broker_indexers_to_arr
from mediamop.modules.broker.broker_indexers_service import get_enabled_indexers
from mediamop.modules.broker.broker_job_context import BrokerJobWorkContext
from mediamop.modules.broker.broker_job_kinds import (
    BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1,
    BROKER_JOB_KIND_SYNC_RADARR_V1,
    BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
    BROKER_JOB_KIND_SYNC_SONARR_V1,
)
from mediamop.modules.broker.broker_sync_service import compute_indexer_fingerprint, fingerprint_unchanged


def _run_arr_sync(
    session_factory: sessionmaker[Session],
    *,
    arr_type: str,
    manual: bool,
) -> None:
    with session_factory() as session:
        with session.begin():
            conn = get_connection(session, arr_type)
            url = (conn.url or "").strip()
            key = (conn.api_key or "").strip()
            if not url or not key:
                raise RuntimeError("ARR not configured")
            enabled = get_enabled_indexers(session)
            fp = compute_indexer_fingerprint(enabled)
            if not manual and fingerprint_unchanged(session, arr_type, fp):
                return

    with session_factory() as session2:
        with session2.begin():
            enabled2 = get_enabled_indexers(session2)
            fp2 = compute_indexer_fingerprint(enabled2)

    client = BrokerArrV3Client(url, key)
    try:
        apply_broker_indexers_to_arr(client, enabled2)
    except Exception as exc:
        err = str(exc)[:10_000]
        with session_factory() as session3:
            with session3.begin():
                set_sync_result(session3, arr_type, ok=False, error=err, fingerprint=None)
                if manual:
                    set_manual_sync_result(session3, arr_type, ok=False)
        raise

    with session_factory() as session4:
        with session4.begin():
            if manual:
                set_sync_result(session4, arr_type, ok=True, error=None, fingerprint=fp2)
                set_manual_sync_result(session4, arr_type, ok=True)
            else:
                set_sync_result(session4, arr_type, ok=True, error=None, fingerprint=fp2)


def register_broker_sync_handlers(
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[BrokerJobWorkContext], None]]:
    def sonarr_auto(_ctx: BrokerJobWorkContext) -> None:
        _run_arr_sync(session_factory, arr_type="sonarr", manual=False)

    def radarr_auto(_ctx: BrokerJobWorkContext) -> None:
        _run_arr_sync(session_factory, arr_type="radarr", manual=False)

    def sonarr_manual(_ctx: BrokerJobWorkContext) -> None:
        _run_arr_sync(session_factory, arr_type="sonarr", manual=True)

    def radarr_manual(_ctx: BrokerJobWorkContext) -> None:
        _run_arr_sync(session_factory, arr_type="radarr", manual=True)

    return {
        BROKER_JOB_KIND_SYNC_SONARR_V1: sonarr_auto,
        BROKER_JOB_KIND_SYNC_RADARR_V1: radarr_auto,
        BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1: sonarr_manual,
        BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1: radarr_manual,
    }
