"""Authenticated Fetcher operational routes (overview, failed-import workflow, jobs inspection, Arr search)."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.fetcher.failed_imports_api import router as fetcher_failed_imports_router
from mediamop.modules.fetcher.fetcher_arr_search_api import router as fetcher_arr_search_router
from mediamop.modules.fetcher.fetcher_jobs_api import router as fetcher_jobs_router
from mediamop.modules.fetcher.schemas import FetcherOperationalOverviewOut
from mediamop.modules.fetcher.service import build_fetcher_operational_overview
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["fetcher"])
router.include_router(fetcher_jobs_router)
router.include_router(fetcher_arr_search_router)
router.include_router(fetcher_failed_imports_router)


@router.get("/fetcher/overview", response_model=FetcherOperationalOverviewOut)
def get_fetcher_operational_overview(
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> FetcherOperationalOverviewOut:
    """Read-only Fetcher operational slice for current status and recent probe signals."""

    return build_fetcher_operational_overview(db, settings)
