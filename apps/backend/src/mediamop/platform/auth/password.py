"""Argon2id password hashing (ADR-0003) — long-term spine default; not pbkdf2/bcrypt shortcuts."""

from __future__ import annotations

import logging

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 12
_WEAK_PASSWORDS = {
    "admin",
    "changeme",
    "letmein",
    "mediamop",
    "password",
    "password1",
    "qwerty",
    "welcome",
}

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    """Return a PHC-style Argon2id string suitable for ``users.password_hash``."""
    return _hasher.hash(plain)


def validate_password_strength(plain: str, *, username: str | None = None) -> None:
    password = plain or ""
    normalized = password.strip().lower()
    user = (username or "").strip().lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    normalized_without_trailing_digits = normalized.rstrip("0123456789")
    if normalized in _WEAK_PASSWORDS or normalized_without_trailing_digits in _WEAK_PASSWORDS:
        raise ValueError("Password is too common. Choose a stronger password.")
    if user and user in normalized:
        raise ValueError("Password must not contain the username.")
    if len(set(password)) < 4:
        raise ValueError("Password must use a wider mix of characters.")


def verify_password(plain: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        _hasher.verify(password_hash, plain)
        return True
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        logger.warning("password verify: stored hash is invalid or unsupported (user record may be corrupt)")
        return False
