"""CRUD for ``broker_indexers`` (Broker-owned)."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_indexers_model import BrokerIndexerRow
from mediamop.modules.broker.broker_job_kinds import (
    BROKER_JOB_KIND_SYNC_RADARR_V1,
    BROKER_JOB_KIND_SYNC_SONARR_V1,
)
from mediamop.modules.broker.broker_jobs_ops import broker_enqueue_or_get_job
from mediamop.modules.broker.broker_schemas import BrokerIndexerCreate, BrokerIndexerOut, BrokerIndexerUpdate


def _dump_json_list_ints(xs: list[int]) -> str:
    return json.dumps(list(xs))


def _dump_json_list_str(xs: list[str]) -> str:
    return json.dumps(list(xs))


def _parse_json_int_list(raw: str) -> list[int]:
    try:
        xs = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(xs, list):
        return []
    out: list[int] = []
    for x in xs:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _parse_json_str_list(raw: str) -> list[str]:
    try:
        xs = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(xs, list):
        return []
    return [str(x) for x in xs if x is not None]


def indexer_to_api_out(row: BrokerIndexerRow) -> BrokerIndexerOut:
    """HTTP DTO — never returns stored ``api_key`` contents."""

    return BrokerIndexerOut(
        id=int(row.id),
        name=str(row.name),
        slug=str(row.slug),
        kind=str(row.kind),
        protocol=str(row.protocol),
        privacy=str(row.privacy),
        url=str(row.url or ""),
        api_key="",
        enabled=bool(int(row.enabled)),
        priority=int(row.priority),
        categories=_parse_json_int_list(row.categories),
        tags=_parse_json_str_list(row.tags),
        last_tested_at=row.last_tested_at,
        last_test_ok=None if row.last_test_ok is None else bool(int(row.last_test_ok)),
        last_test_error=row.last_test_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _enqueue_auto_sync_after_indexer_change(session: Session, *, indexer_id: int) -> None:
    """Enqueue independent Sonarr and Radarr auto-sync jobs (dedupe keys include time for tests)."""

    ts = int(time.time_ns())
    broker_enqueue_or_get_job(
        session,
        dedupe_key=f"broker.sync.auto:sonarr:idx:{indexer_id}:{ts}",
        job_kind=BROKER_JOB_KIND_SYNC_SONARR_V1,
        payload_json=json.dumps({"indexer_id": indexer_id}),
    )
    broker_enqueue_or_get_job(
        session,
        dedupe_key=f"broker.sync.auto:radarr:idx:{indexer_id}:{ts}",
        job_kind=BROKER_JOB_KIND_SYNC_RADARR_V1,
        payload_json=json.dumps({"indexer_id": indexer_id}),
    )


def get_all_indexers(session: Session) -> list[BrokerIndexerRow]:
    return list(session.scalars(select(BrokerIndexerRow).order_by(BrokerIndexerRow.priority, BrokerIndexerRow.id)).all())


def get_indexer_by_id(session: Session, indexer_id: int) -> BrokerIndexerRow | None:
    return session.scalars(select(BrokerIndexerRow).where(BrokerIndexerRow.id == indexer_id)).one_or_none()


def get_enabled_indexers(session: Session) -> list[BrokerIndexerRow]:
    return list(
        session.scalars(
            select(BrokerIndexerRow)
            .where(BrokerIndexerRow.enabled == 1)
            .order_by(BrokerIndexerRow.priority, BrokerIndexerRow.id),
        ).all(),
    )


def create_indexer(session: Session, data: BrokerIndexerCreate) -> BrokerIndexerRow:
    row = BrokerIndexerRow(
        name=data.name.strip(),
        slug=data.slug.strip(),
        kind=data.kind.strip(),
        protocol=data.protocol.strip(),
        privacy=(data.privacy or "public").strip(),
        url=(data.url or "").strip(),
        api_key=(data.api_key or "").strip(),
        enabled=1 if data.enabled else 0,
        priority=int(data.priority),
        categories=_dump_json_list_ints(data.categories),
        tags=_dump_json_list_str(data.tags),
    )
    session.add(row)
    session.flush()
    if row.enabled == 1:
        _enqueue_auto_sync_after_indexer_change(session, indexer_id=int(row.id))
    return row


def update_indexer(session: Session, indexer_id: int, data: BrokerIndexerUpdate) -> BrokerIndexerRow | None:
    row = get_indexer_by_id(session, indexer_id)
    if row is None:
        return None
    prev_enabled = int(row.enabled)
    fields: dict[str, Any] = data.model_dump(exclude_unset=True)
    if "name" in fields and fields["name"] is not None:
        row.name = str(fields["name"]).strip()
    if "slug" in fields and fields["slug"] is not None:
        row.slug = str(fields["slug"]).strip()
    if "kind" in fields and fields["kind"] is not None:
        row.kind = str(fields["kind"]).strip()
    if "protocol" in fields and fields["protocol"] is not None:
        row.protocol = str(fields["protocol"]).strip()
    if "privacy" in fields and fields["privacy"] is not None:
        row.privacy = str(fields["privacy"]).strip()
    if "url" in fields and fields["url"] is not None:
        row.url = str(fields["url"]).strip()
    if "api_key" in fields and fields["api_key"] is not None:
        row.api_key = str(fields["api_key"]).strip()
    if "enabled" in fields and fields["enabled"] is not None:
        row.enabled = 1 if bool(fields["enabled"]) else 0
    if "priority" in fields and fields["priority"] is not None:
        row.priority = int(fields["priority"])
    if "categories" in fields and fields["categories"] is not None:
        row.categories = _dump_json_list_ints(list(fields["categories"]))
    if "tags" in fields and fields["tags"] is not None:
        row.tags = _dump_json_list_str(list(fields["tags"]))
    session.flush()
    next_enabled = int(row.enabled)
    if prev_enabled != next_enabled:
        _enqueue_auto_sync_after_indexer_change(session, indexer_id=int(row.id))
    return row


def delete_indexer(session: Session, indexer_id: int) -> bool:
    row = get_indexer_by_id(session, indexer_id)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True
