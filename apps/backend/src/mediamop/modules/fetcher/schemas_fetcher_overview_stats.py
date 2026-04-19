from __future__ import annotations

from pydantic import BaseModel, Field


class FetcherOverviewStatsOut(BaseModel):
    window_days: int = Field(default=30, ge=1, le=3650)
    sonarr_missing_searches: int = Field(ge=0, description="Completed missing_search.sonarr.monitored_episodes.v1 in window.")
    sonarr_upgrade_searches: int = Field(ge=0, description="Completed upgrade_search.sonarr.cutoff_unmet.v1 in window.")
    radarr_missing_searches: int = Field(ge=0, description="Completed missing_search.radarr.monitored_movies.v1 in window.")
    radarr_upgrade_searches: int = Field(ge=0, description="Completed upgrade_search.radarr.cutoff_unmet.v1 in window.")
    total_searches: int = Field(ge=0)
    failed_jobs: int = Field(
        ge=0,
        description="Terminal-failure search jobs in window (failed + handler_ok_finalize_failed).",
    )
