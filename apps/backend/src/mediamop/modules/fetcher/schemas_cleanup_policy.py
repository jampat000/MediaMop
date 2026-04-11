"""Pydantic schemas for Fetcher failed-import cleanup policy API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mediamop.modules.arr_failed_import.env_settings import AppFailedImportCleanupPolicySettings


class FailedImportCleanupPolicyAxisOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remove_quality_rejections: bool
    remove_unmatched_manual_import_rejections: bool
    remove_corrupt_imports: bool
    remove_failed_downloads: bool
    remove_failed_imports: bool


class FetcherFailedImportCleanupPolicyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movies: FailedImportCleanupPolicyAxisOut = Field(description="Radarr (movies) removal rules.")
    tv_shows: FailedImportCleanupPolicyAxisOut = Field(description="Sonarr (TV) removal rules.")
    updated_at: datetime = Field(description="When this row was last written (including initial seed).")


class FailedImportCleanupPolicyAxisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remove_quality_rejections: bool
    remove_unmatched_manual_import_rejections: bool
    remove_corrupt_imports: bool
    remove_failed_downloads: bool
    remove_failed_imports: bool

    def to_app_settings(self) -> AppFailedImportCleanupPolicySettings:
        return AppFailedImportCleanupPolicySettings(
            remove_quality_rejections=self.remove_quality_rejections,
            remove_unmatched_manual_import_rejections=self.remove_unmatched_manual_import_rejections,
            remove_corrupt_imports=self.remove_corrupt_imports,
            remove_failed_downloads=self.remove_failed_downloads,
            remove_failed_imports=self.remove_failed_imports,
        )


class FetcherFailedImportCleanupPolicyPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movies: FailedImportCleanupPolicyAxisIn
    tv_shows: FailedImportCleanupPolicyAxisIn
    csrf_token: str
