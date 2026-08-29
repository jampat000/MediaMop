"""Response shape for the hardware acceleration report."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerHardwareOut(BaseModel):
    detected: bool = Field(description="Whether MediaMop was able to ask ffmpeg at all.")
    available_methods: list[str] = Field(
        default_factory=list,
        description=(
            "Acceleration methods this ffmpeg build was compiled with. Being listed does not prove a device "
            "is present or working — those are different facts."
        ),
    )
    vendors: list[str] = Field(default_factory=list, description="Vendors covered by the available methods.")
    selectable_vendors: list[str] = Field(
        default_factory=list, description="Vendors that can be switched off on a library."
    )
    strictness_levels: list[str] = Field(default_factory=list)
    detail: str = Field(description="What happened, written for the person reading it.")
