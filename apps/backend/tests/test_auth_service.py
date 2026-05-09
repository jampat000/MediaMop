from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mediamop.platform.auth import service
from mediamop.platform.auth import bootstrap as bootstrap_service
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


class _FakeDeleteSession:
    def execute(self, _stmt):  # noqa: ANN001
        class _ResultWithoutRowcount:
            pass

        return _ResultWithoutRowcount()


class _FakeBootstrapDb:
    def __init__(self, driver_connection: object | None) -> None:
        self._driver_connection = driver_connection

    def connection(self) -> SimpleNamespace:
        return SimpleNamespace(
            connection=SimpleNamespace(driver_connection=self._driver_connection),
        )


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


def test_cleanup_inactive_sessions_handles_missing_rowcount() -> None:
    removed = service.cleanup_inactive_sessions(
        _FakeDeleteSession(),
        settings=SimpleNamespace(session_idle_minutes=60, session_trusted_idle_minutes=1440),
        now=datetime(2026, 5, 9, tzinfo=UTC),
    )
    assert removed == 0


def test_acquire_bootstrap_transaction_lock_raises_when_driver_connection_missing() -> None:
    with pytest.raises(RuntimeError, match="driver connection is unavailable"):
        bootstrap_service.acquire_bootstrap_transaction_lock(_FakeBootstrapDb(None))
