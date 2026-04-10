"""Pydantic for operator-triggered cleanup-drive enqueue (Radarr/Sonarr POST bodies and responses)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ManualCleanupDriveEnqueueIn(BaseModel):
    """Browser POST with CSRF — mirrors finalize-recovery body shape."""

    confirm: Literal[True] = Field(description="Must be true to acknowledge manual enqueue.")
    csrf_token: str


class ManualCleanupDriveEnqueueOut(BaseModel):
    """Enqueue result only — not job execution, completion, or worker liveness."""

    job_id: int
    dedupe_key: str
    job_kind: str
    enqueue_outcome: Literal["created", "already_present"] = Field(
        description="``created`` = new row inserted; ``already_present`` = dedupe key already had a row.",
    )
