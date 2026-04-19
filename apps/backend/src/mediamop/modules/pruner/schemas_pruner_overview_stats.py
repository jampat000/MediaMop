from __future__ import annotations

from pydantic import BaseModel, Field


class PrunerOverviewStatsOut(BaseModel):
    window_days: int = Field(default=30, ge=1, le=3650)
    items_removed: int = Field(ge=0, description="Sum of removed from apply completion detail JSON in window.")
    items_skipped: int = Field(ge=0, description="Sum of skipped from apply completion detail JSON in window.")
    apply_runs: int = Field(ge=0, description="pruner.apply_library_removal_completed events in window.")
    preview_runs: int = Field(ge=0, description="Completed pruner.candidate_removal.preview.v1 jobs in window.")
    failed_applies: int = Field(ge=0, description="pruner.apply_library_removal_failed events in window.")
