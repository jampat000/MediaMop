"""Request and response shapes for Refiner libraries and rule sets."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MediaScope = Literal["movie", "tv"]


class RefinerRuleSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    primary_audio_lang: str
    secondary_audio_lang: str
    tertiary_audio_lang: str
    default_audio_slot: str
    remove_commentary: bool
    subtitle_mode: str
    subtitle_langs_csv: str
    preserve_forced_subs: bool
    preserve_default_subs: bool
    audio_preference_mode: str
    used_by_library_count: int = Field(
        default=0, description="How many libraries reference this rule set. Deleting one still in use is refused."
    )
    updated_at: datetime | None = None


class RefinerRuleSetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=120)
    primary_audio_lang: str = Field("", max_length=24)
    secondary_audio_lang: str = Field("", max_length=24)
    tertiary_audio_lang: str = Field("", max_length=24)
    default_audio_slot: Literal["primary", "secondary", "tertiary"] = "primary"
    remove_commentary: bool = False
    subtitle_mode: Literal["keep_all", "keep_listed", "remove_all"] = "keep_all"
    subtitle_langs_csv: str = Field("", max_length=500)
    preserve_forced_subs: bool = True
    preserve_default_subs: bool = True
    audio_preference_mode: Literal["preferred_langs_quality", "preferred_langs_strict", "quality_all_languages"] = (
        "preferred_langs_quality"
    )


class RefinerLibraryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    media_scope: MediaScope
    display_order: int

    watched_folder: str
    work_folder: str
    output_folder: str

    media_extensions_csv: str
    exclude_markers_csv: str
    include_patterns_csv: str
    exclude_patterns_csv: str
    min_file_size_mb: int
    max_file_size_mb: int
    min_file_age_seconds: int
    exclude_hidden: bool
    top_level_only: bool

    scan_interval_seconds: int
    hold_minutes: int
    file_detection_interval_seconds: int
    ignore_size_changes: bool
    skip_access_tests: bool
    schedule_enabled: bool
    schedule_hours_limited: bool
    schedule_days: str
    schedule_start: str
    schedule_end: str

    max_concurrent_files: int
    priority: int

    rule_set_id: int | None = None
    manager_connection_ids: list[int] = Field(
        default_factory=list,
        description="Media manager connections covering this library. More than one is allowed and is the edge case.",
    )
    discovered_from_connection_id: int | None = None
    discovered_library_key: str | None = None
    active_job_count: int = Field(
        default=0,
        description="Queued or running Refiner jobs for this library. Deletion is refused while this is non-zero.",
    )
    updated_at: datetime | None = None


class RefinerLibraryCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=120)
    media_scope: MediaScope
    enabled: bool = True
    watched_folder: str = Field("", max_length=4000)
    work_folder: str = Field("", max_length=4000)
    output_folder: str = Field("", max_length=4000)
    media_extensions_csv: str = Field("", max_length=1000)
    exclude_markers_csv: str = Field("", max_length=1000)
    include_patterns_csv: str = Field("", max_length=1000)
    exclude_patterns_csv: str = Field("", max_length=1000)
    min_file_size_mb: int = Field(0, ge=0, le=1_000_000)
    max_file_size_mb: int = Field(0, ge=0, le=1_000_000)
    min_file_age_seconds: int = Field(60, ge=0, le=604800)
    exclude_hidden: bool = True
    top_level_only: bool = False
    scan_interval_seconds: int = Field(300, ge=10, le=604800)
    hold_minutes: int = Field(0, ge=0, le=10080)
    file_detection_interval_seconds: int = Field(
        30,
        ge=0,
        le=3600,
        description=(
            "How long this file's size must stay unchanged before MediaMop treats it as finished being "
            "written. 0 turns size settling off."
        ),
    )
    ignore_size_changes: bool = Field(False, description="Skip size settling entirely for this library.")
    skip_access_tests: bool = Field(
        False,
        description="Skip the read/write probe that runs before a file is queued.",
    )
    schedule_enabled: bool = True
    schedule_hours_limited: bool = False
    schedule_days: str = Field("", max_length=200)
    schedule_start: str = Field("00:00", max_length=5)
    schedule_end: str = Field("23:59", max_length=5)
    max_concurrent_files: int = Field(1, ge=1, le=8)
    priority: int = Field(0, ge=-100, le=100)
    rule_set_id: int | None = None
    manager_connection_ids: list[int] = Field(default_factory=list)


class RefinerLibraryUpdateIn(RefinerLibraryCreateIn):
    """Same shape as create. A library is edited whole, so a partial save cannot half-apply."""


class RefinerLibraryDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class RefinerLibraryReorderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    library_ids_in_order: list[int] = Field(..., min_length=1)


class DiscoverableLibraryOut(BaseModel):
    """One library a connected manager reports."""

    key: str = Field(description="The manager's own id, kept only as an integration reference.")
    name: str
    media_scope: MediaScope | None = None
    root_path: str | None = Field(
        default=None, description="Where the manager sees this library, on the manager's host."
    )
    already_imported: bool
    local_path_problem: str | None = Field(
        default=None,
        description="Why that path cannot be used on this machine, shown beside the manager's value.",
    )


class RefinerLibraryImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    keys: list[str] = Field(..., min_length=1, description="Manager library ids to import.")


class LibraryDriftOut(BaseModel):
    """A difference between the manager and MediaMop. Reported, never applied."""

    kind: Literal["root_moved", "library_removed", "library_added", "path_not_local"]
    library_id: int | None = None
    library_name: str
    manager_value: str | None = None
    mediamop_value: str | None = None
    detail: str
