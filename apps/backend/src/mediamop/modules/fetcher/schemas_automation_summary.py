"""Read-only Fetcher failed-import automation summary (persisted jobs + saved settings only)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FetcherFailedImportAxisSummaryOut(BaseModel):
    """Movies (Radarr) or TV (Sonarr) — separate axes."""

    last_finished_at: datetime | None = Field(
        default=None,
        description="When this pass last reached a finished state in the database, if any.",
    )
    last_outcome_label: str = Field(
        description="Plain outcome for the last finished pass, or an honest empty-history line.",
    )
    saved_schedule_primary: str = Field(
        description="Saved schedule intent (interval or off) — not a predicted wall-clock next run.",
    )
    saved_schedule_secondary: str | None = Field(
        default=None,
        description="Honest caveat tying schedule wording to settings and automation activity.",
    )


class FetcherFailedImportAutomationSummaryOut(BaseModel):
    """Bounded read model for the Fetcher page automation strip."""

    scope_note: str = Field(
        description="Top caveat: persisted rows and saved settings only — not live apps or runner health.",
    )
    automation_slots_note: str | None = Field(
        default=None,
        description="When worker count is 0, a single honest line about timed passes not starting alone.",
    )
    movies: FetcherFailedImportAxisSummaryOut
    tv_shows: FetcherFailedImportAxisSummaryOut
