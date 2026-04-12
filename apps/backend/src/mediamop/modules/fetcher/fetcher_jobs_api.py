"""Read-only HTTP for persisted ``fetcher_jobs`` rows (module-wide inspection, not failed-import-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from starlette import status

from mediamop.api.deps import DbSessionDep
from mediamop.modules.fetcher.fetcher_jobs_inspection_service import (
    DEFAULT_TERMINAL_STATUSES,
    list_fetcher_jobs_for_inspection,
    validate_inspection_statuses,
)
from mediamop.modules.fetcher.schemas_fetcher_jobs_inspection import FetcherJobsInspectionOut
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["fetcher"])


@router.get("/fetcher/jobs/inspection", response_model=FetcherJobsInspectionOut)
def get_fetcher_jobs_inspection(
    _user: UserPublicDep,
    db: DbSessionDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Max rows to return.")] = 50,
    statuses: Annotated[
        list[str] | None,
        Query(
            alias="status",
            description=(
                "Filter by persisted status (repeat param). "
                "Omit to return only terminal rows: completed, failed, handler_ok_finalize_failed."
            ),
        ),
    ] = None,
) -> FetcherJobsInspectionOut:
    """Fetcher: read-only persisted ``fetcher_jobs`` rows (all job kinds on the Fetcher lane)."""

    if statuses:
        try:
            st = validate_inspection_statuses(tuple(statuses))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return list_fetcher_jobs_for_inspection(
            db,
            limit=limit,
            statuses=st,
            default_terminal_only=False,
        )
    return list_fetcher_jobs_for_inspection(
        db,
        limit=limit,
        statuses=DEFAULT_TERMINAL_STATUSES,
        default_terminal_only=True,
    )
