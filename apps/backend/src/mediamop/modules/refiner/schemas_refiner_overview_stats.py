from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerOverviewStatsOut(BaseModel):
    window_days: int = Field(default=30, ge=1, le=3650)
    files_processed: int = Field(ge=0, description="Completed refiner.file.remux_pass.v1 jobs in the window.")
    files_failed: int = Field(
        ge=0,
        description="Terminal-failure refiner.file.remux_pass.v1 jobs in the window (failed + finalize-failed).",
    )
    success_rate_percent: float = Field(ge=0.0, le=100.0)
    output_written_count: int = Field(
        ge=0,
        description="Refiner remux activity rows that wrote a new output file in the window.",
    )
    already_optimized_count: int = Field(
        ge=0,
        description="Refiner activity rows where no file changes were needed.",
    )
    net_space_saved_bytes: int = Field(
        description="Net source-bytes minus output-bytes across output-written remuxes in the window.",
    )
    net_space_saved_percent: float = Field(
        description="Net size reduction percentage across output-written remuxes in the window.",
    )
