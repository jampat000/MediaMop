"""Argon2id password hashing (ADR-0003) — long-term spine default; not pbkdf2/bcrypt shortcuts."""

from __future__ import annotations

import logging

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

logger = logging.getLogger(__name__)

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
