from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob, FetcherJobStatus
from mediamop.modules.fetcher.fetcher_search_job_kinds import (
    JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
    JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
    JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
    JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
)
from mediamop.modules.fetcher.schemas_fetcher_overview_stats import FetcherOverviewStatsOut

_FETCHER_SEARCH_JOB_KINDS = (
    JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1,
    JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1,
    JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1,
    JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1,
)


def build_fetcher_overview_stats(db: Session, *, window_days: int = 30) -> FetcherOverviewStatsOut:
    wd = max(1, int(window_days))
    since = datetime.now(timezone.utc) - timedelta(days=wd)

    def _completed_count(job_kind: str) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(FetcherJob)
                .where(
                    FetcherJob.job_kind == job_kind,
                    FetcherJob.status == FetcherJobStatus.COMPLETED.value,
                    FetcherJob.updated_at >= since,
                ),
            )
            or 0,
        )

    son_m = _completed_count(JOB_KIND_MISSING_SEARCH_SONARR_MONITORED_EPISODES_V1)
    son_u = _completed_count(JOB_KIND_UPGRADE_SEARCH_SONARR_CUTOFF_UNMET_V1)
    rad_m = _completed_count(JOB_KIND_MISSING_SEARCH_RADARR_MONITORED_MOVIES_V1)
    rad_u = _completed_count(JOB_KIND_UPGRADE_SEARCH_RADARR_CUTOFF_UNMET_V1)
    total = son_m + son_u + rad_m + rad_u

    failed = int(
        db.scalar(
            select(func.count())
            .select_from(FetcherJob)
            .where(
                FetcherJob.job_kind.in_(_FETCHER_SEARCH_JOB_KINDS),
                FetcherJob.status.in_(
                    (
                        FetcherJobStatus.FAILED.value,
                        FetcherJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
                    ),
                ),
                FetcherJob.updated_at >= since,
            ),
        )
        or 0,
    )

    return FetcherOverviewStatsOut(
        window_days=wd,
        sonarr_missing_searches=son_m,
        sonarr_upgrade_searches=son_u,
        radarr_missing_searches=rad_m,
        radarr_upgrade_searches=rad_u,
        total_searches=total,
        failed_jobs=failed,
    )
