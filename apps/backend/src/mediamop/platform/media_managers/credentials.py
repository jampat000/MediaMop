"""Resolve the address and key for whichever manager looks after a media scope.

Callers never actually wanted "Radarr" — they wanted *the manager that knows about
movies*. That used to be the same thing, so the vendor name stood in for the concept
and got copied into a second function for TV. Now that a connection carries its kind,
the question can be asked properly, and a manager that serves both scopes (Deluno, or
anything speaking the native shape) answers both without new code.

Order of preference: a connection whose kind is specific to the scope, then a
general-purpose connection, then the environment variables that predate the table.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library.arr_connection_crypto import decrypt_arr_api_key
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow

MediaScope = Literal["movie", "tv"]

# Kinds that only ever describe one kind of library.
_SCOPE_SPECIFIC_KINDS: dict[str, str] = {"movie": "radarr", "tv": "sonarr"}

# Kinds that serve any scope.
_GENERAL_KINDS: tuple[str, ...] = ("deluno", "native")


def _credentials_from_row(
    settings: MediaMopSettings,
    row: MediaManagerConnectionRow,
) -> tuple[str, str] | None:
    url = (row.base_url or "").strip()
    ciphertext = (row.api_key_ciphertext or "").strip()
    if not url or not ciphertext:
        return None
    key = decrypt_arr_api_key(settings, ciphertext)
    return (url, key) if key else None


def _environment_fallback(settings: MediaMopSettings, media_scope: str) -> tuple[str | None, str | None]:
    if media_scope == "tv":
        return settings.arr_http_sonarr_credentials()
    return settings.arr_http_radarr_credentials()


def resolve_manager_credentials(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: MediaScope,
) -> tuple[str | None, str | None]:
    """Address and API key for the manager covering ``media_scope``, or ``(None, None)``."""

    scope = "tv" if media_scope == "tv" else "movie"
    preferred = _SCOPE_SPECIFIC_KINDS[scope]

    rows = list(
        session.scalars(
            select(MediaManagerConnectionRow)
            .where(MediaManagerConnectionRow.enabled.is_(True))
            .order_by(MediaManagerConnectionRow.id)
        )
    )

    for kind in (preferred, *_GENERAL_KINDS):
        for row in rows:
            if row.kind != kind:
                continue
            found = _credentials_from_row(settings, row)
            if found is not None:
                return found

    # A connection that exists but is disabled is a deliberate "off", so only fall back
    # to the environment when no enabled connection of a usable kind is configured.
    if any(row.kind == preferred for row in rows):
        return (None, None)
    return _environment_fallback(settings, scope)


def resolve_movie_manager_credentials(
    session: Session,
    settings: MediaMopSettings,
) -> tuple[str | None, str | None]:
    return resolve_manager_credentials(session, settings, media_scope="movie")


def resolve_tv_manager_credentials(
    session: Session,
    settings: MediaMopSettings,
) -> tuple[str | None, str | None]:
    return resolve_manager_credentials(session, settings, media_scope="tv")
