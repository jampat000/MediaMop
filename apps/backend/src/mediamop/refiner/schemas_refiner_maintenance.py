"""Request and response shapes for the maintenance job families.

These families do real work on real paths and, until #339, could only be switched on by an
undocumented environment variable and could not be triggered from outside the process at
all. This is the surface that makes them operable (#346).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MaintenanceFamily = Literal["work_temp_stale_sweep", "failure_cleanup"]
MaintenanceScope = Literal["movie", "tv"]


class MaintenanceFamilyStateOut(BaseModel):
    """What one family is doing, and whether it is switched on."""

    family: MaintenanceFamily
    enabled: bool = Field(description="Whether the schedule runs this family. Triggering by hand ignores this.")
    description: str = Field(description="What this family does, in a sentence.")
    pending: int = Field(description="Queued and not yet started.")
    running: int = Field(description="Leased by a worker right now.")
    last_completed_at: datetime | None = None
    last_failed_at: datetime | None = None
    last_error: str | None = Field(
        default=None, description="The most recent failure reason, when the last run failed."
    )


class MaintenanceStateOut(BaseModel):
    families: list[MaintenanceFamilyStateOut]


class MaintenanceTriggerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    family: MaintenanceFamily
    media_scope: MaintenanceScope = "movie"


class MaintenanceTriggerOut(BaseModel):
    queued: bool = Field(description="False when a run of this family was already waiting or in progress.")
    detail: str = Field(description="What happened, written for the person reading it.")
    job_id: int | None = None
