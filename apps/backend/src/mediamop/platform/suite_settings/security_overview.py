"""Plain-language security snapshot from :class:`~mediamop.core.config.MediaMopSettings` (startup only)."""

from __future__ import annotations

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.schemas import SuiteSecurityOverviewOut


def _plain_duration(seconds: int) -> str:
    s = max(1, int(seconds))
    if s < 60:
        return "1 second" if s == 1 else f"{s} seconds"
    if s < 3600:
        m = s // 60
        return "1 minute" if m == 1 else f"{m} minutes"
    if s < 86400:
        h = s // 3600
        return "1 hour" if h == 1 else f"{h} hours"
    d = s // 86400
    return "1 day" if d == 1 else f"{d} days"


def _same_site_plain(raw: str) -> str:
    v = (raw or "lax").strip().lower()
    if v == "strict":
        return "Strict (tighter; can break some flows)"
    if v == "none":
        return "None (advanced; only makes sense with HTTPS)"
    return "Lax (recommended for most setups)"


def build_suite_security_overview(settings: MediaMopSettings) -> SuiteSecurityOverviewOut:
    secret_ok = bool((settings.session_secret or "").strip())
    return SuiteSecurityOverviewOut(
        session_signing_configured=secret_ok,
        sign_in_cookie_https_only=settings.session_cookie_secure,
        sign_in_cookie_same_site=_same_site_plain(settings.session_cookie_samesite),
        standard_session_idle_timeout_plain=_plain_duration(settings.session_idle_minutes * 60),
        standard_session_absolute_timeout_plain=_plain_duration(settings.session_absolute_days * 86400),
        trusted_session_idle_timeout_plain=_plain_duration(settings.session_trusted_idle_minutes * 60),
        trusted_session_absolute_timeout_plain=_plain_duration(settings.session_trusted_absolute_days * 86400),
        extra_https_hardening_enabled=settings.security_enable_hsts,
        sign_in_attempt_limit=settings.auth_login_rate_max_attempts,
        sign_in_attempt_window_plain=_plain_duration(settings.auth_login_rate_window_seconds),
        first_time_setup_attempt_limit=settings.bootstrap_rate_max_attempts,
        first_time_setup_attempt_window_plain=_plain_duration(settings.bootstrap_rate_window_seconds),
        allowed_browser_origins_count=len(settings.cors_origins),
        restart_required_note=(
            "These safety options are read when the app starts from the server configuration file. "
            "To change them, ask whoever runs the server to edit that file and restart the app."
        ),
    )
