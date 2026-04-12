"""Plain-language fields for ``GET /api/v1/suite/security-overview``."""

from __future__ import annotations

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.security_overview import build_suite_security_overview


def test_build_suite_security_overview_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    monkeypatch.setenv("MEDIAMOP_CORS_ORIGINS", "http://localhost:5173")
    s = MediaMopSettings.load()
    out = build_suite_security_overview(s)
    assert out.session_signing_configured is True
    assert out.sign_in_attempt_limit >= 1
    assert "second" in out.sign_in_attempt_window_plain or "minute" in out.sign_in_attempt_window_plain
    assert out.restart_required_note
