"""CRUD helpers for ``broker_arr_connections``."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_arr_connections_model import BrokerArrConnectionRow
from mediamop.modules.broker.broker_schemas import BrokerArrConnectionOut, BrokerArrConnectionUpdate


def connection_to_api_out(row: BrokerArrConnectionRow) -> BrokerArrConnectionOut:
    """HTTP DTO — never returns stored ``api_key`` contents."""

    return BrokerArrConnectionOut(
        id=int(row.id),
        arr_type=str(row.arr_type),
        url=str(row.url or ""),
        api_key="",
        sync_mode=str(row.sync_mode or "full"),
        last_synced_at=row.last_synced_at,
        last_sync_ok=None if row.last_sync_ok is None else bool(int(row.last_sync_ok)),
        last_sync_error=row.last_sync_error,
        last_manual_sync_at=row.last_manual_sync_at,
        last_manual_sync_ok=None if row.last_manual_sync_ok is None else bool(int(row.last_manual_sync_ok)),
        indexer_fingerprint=row.indexer_fingerprint,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_connection(session: Session, arr_type: str) -> BrokerArrConnectionRow:
    row = session.scalars(select(BrokerArrConnectionRow).where(BrokerArrConnectionRow.arr_type == arr_type)).one_or_none()
    if row is None:
        msg = f"broker_arr_connections missing row for arr_type={arr_type!r}"
        raise RuntimeError(msg)
    return row


def update_connection(
    session: Session,
    arr_type: str,
    data: BrokerArrConnectionUpdate,
) -> BrokerArrConnectionRow:
    row = get_connection(session, arr_type)
    if data.url is not None:
        row.url = data.url.strip()
    if data.api_key is not None:
        row.api_key = data.api_key.strip()
    if data.sync_mode is not None:
        row.sync_mode = data.sync_mode.strip()
    session.flush()
    return row


def set_sync_result(
    session: Session,
    arr_type: str,
    *,
    ok: bool,
    error: str | None,
    fingerprint: str | None,
) -> None:
    row = get_connection(session, arr_type)
    row.last_synced_at = datetime.now(timezone.utc)
    row.last_sync_ok = 1 if ok else 0
    row.last_sync_error = None if ok else (error or "")[:10_000]
    if ok:
        row.indexer_fingerprint = fingerprint
    session.flush()


def set_manual_sync_result(
    session: Session,
    arr_type: str,
    *,
    ok: bool,
    error: str | None = None,
    indexer_fingerprint: str | None = None,
) -> None:
    row = get_connection(session, arr_type)
    row.last_manual_sync_at = datetime.now(timezone.utc)
    row.last_manual_sync_ok = 1 if ok else 0
    if ok and indexer_fingerprint is not None:
        row.indexer_fingerprint = indexer_fingerprint
    session.flush()
