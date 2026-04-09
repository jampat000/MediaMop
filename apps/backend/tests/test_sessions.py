"""Server-side session utility behavior (no database required)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from mediamop.platform.auth.models import UserSession
from mediamop.platform.auth.sessions import (
    compute_absolute_expiry,
    hash_session_token,
    is_idle_expired,
    is_past_absolute_expiry,
    is_revoked,
    session_is_valid,
    touch_last_seen,
    utcnow,
)


def test_token_hash_stable() -> None:
    assert hash_session_token("same") == hash_session_token("same")
    assert hash_session_token("a") != hash_session_token("b")


def test_session_validity_guards() -> None:
    now = utcnow()
    row = UserSession(
        id=uuid.uuid4(),
        user_id=1,
        token_hash="ab" * 32,
        absolute_expires_at=compute_absolute_expiry(now=now, ttl=timedelta(hours=1)),
        last_seen_at=now,
    )
    assert session_is_valid(row, now=now) is True
    assert is_revoked(row) is False
    revoke = UserSession(
        id=uuid.uuid4(),
        user_id=1,
        token_hash="cd" * 32,
        absolute_expires_at=compute_absolute_expiry(now=now, ttl=timedelta(hours=1)),
        last_seen_at=now,
        revoked_at=now,
    )
    assert session_is_valid(revoke, now=now) is False


def test_absolute_and_idle_expiry() -> None:
    now = utcnow()
    row = UserSession(
        id=uuid.uuid4(),
        user_id=1,
        token_hash="ef" * 32,
        absolute_expires_at=now - timedelta(seconds=1),
        last_seen_at=now - timedelta(hours=24),
    )
    assert is_past_absolute_expiry(row, now=now) is True
    assert session_is_valid(row, now=now) is False

    future = UserSession(
        id=uuid.uuid4(),
        user_id=1,
        token_hash="12" * 32,
        absolute_expires_at=now + timedelta(days=7),
        last_seen_at=now - timedelta(hours=13),
    )
    assert is_idle_expired(future, idle=timedelta(hours=12), now=now) is True
    assert session_is_valid(future, idle=timedelta(hours=12), now=now) is False


def test_touch_last_seen_updates() -> None:
    row = UserSession(
        id=uuid.uuid4(),
        user_id=1,
        token_hash="9f" * 32,
        absolute_expires_at=utcnow() + timedelta(days=1),
        last_seen_at=utcnow() - timedelta(minutes=5),
    )
    at = utcnow()
    touch_last_seen(row, at=at)
    assert row.last_seen_at == at
