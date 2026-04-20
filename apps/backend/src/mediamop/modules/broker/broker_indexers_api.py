"""HTTP: Broker indexer CRUD under ``/api/v1/broker/indexers``."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_job_kinds import BROKER_JOB_KIND_INDEXER_TEST_V1
from mediamop.modules.broker.broker_jobs_ops import broker_enqueue_or_get_job
from mediamop.modules.broker.broker_indexers_service import (
    create_indexer,
    delete_indexer,
    get_all_indexers,
    get_indexer_by_id,
    indexer_to_api_out,
    update_indexer,
)
from mediamop.modules.broker.broker_schemas import (
    BrokerIndexerCreate,
    BrokerIndexerOut,
    BrokerIndexerTestEnqueueIn,
    BrokerIndexerUpdate,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import verify_csrf_token

router = APIRouter(tags=["broker-indexers"])


class BrokerIndexerCreateHttpIn(BrokerIndexerCreate):
    csrf_token: str = Field(..., min_length=1)


class BrokerIndexerPutHttpIn(BrokerIndexerUpdate):
    csrf_token: str = Field(..., min_length=1)


def _csrf(settings: MediaMopSettings, token: str) -> None:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")


@router.get("", response_model=list[BrokerIndexerOut])
def list_broker_indexers(
    _user: RequireOperatorDep,
    db: DbSessionDep,
) -> list[BrokerIndexerOut]:
    return [indexer_to_api_out(r) for r in get_all_indexers(db)]


@router.post("", response_model=BrokerIndexerOut)
def post_broker_indexer(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    body: BrokerIndexerCreateHttpIn,
) -> BrokerIndexerOut:
    _csrf(settings, body.csrf_token)
    payload = body.model_dump(exclude={"csrf_token"})
    create = BrokerIndexerCreate.model_validate(payload)
    row = create_indexer(db, create)
    return indexer_to_api_out(row)


@router.get("/{indexer_id}", response_model=BrokerIndexerOut)
def get_broker_indexer(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    indexer_id: int,
) -> BrokerIndexerOut:
    row = get_indexer_by_id(db, indexer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown indexer id.")
    return indexer_to_api_out(row)


@router.put("/{indexer_id}", response_model=BrokerIndexerOut)
def put_broker_indexer(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    indexer_id: int,
    body: BrokerIndexerPutHttpIn,
) -> BrokerIndexerOut:
    _csrf(settings, body.csrf_token)
    payload = body.model_dump(exclude_unset=True, exclude={"csrf_token"})
    update = BrokerIndexerUpdate.model_validate(payload)
    row = update_indexer(db, indexer_id, update)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown indexer id.")
    return indexer_to_api_out(row)


@router.delete("/{indexer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_broker_indexer(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    indexer_id: int,
) -> None:
    ok = delete_indexer(db, indexer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown indexer id.")


@router.post("/{indexer_id}/test", response_model=dict[str, str])
def post_broker_indexer_test(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    indexer_id: int,
    body: BrokerIndexerTestEnqueueIn,
) -> dict[str, str]:
    _csrf(settings, body.csrf_token)
    row = get_indexer_by_id(db, indexer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown indexer id.")
    broker_enqueue_or_get_job(
        db,
        dedupe_key=f"broker.indexer.test:{indexer_id}:{time.time_ns()}",
        job_kind=BROKER_JOB_KIND_INDEXER_TEST_V1,
        payload_json=json.dumps({"indexer_id": indexer_id}),
    )
    return {"status": "enqueued"}
