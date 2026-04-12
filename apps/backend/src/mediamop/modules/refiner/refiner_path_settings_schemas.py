"""HTTP schemas for Refiner path settings (singleton row)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RefinerPathSettingsOut(BaseModel):
    refiner_watched_folder: str | None
    refiner_work_folder: str | None
    refiner_output_folder: str
    resolved_default_work_folder: str
    effective_work_folder: str
    updated_at: datetime


class RefinerPathSettingsPutIn(BaseModel):
    refiner_watched_folder: str | None = None
    refiner_work_folder: str | None = None
    refiner_output_folder: str = Field(..., min_length=1)
    csrf_token: str = Field(..., min_length=1)
