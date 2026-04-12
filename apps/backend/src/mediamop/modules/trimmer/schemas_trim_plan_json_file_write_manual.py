"""Manual enqueue for ``trimmer.supplied_trim_plan.json_file_write.v1`` (``trimmer_jobs`` only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TrimPlanJsonFileWriteSegmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sec: float = Field(..., ge=0)
    end_sec: float = Field(..., description="Must be strictly greater than start_sec.")

    @model_validator(mode="after")
    def _end_after_start(self) -> TrimPlanJsonFileWriteSegmentIn:
        if self.end_sec <= self.start_sec:
            msg = "each segment needs end_sec > start_sec"
            raise ValueError(msg)
        return self


class TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueIn(BaseModel):
    """Same segment outline as constraint check; worker validates then writes JSON under ``MEDIAMOP_HOME``."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    segments: list[TrimPlanJsonFileWriteSegmentIn] = Field(..., min_length=1)
    source_duration_sec: float | None = Field(
        default=None,
        description="When set, segments must fit within this source length and total kept time must not exceed it.",
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


class TrimmerSuppliedTrimPlanJsonFileWriteManualEnqueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: int
    dedupe_key: str
    job_kind: str
