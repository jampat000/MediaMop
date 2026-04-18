"""HTTP: read-only ``subber_jobs`` inspection (Subber lane)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from starlette import status

from mediamop.api.deps import DbSessionDep
from mediamop.modules.subber.subber_jobs_inspection_service import (
    list_subber_jobs_for_inspection,
    validate_subber_inspection_statuses,
)
from mediamop.modules.subber.subber_schemas import SubberJobsInspectionOut
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["subber-jobs"])


@router.get("/jobs", response_model=SubberJobsInspectionOut)
def get_subber_jobs(
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
) -> SubberJobsInspectionOut:
    if statuses:
        try:
            st = validate_subber_inspection_statuses(tuple(statuses))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return list_subber_jobs_for_inspection(db, limit=limit, statuses=st)
    return list_subber_jobs_for_inspection(db, limit=limit, statuses=None)
