"""Pydantic schemas for the notification channels API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from mediamop.platform.notifications.model import SUPPORTED_EVENTS, SUPPORTED_PROVIDERS


class NotificationChannelOut(BaseModel):
    id: int
    label: str
    provider: str
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationChannelListOut(BaseModel):
    items: list[NotificationChannelOut]
    supported_events: list[str] = list(SUPPORTED_EVENTS)
    supported_providers: list[str] = list(SUPPORTED_PROVIDERS)


class NotificationChannelIn(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    provider: str
    url: str = Field(min_length=1)
    events: list[str] = Field(default_factory=lambda: ["job_failed"])
    enabled: bool = True
    csrf_token: str


class NotificationChannelTestIn(BaseModel):
    csrf_token: str


class NotificationChannelTestOut(BaseModel):
    ok: bool
    error: str | None = None
