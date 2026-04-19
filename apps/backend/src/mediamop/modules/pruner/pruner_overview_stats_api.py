from __future__ import annotations

from fastapi import APIRouter

from mediamop.api.deps import DbSessionDep
from mediamop.modules.pruner.pruner_overview_stats_service import build_pruner_overview_stats
from mediamop.modules.pruner.schemas_pruner_overview_stats import PrunerOverviewStatsOut
from mediamop.platform.auth.authorization import RequireOperatorDep

router = APIRouter(tags=["pruner"])


@router.get("/pruner/overview-stats", response_model=PrunerOverviewStatsOut)
def get_pruner_overview_stats(
    db: DbSessionDep,
    _user: RequireOperatorDep,
) -> PrunerOverviewStatsOut:
    return build_pruner_overview_stats(db)
