"""CRUD operations for NotificationChannel rows."""

from __future__ import annotations

import json
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.platform.notifications.model import (
    SUPPORTED_EVENTS,
    SUPPORTED_PROVIDERS,
    NotificationChannel,
)
from mediamop.platform.outbound_http import validate_external_provider_url


def _parse_events(events_json: str) -> list[str]:
    try:
        return [e for e in json.loads(events_json) if isinstance(e, str)]
    except (ValueError, TypeError):
        return []


def _validate_channel_input(
    label: str,
    provider: str,
    url: str,
    events: list[str],
) -> None:
    label = label.strip()
    if not label:
        raise ValueError("Label must not be empty.")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider!r}. Choose from: {', '.join(SUPPORTED_PROVIDERS)}")
    validate_external_provider_url(url)
    bad = [e for e in events if e not in SUPPORTED_EVENTS]
    if bad:
        raise ValueError(f"Unknown events: {', '.join(bad)}. Supported: {', '.join(SUPPORTED_EVENTS)}")
    if not events:
        raise ValueError("At least one event must be selected.")


def list_notification_channels(session: Session) -> list[NotificationChannel]:
    return list(session.scalars(select(NotificationChannel).order_by(NotificationChannel.id)))


def get_notification_channel(session: Session, channel_id: int) -> NotificationChannel | None:
    return session.scalars(select(NotificationChannel).where(NotificationChannel.id == channel_id)).one_or_none()


def create_notification_channel(
    session: Session,
    *,
    label: str,
    provider: str,
    url: str,
    events: list[str],
    enabled: bool = True,
) -> NotificationChannel:
    _validate_channel_input(label, provider, url, events)
    row = NotificationChannel(
        label=label.strip(),
        provider=provider,
        url=url,
        events_json=json.dumps(events),
        enabled=enabled,
    )
    session.add(row)
    session.flush()
    return row


def update_notification_channel(
    session: Session,
    channel_id: int,
    *,
    label: str,
    provider: str,
    url: str,
    events: list[str],
    enabled: bool,
) -> NotificationChannel | None:
    row = get_notification_channel(session, channel_id)
    if row is None:
        return None
    _validate_channel_input(label, provider, url, events)
    row.label = label.strip()
    row.provider = provider
    row.url = url
    row.events_json = json.dumps(events)
    row.enabled = enabled
    session.flush()
    return row


def delete_notification_channel(
    session: Session,
    channel_id: int,
) -> Literal["ok", "not_found"]:
    row = get_notification_channel(session, channel_id)
    if row is None:
        return "not_found"
    session.delete(row)
    session.flush()
    return "ok"


def get_channels_for_event(session: Session, event: str) -> list[NotificationChannel]:
    """Return enabled channels whose events_json includes *event* or its wildcard counterpart."""
    rows = session.scalars(select(NotificationChannel).where(NotificationChannel.enabled.is_(True))).all()
    result = []
    for row in rows:
        subscribed = _parse_events(row.events_json)
        if event in subscribed:
            result.append(row)
    return result
