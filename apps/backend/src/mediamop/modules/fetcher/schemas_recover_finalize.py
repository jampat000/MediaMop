"""Pydantic bodies for Fetcher failed-import manual recovery (finalize handler-ok rows)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RecoverFinalizeFailureIn(BaseModel):
    """Explicit confirmation required — no accidental clicks via missing body fields."""

    confirm: Literal[True] = Field(description="Must be true to acknowledge manual recovery.")
    csrf_token: str


class RecoverFinalizeFailureOut(BaseModel):
    job_id: int
    status: str = Field(description="Persisted task status after recovery (always ``completed`` on success).")
