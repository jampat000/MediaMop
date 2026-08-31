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
    audio_sorters_json: str
    subtitle_sorters_json: str
    keep_original_language: bool
    original_language_additional_csv: str
    original_language_keep_only_first: bool
    original_language_first_if_none: bool
    original_language_treat_empty_as_original: bool
    remove_images: bool
    remove_attachments: bool
    remove_title: bool
    remove_language_tags: bool
    remove_other_metadata: bool
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
    audio_sorters_json: str = Field(
        "",
        description=(
            'Ordered track sorters as JSON: [{"field": "language", "value": "eng"}, '
            '{"field": "channels", "value": ">=5.1"}]. Fields: bitrate, channels, codec, language, '
            'title, default, forced, commentary. Omit "value" to sort by the field itself; "reversed" '
            "flips it. Empty uses the default order, which is what Refiner has always applied."
        ),
    )
    subtitle_sorters_json: str = Field("", description="The same, for subtitle tracks.")
    keep_original_language: bool = Field(
        False,
        description=(
            "Keep the audio in the film's original language instead of following the language preferences. "
            "Needs a metadata provider; without one the preferences decide exactly as before."
        ),
    )
    original_language_additional_csv: str = Field(
        "", max_length=200, description="Extra languages kept alongside the original, comma separated."
    )
    original_language_keep_only_first: bool = Field(
        True, description="Keep only the first track of each kept language."
    )
    original_language_first_if_none: bool = Field(
        True,
        description=(
            "If nothing matches the original language, fall back to the language preferences so the output "
            "still has audio. A safety net rather than a preference."
        ),
    )
    original_language_treat_empty_as_original: bool = Field(
        False, description="Treat a track with no language tag as the original language."
    )
    remove_images: bool = Field(
        False,
        description=(
            "Strip embedded cover art. An embedded poster is carried as a video stream, so this removes a "
            "stream as well as an image."
        ),
    )
    remove_attachments: bool = Field(False, description="Strip attached fonts and similar.")
    remove_title: bool = Field(False, description="Strip the container title, leaving other metadata alone.")
    remove_language_tags: bool = Field(False, description="Strip per-stream language tags.")
    remove_other_metadata: bool = Field(False, description="Strip the remaining container metadata.")
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
    sidecar_patterns_csv: str
    preserve_original_timestamps: bool
    output_collision_policy: str
    hardware_decode_mode: str
    hardware_device: str
    hardware_disabled_vendors_csv: str
    ffmpeg_strictness: str
    file_detection_interval_seconds: int
    ignore_size_changes: bool
    skip_access_tests: bool
    file_system_events_enabled: bool
    schedule_grid: str
    max_attempts: int
    retry_backoff_seconds: int
    retry_execution_failures: bool
    retry_preflight_failures: bool
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
    manager_coverage: str = Field(
        default="no_upstream_signal",
        description="connected, no_upstream_signal, or unreachable; absence of a manager is not an empty queue.",
    )
    manager_coverage_detail: str = Field(default="")
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
    sidecar_patterns_csv: str = Field(
        ".srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png",
        description=(
            "Which files beside the video travel with it to the output, renamed to the output's stem. "
            "Empty migrates nothing — and the source folder deletion would then remove them."
        ),
    )
    preserve_original_timestamps: bool = Field(
        False, description="Give the output the original file's modification time."
    )
    output_collision_policy: Literal["replace", "skip", "keep_both", "replace_if_larger", "replace_if_newer"] = Field(
        "replace",
        description=(
            "What to do when an output already exists at the same path. 'replace' is what MediaMop has "
            "always done. The policy and the decision taken are both recorded on the file, so 'why is there "
            "no new output for this file' is answerable."
        ),
    )
    hardware_decode_mode: Literal["off", "auto", "device"] = Field(
        "off",
        description=(
            "Hardware decoding. 'off' is what MediaMop has always done. A choice that cannot work falls back "
            "to software and records why — it never fails a file."
        ),
    )
    hardware_device: str = Field(
        "", max_length=32, description="The ffmpeg method to use when the mode is 'device' — cuda, qsv, vaapi."
    )
    hardware_disabled_vendors_csv: str = Field(
        "",
        max_length=200,
        description="Vendors to never use, comma separated: nvidia, intel, amd, vaapi, apple.",
    )
    ffmpeg_strictness: Literal["very", "strict", "normal", "unofficial", "experimental"] = Field(
        "normal", description="ffmpeg's -strict level. 'normal' is its own default and passes no flag."
    )
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
    max_attempts: int = Field(
        3, ge=1, le=20, description="How many times MediaMop tries a file on its own before stopping."
    )
    retry_backoff_seconds: int = Field(
        300, ge=1, le=3600, description="The first wait before a retry. It doubles each attempt, capped at an hour."
    )
    retry_execution_failures: bool = Field(
        True,
        description="Retry files that failed while being processed — a dead ffmpeg, a full disk, a dropped share.",
    )
    retry_preflight_failures: bool = Field(
        False,
        description=(
            "Retry files rejected before work started. Off by default: a file with no usable audio will not "
            "have grown one in five minutes."
        ),
    )
    schedule_grid: str = Field(
        "",
        description=(
            "7 days x 96 quarter-hours as 672 characters of 0/1, Monday first. Empty means no restriction. "
            "Work already running finishes when a window closes; the window stops MediaMop starting anything new."
        ),
    )
    file_system_events_enabled: bool = Field(
        True,
        description=(
            "Watch this folder for changes so new files are picked up within seconds. The periodic scan "
            "runs regardless, so switching this off makes MediaMop slower to notice a file, never blind to it."
        ),
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
    processes_before_import: bool = Field(
        default=False,
        description=(
            "Whether the manager processes this library before importing it. When it does, it also "
            "publishes where it expects the finished file."
        ),
    )
    output_path: str | None = Field(
        default=None,
        description="Where the manager expects processed output. Only set when it processes before importing.",
    )
    output_path_problem: str | None = Field(
        default=None, description="Why that output path cannot be used on this machine."
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
