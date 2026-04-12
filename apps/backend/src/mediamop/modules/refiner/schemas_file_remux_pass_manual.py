"""Manual enqueue for ``refiner.file.remux_pass.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RefinerFileRemuxPassManualEnqueueIn(BaseModel):
    """Per-file remux pass under ``MEDIAMOP_REFINER_REMUX_MEDIA_ROOT``; ``dry_run`` defaults to safe preview."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    relative_media_path: str = Field(
        ...,
        min_length=1,
        description="Path relative to MEDIAMOP_REFINER_REMUX_MEDIA_ROOT (no .. segments).",
    )
    dry_run: bool = Field(
        default=True,
        description="When true (default), runs ffprobe + planning only — no ffmpeg output file and no source moves.",
    )


class RefinerFileRemuxPassManualEnqueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
