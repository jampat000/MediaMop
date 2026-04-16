"""Manual enqueue for ``refiner.file.remux_pass.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from typing import Literal

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
    media_scope: Literal["movie", "tv"] = Field(
        default="movie",
        description="Which saved watched/output tree resolves ``relative_media_path``.",
    )


class RefinerFileRemuxPassManualEnqueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
