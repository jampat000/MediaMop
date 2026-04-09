"""Server-side session helpers — authoritative rows in ``user_sessions`` (ADR-0003).

The browser will eventually receive an **opaque** cookie value; only a **hash** of a
high-entropy token is stored in ``UserSession.token_hash``. This is **not** a JWT payload
in the cookie and **not** localStorage.

**Rotation:** On login (when implemented), create a new ``UserSession`` and revoke or delete
prior rows for that user or device policy.

**Invalidation / logout:** Set ``revoked_at`` (or delete the row).

**Idle timeout:** Enforce ``now > last_seen_at + idle_window``; bump ``last_seen_at`` on
authenticated requests that pass other checks.

**Absolute timeout:** Enforce ``now >= absolute_expires_at`` regardless of idle sliding.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from mediamop.platform.auth.models import UserSession

DEFAULT_ABSOLUTE_TTL = timedelta(days=14)
DEFAULT_IDLE_TIMEOUT = timedelta(hours=12)
_TOKEN_ENTROPY_BYTES = 32


def generate_raw_session_token() -> str:
    """Return a high-entropy secret shown to the client once (cookie) — never log it raw."""
    return secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)


def hash_session_token(raw_token: str) -> str:
    """Store only the SHA-256 hex digest in ``user_sessions.token_hash``."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_absolute_expiry(
    *,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_ABSOLUTE_TTL,
) -> datetime:
    return (now or utcnow()) + ttl


def touch_last_seen(session_row: UserSession, *, at: datetime | None = None) -> None:
    session_row.last_seen_at = at or utcnow()


def revoke_session(session_row: UserSession, *, at: datetime | None = None) -> None:
    session_row.revoked_at = at or utcnow()


def is_revoked(session_row: UserSession) -> bool:
    return session_row.revoked_at is not None


def is_past_absolute_expiry(session_row: UserSession, *, now: datetime | None = None) -> bool:
    return (now or utcnow()) >= session_row.absolute_expires_at


def is_idle_expired(
    session_row: UserSession,
    *,
    idle: timedelta = DEFAULT_IDLE_TIMEOUT,
    now: datetime | None = None,
) -> bool:
    return (now or utcnow()) > session_row.last_seen_at + idle


def session_is_valid(
    session_row: UserSession,
    *,
    idle: timedelta = DEFAULT_IDLE_TIMEOUT,
    now: datetime | None = None,
) -> bool:
    n = now or utcnow()
    if is_revoked(session_row):
        return False
    if is_past_absolute_expiry(session_row, now=n):
        return False
    if is_idle_expired(session_row, idle=idle, now=n):
        return False
    return True
