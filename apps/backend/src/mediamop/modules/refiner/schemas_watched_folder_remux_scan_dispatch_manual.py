"""Manual enqueue for ``refiner.watched_folder.remux_scan_dispatch.v1`` (``refiner_jobs`` only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RefinerWatchedFolderRemuxScanDispatchManualEnqueueIn(BaseModel):
    """Queue one watched-folder scan; optional enqueue of per-file ``refiner.file.remux_pass.v1`` rows."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    enqueue_remux_jobs: bool = Field(
        default=False,
        description=(
            "When false (default), the scan only classifies files and writes one activity summary — "
            "no remux jobs are queued. When true, eligible files (verdict proceed) also enqueue remux jobs."
        ),
    )
    media_scope: Literal["movie", "tv"] = Field(
        default="movie",
        description="Which saved watched/output tree this scan uses (Movies vs TV path settings).",
    )


class RefinerWatchedFolderRemuxScanDispatchManualEnqueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
