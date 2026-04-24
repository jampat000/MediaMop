"""Pydantic schemas for Subber HTTP APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from mediamop.modules.subber.subber_settings_schema_sections import (
    SubberSettingsAdaptiveOut,
    SubberSettingsAdaptivePut,
    SubberSettingsCoreOut,
    SubberSettingsCorePut,
    SubberSettingsMoviesScheduleOut,
    SubberSettingsMoviesSchedulePut,
    SubberSettingsOpensubtitlesOut,
    SubberSettingsOpensubtitlesPut,
    SubberSettingsRadarrOut,
    SubberSettingsRadarrPut,
    SubberSettingsSonarrOut,
    SubberSettingsSonarrPut,
    SubberSettingsTvScheduleOut,
    SubberSettingsTvSchedulePut,
    SubberSettingsUpgradeOut,
    SubberSettingsUpgradePut,
)


class SubberJobsInspectionRow(BaseModel):
    id: int
    dedupe_key: str
    job_kind: str
    status: str
    scope: str | None = None
    payload_json: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SubberJobsInspectionOut(BaseModel):
    jobs: list[SubberJobsInspectionRow]
    default_recent_slice: bool


class SubberSubtitleLangStateOut(BaseModel):
    state_id: int
    language_code: str
    status: str
    subtitle_path: str | None = None
    last_searched_at: datetime | None = None
    search_count: int
    source: str | None = None
    provider_key: str | None = None
    upgrade_count: int = 0


class SubberTvEpisodeOut(BaseModel):
    file_path: str
    episode_number: int | None
    episode_title: str | None
    languages: list[SubberSubtitleLangStateOut]


class SubberTvSeasonOut(BaseModel):
    season_number: int | None
    episodes: list[SubberTvEpisodeOut]


class SubberTvShowOut(BaseModel):
    show_title: str
    seasons: list[SubberTvSeasonOut]


class SubberTvLibraryOut(BaseModel):
    shows: list[SubberTvShowOut]
    total: int = Field(0, description="Total episodes matching filters (before limit/offset).")


class SubberMovieRowOut(BaseModel):
    file_path: str
    movie_title: str | None
    movie_year: int | None
    languages: list[SubberSubtitleLangStateOut]


class SubberMoviesLibraryOut(BaseModel):
    movies: list[SubberMovieRowOut]
    total: int = Field(0, description="Total movies matching filters (before limit/offset).")


class SubberSettingsOut(
    SubberSettingsCoreOut,
    SubberSettingsOpensubtitlesOut,
    SubberSettingsSonarrOut,
    SubberSettingsRadarrOut,
    SubberSettingsTvScheduleOut,
    SubberSettingsMoviesScheduleOut,
    SubberSettingsAdaptiveOut,
    SubberSettingsUpgradeOut,
):
    """Aggregated Subber settings (flat JSON for ``GET /api/v1/subber/settings``)."""


class SubberSettingsPutIn(
    SubberSettingsCorePut,
    SubberSettingsOpensubtitlesPut,
    SubberSettingsSonarrPut,
    SubberSettingsRadarrPut,
    SubberSettingsTvSchedulePut,
    SubberSettingsMoviesSchedulePut,
    SubberSettingsAdaptivePut,
    SubberSettingsUpgradePut,
):
    """Partial update body for ``PUT /api/v1/subber/settings`` (flat JSON)."""


class SubberTestConnectionOut(BaseModel):
    ok: bool
    message: str


class SubberArrRootFolderOut(BaseModel):
    path: str
    free_space: int | None = None


class SubberArrRootFoldersOut(BaseModel):
    ok: bool
    message: str
    folders: list[SubberArrRootFolderOut] = Field(default_factory=list)


class SubberOverviewOut(BaseModel):
    window_days: int = 30
    subtitles_downloaded: int = Field(ge=0, description="Rows in subber_subtitle_state with status=found.")
    still_missing: int = Field(ge=0)
    skipped: int = Field(ge=0)
    tv_tracked: int = Field(ge=0, description="Rows with media_scope=tv.")
    movies_tracked: int = Field(ge=0, description="Rows with media_scope=movies.")
    tv_found: int = Field(ge=0)
    movies_found: int = Field(ge=0)
    tv_missing: int = Field(ge=0)
    movies_missing: int = Field(ge=0)
    searches_last_30_days: int = Field(ge=0)
    found_last_30_days: int = Field(ge=0, description="subtitle_search_completed with detail ok=true.")
    not_found_last_30_days: int = Field(ge=0, description="subtitle_search_completed with detail ok=false.")
    upgrades_last_30_days: int = Field(ge=0, description="Sum of upgraded from subtitle_upgrade_completed detail.")


class SubberProviderOut(BaseModel):
    provider_key: str
    display_name: str
    enabled: bool
    priority: int | None = None
    requires_account: bool
    has_credentials: bool


class SubberProviderPutIn(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
