"""verify_password tolerates corrupt stored hashes without raising."""

from __future__ import annotations

from mediamop.platform.auth.password import verify_password


def test_verify_password_empty_hash() -> None:
    assert verify_password("any", "") is False


def test_verify_password_garbage_hash_returns_false() -> None:
    assert verify_password("secret", "not-a-valid-phc-string") is False
