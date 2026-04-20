"""HTTP: read-only ``broker_jobs`` inspection (Broker lane)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from starlette import status

from mediamop.api.deps import DbSessionDep
from mediamop.modules.broker.broker_jobs_inspection_service import (
    list_broker_jobs_for_inspection,
    validate_broker_inspection_statuses,
)
from mediamop.modules.broker.broker_schemas import BrokerJobsInspectionOut
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["broker-jobs"])


@router.get("/jobs", response_model=BrokerJobsInspectionOut)
def get_broker_jobs(
    _user: UserPublicDep,
    db: DbSessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    statuses: Annotated[
        list[str] | None,
        Query(
            alias="status",
            description="Optional filter by persisted status (repeat param).",
        ),
    ] = None,
) -> BrokerJobsInspectionOut:
    if statuses:
        try:
            st = validate_broker_inspection_statuses(tuple(statuses))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return list_broker_jobs_for_inspection(db, limit=limit, statuses=st)
    return list_broker_jobs_for_inspection(db, limit=limit, statuses=None)
