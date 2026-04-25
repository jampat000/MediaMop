"""GET/PUT /api/v1/refiner/operator-settings."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RefinerOperatorSettingsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrent_files: int = Field(ge=1, le=8)
    min_file_age_seconds: int = Field(ge=0, le=7 * 24 * 3600)
    movie_schedule_enabled: bool
    movie_schedule_hours_limited: bool = Field(
        description="When true, timed movie scans only enqueue inside the days and times below (suite time zone).",
    )
    movie_schedule_days: str = Field(max_length=2000)
    movie_schedule_start: str = Field(max_length=5)
    movie_schedule_end: str = Field(max_length=5)
    tv_schedule_enabled: bool
    tv_schedule_hours_limited: bool
    tv_schedule_days: str = Field(max_length=2000)
    tv_schedule_start: str = Field(max_length=5)
    tv_schedule_end: str = Field(max_length=5)
    schedule_timezone: str = Field(description="IANA zone for schedule windows (suite settings).")
    updated_at: str


class RefinerOperatorSettingsPutIn(BaseModel):
    """PUT body supports partial updates: omit a group to leave it unchanged on the server."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    max_concurrent_files: int | None = Field(default=None, ge=1, le=8)
    min_file_age_seconds: int | None = Field(default=None, ge=0, le=7 * 24 * 3600)
    movie_schedule_enabled: bool | None = None
    movie_schedule_hours_limited: bool | None = None
    movie_schedule_days: str | None = Field(default=None, max_length=2000)
    movie_schedule_start: str | None = Field(default=None, max_length=5)
    movie_schedule_end: str | None = Field(default=None, max_length=5)
    tv_schedule_enabled: bool | None = None
    tv_schedule_hours_limited: bool | None = None
    tv_schedule_days: str | None = Field(default=None, max_length=2000)
    tv_schedule_start: str | None = Field(default=None, max_length=5)
    tv_schedule_end: str | None = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def _movie_schedule_all_or_nothing(self) -> RefinerOperatorSettingsPutIn:
        keys = (
            self.movie_schedule_enabled,
            self.movie_schedule_hours_limited,
            self.movie_schedule_days,
            self.movie_schedule_start,
            self.movie_schedule_end,
        )
        present = sum(1 for v in keys if v is not None)
        if present not in (0, len(keys)):
            raise ValueError(
                "Refiner movie schedule fields must all be omitted or all provided together.",
            )
        return self

    @model_validator(mode="after")
    def _tv_schedule_all_or_nothing(self) -> RefinerOperatorSettingsPutIn:
        keys = (
            self.tv_schedule_enabled,
            self.tv_schedule_hours_limited,
            self.tv_schedule_days,
            self.tv_schedule_start,
            self.tv_schedule_end,
        )
        present = sum(1 for v in keys if v is not None)
        if present not in (0, len(keys)):
            raise ValueError(
                "Refiner TV schedule fields must all be omitted or all provided together.",
            )
        return self

    @model_validator(mode="after")
    def _at_least_one_update_field(self) -> RefinerOperatorSettingsPutIn:
        has_process = self.max_concurrent_files is not None or self.min_file_age_seconds is not None
        has_movie = self.movie_schedule_enabled is not None
        has_tv = self.tv_schedule_enabled is not None
        if not (has_process or has_movie or has_tv):
            raise ValueError("No Refiner operator settings fields to update.")
        return self
