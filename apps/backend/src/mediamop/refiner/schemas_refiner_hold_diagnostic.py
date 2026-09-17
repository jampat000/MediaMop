"""Response shape for the "why is this file held?" diagnostic."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RefinerWhyHeldOut(BaseModel):
    """A live answer, alongside the recorded one, so a stale record is visible as stale."""

    file_id: int
    relative_path: str
    library_name: str

    recorded_status: str = Field(description="What the last scan concluded about this file.")
    recorded_reason: str = Field(description="The sentence the last scan recorded.")

    verdict: Literal["proceed", "wait_upstream", "not_held", "no_upstream_signal"] = Field(
        description=(
            "What the managers say right now. 'no_upstream_signal' is distinct from 'not_held': "
            "unknown never means safe."
        ),
    )
    owned: bool
    blocked_upstream: bool
    blocked_by_connection: str | None = Field(
        default=None,
        description="The connection holding this file, named the way MediaMop names connections.",
    )
    queue_row_count: int
    managers_consulted: int
    managers_reporting: int
    managers_without_queue_signal: list[str] = Field(
        default_factory=list,
        description="Connections that could not answer. A manager that is unreachable is reported, never assumed idle.",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Plain-language reasons, already written for the person reading them.",
    )
