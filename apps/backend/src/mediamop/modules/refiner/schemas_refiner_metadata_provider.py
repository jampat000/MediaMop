"""Request and response shapes for the metadata provider connection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetadataProviderOut(BaseModel):
    provider: str = Field(description="The configured provider, or empty when there is none.")
    base_url: str = Field(
        description="Where MediaMop asks. Configurable so a cache or gateway in front of the provider works."
    )
    #: Never the key itself.
    key_configured: bool = Field(description="Whether a key is stored. The key itself is never returned.")
    known_providers: list[str] = Field(default_factory=list)


class MetadataProviderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    provider: Literal["", "tmdb"] = Field("", description="Empty clears the connection.")
    base_url: str = Field("", max_length=500)
    api_key: str | None = Field(
        default=None,
        max_length=500,
        description="Omit to leave the stored key untouched. An empty string clears it.",
    )


class MetadataProviderTestOut(BaseModel):
    status: Literal["matched", "no_match", "not_configured", "unreachable"]
    detail: str = Field(description="What happened, written for the person reading it.")
