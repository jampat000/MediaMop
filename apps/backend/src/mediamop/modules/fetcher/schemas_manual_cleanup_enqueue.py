"""Pydantic for operator-triggered failed-import download-queue pass enqueue (movies / TV POST bodies)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ManualCleanupDriveEnqueueIn(BaseModel):
    """Browser POST with CSRF — mirrors finalize-recovery body shape."""

    confirm: Literal[True] = Field(description="Must be true to acknowledge adding a download-queue pass for the worker.")
    csrf_token: str


class ManualCleanupDriveEnqueueOut(BaseModel):
    """Enqueue result only — not pass execution, completion, or runner liveness."""

    job_id: int
    dedupe_key: str
    job_kind: str
    queue_outcome: Literal["created", "already_present"] = Field(
        description=(
            "``created`` = new persisted job row inserted; ``already_present`` = same dedupe key already had a row."
        ),
    )
