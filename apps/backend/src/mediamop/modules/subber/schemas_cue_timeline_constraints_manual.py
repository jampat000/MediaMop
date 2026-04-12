"""Manual enqueue for ``subber.supplied_cue_timeline.constraints_check.v1`` (``subber_jobs`` only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SubberCueIntervalIn(BaseModel):
    """One cue display interval on a notional media clock (seconds only — not read from files here)."""

    model_config = ConfigDict(extra="forbid")

    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., description="Must be strictly greater than start_sec.")

    @model_validator(mode="after")
    def _end_after_start(self) -> SubberCueIntervalIn:
        if self.end_sec <= self.start_sec:
            msg = "each cue needs end_sec > start_sec"
            raise ValueError(msg)
        return self


class SubberSuppliedCueTimelineConstraintsCheckManualEnqueueIn(BaseModel):
    """Operator-supplied cue timeline; workers validate numeric constraints only."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    cues: list[SubberCueIntervalIn] = Field(..., min_length=1)
    source_duration_sec: float | None = Field(
        default=None,
        description="When set, cue intervals must fit within this notional program length.",
    )

    @field_validator("source_duration_sec")
    @classmethod
    def _positive_source(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if v <= 0:
            msg = "source_duration_sec must be positive when set"
            raise ValueError(msg)
        return v


class SubberSuppliedCueTimelineConstraintsCheckManualEnqueueOut(BaseModel):
    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
