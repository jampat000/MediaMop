"""Safe parsing of select integer env vars in MediaMopSettings.load."""

from __future__ import annotations

import pytest

from mediamop.core.config import MediaMopSettings


def test_session_ttl_integers_ignore_malformed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "not-a-number")
    monkeypatch.setenv("MEDIAMOP_SESSION_ABSOLUTE_DAYS", "xyz")
    s = MediaMopSettings.load()
    assert s.session_idle_minutes == 720
    assert s.session_absolute_days == 14


def test_session_ttl_integers_respect_valid_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "60")
    monkeypatch.setenv("MEDIAMOP_SESSION_ABSOLUTE_DAYS", "7")
    s = MediaMopSettings.load()
    assert s.session_idle_minutes == 60
    assert s.session_absolute_days == 7


def test_session_ttl_clamps_to_at_least_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "0")
    monkeypatch.setenv("MEDIAMOP_SESSION_ABSOLUTE_DAYS", "-5")
    s = MediaMopSettings.load()
    assert s.session_idle_minutes == 1
    assert s.session_absolute_days == 1
