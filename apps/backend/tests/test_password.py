"""Argon2id password helpers (Phase 4)."""

from __future__ import annotations

from mediamop.platform.auth.password import hash_password, verify_password


def test_hash_and_verify_round_trip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_rejects_wrong_password() -> None:
    h = hash_password("one password")
    assert verify_password("other password", h) is False


def test_verify_empty_hash() -> None:
    assert verify_password("x", "") is False
