"""Request and response shapes for the Refiner Files screen."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RefinerFileStatusName = Literal[
    "unprocessed",
    "processing",
    "processed",
    "processing_failed",
    "disabled",
    "on_hold",
    "out_of_schedule",
    "blocked_upstream",
]


class RefinerFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    library_id: int
    library_name: str
    relative_path: str
    status: RefinerFileStatusName
    status_reason: str = Field(description="Why the file is in this state, written for the person reading it.")
    blocked_by_connection: str | None = Field(
        default=None,
        description="The media manager connection holding this file, when the status is blocked_upstream.",
    )
    size_bytes: int
    last_seen_at: datetime | None = None
    last_attempt_at: datetime | None = None


class RefinerFilesPageOut(BaseModel):
    """A page of files plus the bucket counts shown above them."""

    files: list[RefinerFileOut]
    status_counts: dict[str, int]
    returned: int
    limit: int


class RefinerFileForgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
