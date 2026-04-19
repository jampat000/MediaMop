from __future__ import annotations

from fastapi import APIRouter

from mediamop.api.deps import DbSessionDep
from mediamop.modules.fetcher.fetcher_overview_stats_service import build_fetcher_overview_stats
from mediamop.modules.fetcher.schemas_fetcher_overview_stats import FetcherOverviewStatsOut
from mediamop.platform.auth.authorization import RequireOperatorDep

router = APIRouter(tags=["fetcher"])


@router.get("/fetcher/overview-stats", response_model=FetcherOverviewStatsOut)
def get_fetcher_overview_stats(
    db: DbSessionDep,
    _user: RequireOperatorDep,
) -> FetcherOverviewStatsOut:
    return build_fetcher_overview_stats(db)
