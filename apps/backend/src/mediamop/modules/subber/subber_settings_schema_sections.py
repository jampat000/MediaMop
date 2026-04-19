"""Composable Pydantic sections for Subber singleton settings.

The HTTP JSON for ``GET``/``PUT`` ``/api/v1/subber/settings`` stays a **flat** object; these
models only split the schema for clearer code and OpenAPI grouping.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SubberSettingsCoreOut(BaseModel):
    enabled: bool
    language_preferences: list[str]
    subtitle_folder: str
    exclude_hearing_impaired: bool = False


class SubberSettingsOpensubtitlesOut(BaseModel):
    opensubtitles_username: str
    opensubtitles_password_set: bool
    opensubtitles_api_key_set: bool


class SubberSettingsSonarrOut(BaseModel):
    sonarr_base_url: str
    sonarr_api_key_set: bool
    sonarr_path_mapping_enabled: bool = False
    sonarr_path_sonarr: str = ""
    sonarr_path_subber: str = ""
    fetcher_sonarr_base_url_hint: str = ""


class SubberSettingsRadarrOut(BaseModel):
    radarr_base_url: str
    radarr_api_key_set: bool
    radarr_path_mapping_enabled: bool = False
    radarr_path_radarr: str = ""
    radarr_path_subber: str = ""
    fetcher_radarr_base_url_hint: str = ""


class SubberSettingsTvScheduleOut(BaseModel):
    tv_schedule_enabled: bool
    tv_schedule_interval_seconds: int
    tv_schedule_hours_limited: bool
    tv_schedule_days: str
    tv_schedule_start: str
    tv_schedule_end: str
    tv_last_scheduled_scan_enqueued_at: datetime | None = None


class SubberSettingsMoviesScheduleOut(BaseModel):
    movies_schedule_enabled: bool
    movies_schedule_interval_seconds: int
    movies_schedule_hours_limited: bool
    movies_schedule_days: str
    movies_schedule_start: str
    movies_schedule_end: str
    movies_last_scheduled_scan_enqueued_at: datetime | None = None


class SubberSettingsAdaptiveOut(BaseModel):
    adaptive_searching_enabled: bool = True
    adaptive_searching_delay_hours: int = 168
    adaptive_searching_max_attempts: int = 3
    permanent_skip_after_attempts: int = 10


class SubberSettingsUpgradeOut(BaseModel):
    upgrade_enabled: bool = False
    upgrade_schedule_enabled: bool = False
    upgrade_schedule_interval_seconds: int = 604800
    upgrade_schedule_hours_limited: bool = False
    upgrade_schedule_days: str = ""
    upgrade_schedule_start: str = "00:00"
    upgrade_schedule_end: str = "23:59"
    upgrade_last_scheduled_at: datetime | None = None


class SubberSettingsCorePut(BaseModel):
    enabled: bool | None = None
    language_preferences: list[str] | None = None
    subtitle_folder: str | None = None
    exclude_hearing_impaired: bool | None = None


class SubberSettingsOpensubtitlesPut(BaseModel):
    opensubtitles_username: str | None = None
    opensubtitles_password: str | None = None
    opensubtitles_api_key: str | None = None


class SubberSettingsSonarrPut(BaseModel):
    sonarr_base_url: str | None = None
    sonarr_api_key: str | None = None
    sonarr_path_mapping_enabled: bool | None = None
    sonarr_path_sonarr: str | None = None
    sonarr_path_subber: str | None = None


class SubberSettingsRadarrPut(BaseModel):
    radarr_base_url: str | None = None
    radarr_api_key: str | None = None
    radarr_path_mapping_enabled: bool | None = None
    radarr_path_radarr: str | None = None
    radarr_path_subber: str | None = None


class SubberSettingsTvSchedulePut(BaseModel):
    tv_schedule_enabled: bool | None = None
    tv_schedule_interval_seconds: int | None = Field(None, ge=60, le=7 * 24 * 3600)
    tv_schedule_hours_limited: bool | None = None
    tv_schedule_days: str | None = None
    tv_schedule_start: str | None = None
    tv_schedule_end: str | None = None


class SubberSettingsMoviesSchedulePut(BaseModel):
    movies_schedule_enabled: bool | None = None
    movies_schedule_interval_seconds: int | None = Field(None, ge=60, le=7 * 24 * 3600)
    movies_schedule_hours_limited: bool | None = None
    movies_schedule_days: str | None = None
    movies_schedule_start: str | None = None
    movies_schedule_end: str | None = None


class SubberSettingsAdaptivePut(BaseModel):
    adaptive_searching_enabled: bool | None = None
    adaptive_searching_delay_hours: int | None = Field(None, ge=1, le=24 * 365)
    adaptive_searching_max_attempts: int | None = Field(None, ge=1, le=1000)
    permanent_skip_after_attempts: int | None = Field(None, ge=1, le=100_000)


class SubberSettingsUpgradePut(BaseModel):
    upgrade_enabled: bool | None = None
    upgrade_schedule_enabled: bool | None = None
    upgrade_schedule_interval_seconds: int | None = Field(None, ge=60, le=365 * 24 * 3600)
    upgrade_schedule_hours_limited: bool | None = None
    upgrade_schedule_days: str | None = None
    upgrade_schedule_start: str | None = None
    upgrade_schedule_end: str | None = None
