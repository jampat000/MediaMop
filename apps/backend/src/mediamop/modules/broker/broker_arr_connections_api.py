"""HTTP: Broker *arr connection settings and manual sync under ``/api/v1/broker/connections``."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_job_kinds import (
    BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1,
    BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
)
from mediamop.modules.broker.broker_jobs_ops import broker_enqueue_or_get_job
from mediamop.modules.broker.broker_arr_connections_service import (
    connection_to_api_out,
    get_connection,
    update_connection,
)
from mediamop.modules.broker.broker_schemas import (
    BrokerArrConnectionOut,
    BrokerArrConnectionPutIn,
    BrokerArrConnectionSyncIn,
    BrokerArrConnectionUpdate,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import verify_csrf_token

router = APIRouter(tags=["broker-connections"])

_ALLOWED_ARR = frozenset({"sonarr", "radarr"})


def _csrf(settings: MediaMopSettings, token: str) -> None:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")


def _normalize_arr_type(arr_type: str) -> str:
    s = arr_type.strip().lower()
    if s not in _ALLOWED_ARR:
        raise HTTPException(status_code=404, detail="arr_type must be sonarr or radarr.")
    return s


@router.get("/{arr_type}", response_model=BrokerArrConnectionOut)
def get_broker_connection(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    arr_type: str,
) -> BrokerArrConnectionOut:
    at = _normalize_arr_type(arr_type)
    row = get_connection(db, at)
    return connection_to_api_out(row)


@router.put("/{arr_type}", response_model=BrokerArrConnectionOut)
def put_broker_connection(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    arr_type: str,
    body: BrokerArrConnectionPutIn,
) -> BrokerArrConnectionOut:
    _csrf(settings, body.csrf_token)
    at = _normalize_arr_type(arr_type)
    payload = body.model_dump(exclude_unset=True, exclude={"csrf_token"})
    data = BrokerArrConnectionUpdate.model_validate(payload)
    row = update_connection(db, at, data)
    return connection_to_api_out(row)


@router.post("/{arr_type}/sync", response_model=dict[str, str])
def post_broker_connection_sync(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    arr_type: str,
    body: BrokerArrConnectionSyncIn,
) -> dict[str, str]:
    _csrf(settings, body.csrf_token)
    at = _normalize_arr_type(arr_type)
    kind = (
        BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1 if at == "sonarr" else BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1
    )
    broker_enqueue_or_get_job(
        db,
        dedupe_key=f"broker.sync.manual:{at}:{time.time_ns()}",
        job_kind=kind,
        payload_json=None,
    )
    return {"status": "enqueued", "job_kind": kind}
