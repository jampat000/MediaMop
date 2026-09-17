"""Manual enqueue for ``refiner.watched_folder.remux_scan_dispatch.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RefinerWatchedFolderRemuxScanDispatchManualEnqueueIn(BaseModel):
    """Queue one watched-folder scan."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    enqueue_remux_jobs: bool = Field(
        default=True,
        description=(
            "When true, files found in the watched folder are added to Refiner's processing queue. "
            "When false, MediaMop only checks the folder and writes an activity summary."
        ),
    )
    media_scope: Literal["movie", "tv"] = Field(
        default="movie",
        description="Which saved watched/output tree this scan uses (Movies vs TV path settings).",
    )
    library_id: int | None = Field(
        default=None,
        ge=1,
        description="Limit the recheck to this saved Refiner library; omit for the scope default.",
    )


class RefinerWatchedFolderRemuxScanDispatchManualEnqueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
