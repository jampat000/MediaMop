"""Read and write media manager connections.

Secrets are stored encrypted and never returned. The API reports whether one is
saved, which is all a settings screen needs to render honestly.
"""

from __future__ import annotations

import secrets as pysecrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library.arr_connection_crypto import (
    decrypt_arr_api_key,
    encrypt_arr_api_key,
)
from mediamop.platform.media_managers.connection_model import (
    MEDIA_MANAGER_KINDS,
    SEARCH_LANES,
    MediaManagerConnectionRow,
    MediaManagerSearchLaneRow,
)
from mediamop.platform.outbound_http import normalize_local_service_base_url


class MediaManagerConnectionError(ValueError):
    """A connection could not be saved as asked, with an operator-readable reason."""


@dataclass(frozen=True, slots=True)
class ResolvedCallbackTarget:
    """Where to report a finished hand-off, and how to authenticate."""

    base_url: str
    api_key: str | None


def list_connections(session: Session) -> list[MediaManagerConnectionRow]:
    return list(session.scalars(select(MediaManagerConnectionRow).order_by(MediaManagerConnectionRow.id)))


def get_connection(session: Session, connection_id: int) -> MediaManagerConnectionRow | None:
    return session.get(MediaManagerConnectionRow, connection_id)


def connection_for_kind(session: Session, kind: str) -> MediaManagerConnectionRow | None:
    """First enabled connection of a kind — what an inbound webhook is matched against."""

    return session.scalars(
        select(MediaManagerConnectionRow)
        .where(MediaManagerConnectionRow.kind == kind)
        .where(MediaManagerConnectionRow.enabled.is_(True))
        .order_by(MediaManagerConnectionRow.id)
    ).first()


def _validate_kind(kind: str) -> str:
    value = (kind or "").strip().lower()
    if value not in MEDIA_MANAGER_KINDS:
        raise MediaManagerConnectionError(
            f"Unknown media manager kind {kind!r}. Known kinds: {', '.join(MEDIA_MANAGER_KINDS)}."
        )
    return value


def _validate_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        return ""
    try:
        return normalize_local_service_base_url(raw)
    except ValueError as exc:
        raise MediaManagerConnectionError(f"That address will not work: {exc}") from exc


def create_connection(
    session: Session,
    settings: MediaMopSettings,
    *,
    kind: str,
    name: str,
    base_url: str = "",
    api_key: str | None = None,
    enabled: bool = True,
) -> MediaManagerConnectionRow:
    label = (name or "").strip()
    if not label:
        raise MediaManagerConnectionError("Give the connection a name so you can tell it apart later.")
    if session.scalars(select(MediaManagerConnectionRow).where(MediaManagerConnectionRow.name == label)).first():
        raise MediaManagerConnectionError(f"A connection named {label!r} already exists.")

    key = (api_key or "").strip()
    row = MediaManagerConnectionRow(
        kind=_validate_kind(kind),
        name=label,
        enabled=enabled,
        base_url=_validate_base_url(base_url),
        api_key_ciphertext=encrypt_arr_api_key(settings, key) if key else None,
    )
    session.add(row)
    session.flush()
    for lane in SEARCH_LANES:
        session.add(MediaManagerSearchLaneRow(connection_id=row.id, lane=lane))
    session.flush()
    return row


def update_connection(
    session: Session,
    settings: MediaMopSettings,
    row: MediaManagerConnectionRow,
    *,
    name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enabled: bool | None = None,
) -> MediaManagerConnectionRow:
    if name is not None:
        label = name.strip()
        if not label:
            raise MediaManagerConnectionError("Give the connection a name so you can tell it apart later.")
        clash = session.scalars(
            select(MediaManagerConnectionRow).where(MediaManagerConnectionRow.name == label)
        ).first()
        if clash is not None and clash.id != row.id:
            raise MediaManagerConnectionError(f"A connection named {label!r} already exists.")
        row.name = label
    if base_url is not None:
        row.base_url = _validate_base_url(base_url)
    if enabled is not None:
        row.enabled = enabled
    # An empty string clears the stored key; None leaves it untouched, so a settings
    # form can round-trip without the operator retyping a secret it never displays.
    if api_key is not None:
        row.api_key_ciphertext = encrypt_arr_api_key(settings, api_key.strip()) if api_key.strip() else None
    session.flush()
    return row


def rotate_webhook_secret(session: Session, settings: MediaMopSettings, row: MediaManagerConnectionRow) -> str:
    """Generate, store and return a fresh inbound secret. Returned once, never again."""

    plaintext = pysecrets.token_urlsafe(32)
    row.webhook_secret_ciphertext = encrypt_arr_api_key(settings, plaintext)
    session.flush()
    return plaintext


def webhook_secret_matches(settings: MediaMopSettings, row: MediaManagerConnectionRow, presented: str | None) -> bool:
    stored = row.webhook_secret_ciphertext
    if not stored:
        # No per-connection secret configured: this connection does not require one.
        return True
    expected = decrypt_arr_api_key(settings, stored)
    if not expected:
        return False
    return pysecrets.compare_digest(expected, (presented or "").strip())


def resolve_callback_target(
    settings: MediaMopSettings,
    row: MediaManagerConnectionRow,
) -> ResolvedCallbackTarget | None:
    """The base URL and credential to report a finished hand-off with."""

    base = (row.base_url or "").strip()
    if not base:
        return None
    api_key = decrypt_arr_api_key(settings, row.api_key_ciphertext) if row.api_key_ciphertext else None
    return ResolvedCallbackTarget(base_url=base.rstrip("/"), api_key=api_key)
