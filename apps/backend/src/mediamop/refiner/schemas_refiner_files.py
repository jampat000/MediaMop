"""Request and response shapes for the Refiner Files screen."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RefinerFileStatusName = Literal[
    "unprocessed",
    "processing",
    "processed",
    "processing_failed",
    "skipped",
    "disabled",
    "on_hold",
    "out_of_schedule",
    "blocked_upstream",
]


class DirectPlayOut(BaseModel):
    device_id: str
    device_name: str
    verdict: str = Field(description="yes, no, maybe (partial or model-dependent support), or unknown (not measured).")
    reasons: list[str] = Field(default_factory=list)


class DirectPlayDeviceOut(BaseModel):
    id: str
    name: str
    source: str = Field(description="Where this device's capabilities come from.")
    note: str
    selected: bool


class DirectPlayDevicesOut(BaseModel):
    devices: list[DirectPlayDeviceOut]
    customised: bool = Field(description="True when the list comes from the operator's own direct-play-devices.json.")


class DirectPlayDevicesIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)
    selected: list[str] = Field(default_factory=list, max_length=100)


class RefinerFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    library_id: int
    library_name: str
    relative_path: str
    status: RefinerFileStatusName
    status_reason: str = Field(description="Why the file is in this state, written for the person reading it.")
    blocked_by_connection: str | None = Field(
        default=None,
        description="The media manager connection holding this file, when the status is blocked_upstream.",
    )
    size_bytes: int
    # What the file actually is, measured at the last probe. Null means not probed yet, which
    # is deliberately distinct from a real zero.
    video_codec: str | None = Field(default=None, description="Video codec as ffprobe named it, e.g. hevc.")
    video_width: int | None = Field(default=None, description="Measured width in pixels.")
    video_height: int | None = Field(default=None, description="Measured height in pixels.")
    audio_track_count: int | None = Field(default=None, description="How many audio tracks the file carries.")
    subtitle_track_count: int | None = Field(default=None, description="How many subtitle tracks the file carries.")
    duration_seconds: float | None = Field(default=None, description="Runtime in seconds, as probed.")
    direct_play: list[DirectPlayOut] = Field(
        default_factory=list,
        description=(
            "For each device the operator owns: will it play this file without conversion. Information only; "
            "it never changes how MediaMop processes the file. Empty when no devices are chosen."
        ),
    )
    progress_percent: float | None = Field(
        default=None,
        description="How far the current pass has got, when one is running. Null when nothing is in flight.",
    )
    progress_message: str | None = Field(
        default=None,
        description="What the running pass is doing, in the words it reported.",
    )
    progress_eta_seconds: float | None = Field(
        default=None,
        description="The running pass's own estimate of the time left, when it has one.",
    )
    failure_class: str | None = Field(
        default=None,
        description="Why this file failed, in terms a retry policy acts on: preflight, execution, guardrail, unknown.",
    )
    failure_attempts: int = 0
    quarantined: bool = Field(
        default=False,
        description="True when repeated failures placed this file on hold until an operator requeues it.",
    )
    next_retry_at: datetime | None = Field(
        default=None,
        description="When MediaMop will try this file again on its own. Null when no automatic retry is coming.",
    )
    output_collision_policy: str | None = Field(
        default=None,
        description="The collision policy in force when this file's output was written.",
    )
    output_collision_action: str | None = Field(default=None, description="What that policy decided: write, or skip.")
    output_collision_reason: str | None = Field(
        default=None,
        description="Why, written for the person asking why there is no new output for this file.",
    )
    hold_until: datetime | None = Field(
        default=None,
        description=(
            "When an on-hold file becomes eligible. Null when the hold is waiting on a writer to stop "
            "rather than on the clock."
        ),
    )
    size_changed_at: datetime | None = Field(
        default=None,
        description="When this file's size last changed, as observed across scans.",
    )
    created_at: datetime = Field(description="When MediaMop first recorded this file.")
    updated_at: datetime = Field(description="When this file row was last changed.")
    last_seen_at: datetime | None = None
    last_attempt_at: datetime | None = None


class RefinerFilesPageOut(BaseModel):
    """A page of files plus the bucket counts shown above them."""

    files: list[RefinerFileOut]
    status_counts: dict[str, int]
    returned: int
    limit: int


class RefinerFileMoveToTopOut(BaseModel):
    """What happened, said in words the screen can show unchanged."""

    moved: bool
    detail: str


class RefinerFileForgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class RefinerFileMoveToTopIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class RefinerFileRequeueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class RefinerFilesBulkRequeueIn(BaseModel):
    """Requeue everything matching a filter, described the same way the list is filtered."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    library_id: int | None = Field(default=None, ge=1)
    file_status: RefinerFileStatusName | None = None
    path_contains: str | None = Field(default=None, max_length=500)
    limit: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="A ceiling on how many are queued in one go, so a mis-typed filter cannot queue a whole library.",
    )


class RefinerRequeueOut(BaseModel):
    requeued: int
    skipped: int
    detail: str


class RefinerFileStoryStepOut(BaseModel):
    """One plain-language step in what happened to a file, built from the stored pass record."""

    heading: str
    sentence: str
    tone: str = Field(description="neutral, good, warn or bad — how the step should read, not a severity.")


class RefinerFileLogEntryOut(BaseModel):
    """One completed pass over this file."""

    id: int
    recorded_at: datetime
    outcome: str
    title: str
    library_name: str
    detail: dict[str, object] = Field(
        default_factory=dict,
        description="The whole pass payload: admission decisions, probe, plan, ffmpeg argv, cleanup gates, timings.",
    )
    story: list[RefinerFileStoryStepOut] = Field(
        default_factory=list,
        description=(
            "The same pass told in plain language. Rebuilt from the stored record on every request, "
            "so improving the wording improves past entries too."
        ),
    )


class RefinerFileLogOut(BaseModel):
    file_id: int
    relative_path: str
    retention_days: int = Field(
        description="How long these records are kept. 0 means they are kept forever.",
    )
    entries: list[RefinerFileLogEntryOut]
