"""Auth orchestration — credentials, server-side sessions, logout (ADR-0003).

No JWT for browser, no localStorage. Cookie holds opaque token; ``UserSession`` is authoritative.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.datetime_util import as_utc
from mediamop.platform.auth.models import User, UserSession
from mediamop.platform.auth.password import hash_password, verify_password
from mediamop.platform.auth.sessions import (
    compute_absolute_expiry,
    generate_raw_session_token,
    hash_session_token,
    session_is_valid,
    touch_last_seen,
    utcnow,
    revoke_session,
)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    stmt = select(User).where(User.username == username)
    user = db.scalars(stmt).first()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def revoke_active_sessions_for_user(db: Session, user_id: int) -> None:
    """Invalidate all active sessions for user — login rotation (new session created after)."""

    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.execute(stmt)


def create_user_session(
    db: Session,
    user: User,
    *,
    settings: MediaMopSettings,
) -> tuple[UserSession, str]:
    """Persist session row and return (row, raw_cookie_token)— hash only in DB."""

    raw = generate_raw_session_token()
    th = hash_session_token(raw)
    abs_ttl = timedelta(days=settings.session_absolute_days)
    now = utcnow()
    row = UserSession(
        user_id=user.id,
        token_hash=th,
        absolute_expires_at=compute_absolute_expiry(now=now, ttl=abs_ttl),
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return row, raw


def login_user(
    db: Session,
    *,
    username: str,
    password: str,
    settings: MediaMopSettings,
) -> tuple[User, str] | None:
    """Verify credentials and create a new server-side session. Returns user + raw token."""

    user = authenticate_user(db, username, password)
    if user is None:
        return None
    _row, raw = create_user_session(db, user, settings=settings)
    return user, raw


def _session_last_seen_touch_gap(idle: timedelta) -> timedelta:
    """Minimum wall time between persisting ``last_seen_at`` updates.

    Bounded by 60s to limit SQLite write pressure on read-heavy paths, and by
    half the idle window so the sliding idle timeout cannot be undermined.
    """

    half_idle = idle / 2
    cap = timedelta(seconds=60)
    return min(cap, half_idle)


def load_valid_session_for_request(
    db: Session,
    raw_cookie_token: str | None,
    settings: MediaMopSettings,
) -> tuple[UserSession, User] | None:
    """Lookup by token hash, enforce idle/absolute/revocation, bump last_seen (throttled)."""

    if not raw_cookie_token:
        return None
    th = hash_session_token(raw_cookie_token)
    row = db.scalars(select(UserSession).where(UserSession.token_hash == th)).first()
    if row is None:
        return None
    idle = timedelta(minutes=settings.session_idle_minutes)
    now = utcnow()
    if not session_is_valid(row, idle=idle, now=now):
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    touch_gap = _session_last_seen_touch_gap(idle)
    if now - as_utc(row.last_seen_at) >= touch_gap:
        touch_last_seen(row, at=now)
    return row, user


def logout_by_cookie(
    db: Session,
    raw_cookie_token: str | None,
    settings: MediaMopSettings,
) -> bool:
    """Revoke matching session if present and valid. Returns True if a row was revoked."""

    pair = load_valid_session_for_request(db, raw_cookie_token, settings)
    if pair is None:
        return False
    row, _user = pair
    revoke_session(row)
    return True


def user_public(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


def change_password_for_user(
    db: Session,
    *,
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    """Rotate password hash after verifying current password; revoke all active sessions."""

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ValueError("Account is not available.")
    if not verify_password(current_password, user.password_hash):
        raise ValueError("Current password is incorrect.")
    if current_password == new_password:
        raise ValueError("New password must be different from the current password.")
    user.password_hash = hash_password(new_password)
    revoke_active_sessions_for_user(db, user.id)
    db.flush()
