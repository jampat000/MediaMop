from __future__ import annotations

from fastapi import APIRouter, Query

from mediamop.api.deps import DbSessionDep
from mediamop.modules.refiner.refiner_overview_stats_service import build_refiner_overview_stats
from mediamop.modules.refiner.schemas_refiner_overview_stats import RefinerOverviewStatsOut
from mediamop.platform.auth.authorization import RequireOperatorDep

router = APIRouter(tags=["refiner"])


@router.get("/refiner/overview-stats", response_model=RefinerOverviewStatsOut)
def get_refiner_overview_stats(
    db: DbSessionDep,
    _user: RequireOperatorDep,
    window_days: int = Query(
        default=30,
        ge=1,
        le=3650,
        description="How far back to count. Pass 1 for 'today' on the custody screen.",
    ),
) -> RefinerOverviewStatsOut:
    # The builder already took a window; only the route was fixed at 30 days.
    return build_refiner_overview_stats(db, window_days=window_days)
