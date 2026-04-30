from __future__ import annotations

from types import SimpleNamespace

from mediamop.platform.auth import service
from mediamop.platform.auth.password import DUMMY_PASSWORD_HASH


class _ScalarResult:
    def __init__(self, user) -> None:
        self._user = user

    def first(self):
        return self._user


class _FakeSession:
    def __init__(self, user) -> None:
        self._user = user

    def scalars(self, _stmt):
        return _ScalarResult(self._user)


def test_authenticate_user_pads_missing_username_with_dummy_verify(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_verify(password: str, password_hash: str) -> bool:
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr(service, "verify_password", fake_verify)

    user = service.authenticate_user(_FakeSession(None), "missing-user", "wrong-password")

    assert user is None
    assert calls == [("wrong-password", DUMMY_PASSWORD_HASH)]


def test_authenticate_user_pads_inactive_account_with_dummy_verify(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_verify(password: str, password_hash: str) -> bool:
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr(service, "verify_password", fake_verify)
    inactive_user = SimpleNamespace(is_active=False, password_hash="stored-hash")

    user = service.authenticate_user(_FakeSession(inactive_user), "inactive-user", "wrong-password")

    assert user is None
    assert calls == [("wrong-password", DUMMY_PASSWORD_HASH)]
