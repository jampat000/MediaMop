"""Request and response shapes for the suite pause control."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SuitePauseOut(BaseModel):
    paused: bool
    paused_until: datetime | None = Field(
        default=None,
        description="When the pause lifts on its own. Null for a pause that lasts until it is lifted by hand.",
    )
    scan_while_paused: bool = Field(
        description="Whether MediaMop keeps noticing new files while it is not working on them.",
    )
    reason: str = Field(description="What to show an operator, written for them rather than for the code.")
    in_flight_policy: str = Field(
        description="What happens to work that is already running when a pause or a schedule window starts.",
    )


class SuitePauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    paused: bool
    pause_for_minutes: int | None = Field(
        default=None,
        ge=1,
        le=10080,
        description="Lift the pause automatically after this many minutes. Omit for a pause with no expiry.",
    )
    scan_while_paused: bool = True
