"""Manual enqueue for ``refiner.file.remux_pass.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RefinerFileRemuxPassManualEnqueueIn(BaseModel):
    """Manual ``refiner.file.remux_pass.v1`` enqueue — requires a saved Refiner watched folder before this POST succeeds."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    relative_media_path: str = Field(
        ...,
        min_length=1,
        description=(
            "Path relative to the saved Refiner watched folder (no .. segments). "
            "The watched folder is not required when saving path settings alone, but it must be configured before enqueue."
        ),
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "When true (default), runs ffprobe + planning only — no ffmpeg output file, no source deletion, "
            "and no requirement for a saved output folder."
        ),
    )


class RefinerFileRemuxPassManualEnqueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
