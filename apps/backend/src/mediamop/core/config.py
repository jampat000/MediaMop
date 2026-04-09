"""Environment-backed settings — no secrets embedded in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mediamop.core.paths import resolve_mediamop_home


def _load_backend_dotenv_if_present() -> None:
    """Load ``apps/backend/.env`` so local dev works after ``cp .env.example .env``."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    backend_root = Path(__file__).resolve().parents[3]
    path = backend_root / ".env"
    if path.is_file():
        load_dotenv(path)


def _parse_csv_urls(raw: str) -> tuple[str, ...]:
    parts = [x.strip() for x in raw.split(",")]
    return tuple(p for p in parts if p)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class MediaMopSettings:
    """Runtime configuration loaded at process start."""

    env: str
    database_url: str | None
    log_level: str
    cors_origins: tuple[str, ...]
    session_secret: str | None
    session_cookie_name: str
    session_cookie_secure: bool
    session_cookie_samesite: str
    session_idle_minutes: int
    session_absolute_days: int
    trusted_browser_origins_override: tuple[str, ...]
    auth_login_rate_max_attempts: int
    auth_login_rate_window_seconds: int
    bootstrap_rate_max_attempts: int
    bootstrap_rate_window_seconds: int
    security_enable_hsts: bool
    mediamop_home: str
    fetcher_base_url: str | None

    @property
    def trusted_browser_origins(self) -> tuple[str, ...]:
        """Origins allowed for unsafe browser POST CSRF defense (Origin/Referer)."""

        if self.trusted_browser_origins_override:
            return self.trusted_browser_origins_override
        return self.cors_origins

    @classmethod
    def load(cls) -> MediaMopSettings:
        _load_backend_dotenv_if_present()
        env = (os.environ.get("MEDIAMOP_ENV") or "development").strip().lower()
        url = (os.environ.get("MEDIAMOP_DATABASE_URL") or "").strip() or None
        level = (os.environ.get("MEDIAMOP_LOG_LEVEL") or "INFO").strip() or "INFO"
        cors = _parse_csv_urls(os.environ.get("MEDIAMOP_CORS_ORIGINS") or "")
        session = (os.environ.get("MEDIAMOP_SESSION_SECRET") or "").strip() or None
        cookie_name = (
            (os.environ.get("MEDIAMOP_SESSION_COOKIE_NAME") or "").strip()
            or "mediamop_session"
        )
        samesite = (
            (os.environ.get("MEDIAMOP_SESSION_COOKIE_SAMESITE") or "lax").strip().lower()
        )
        if samesite not in ("lax", "strict", "none"):
            samesite = "lax"
        secure = _env_bool(
            "MEDIAMOP_SESSION_COOKIE_SECURE",
            default=(env == "production"),
        )
        idle_min = max(1, _env_int("MEDIAMOP_SESSION_IDLE_MINUTES", 720))
        abs_days = max(1, _env_int("MEDIAMOP_SESSION_ABSOLUTE_DAYS", 14))
        trusted_override = _parse_csv_urls(
            os.environ.get("MEDIAMOP_TRUSTED_BROWSER_ORIGINS") or "",
        )
        login_max = max(1, _env_int("MEDIAMOP_AUTH_LOGIN_RATE_MAX_ATTEMPTS", 30))
        login_win = max(1, _env_int("MEDIAMOP_AUTH_LOGIN_RATE_WINDOW_SECONDS", 60))
        boot_max = max(1, _env_int("MEDIAMOP_BOOTSTRAP_RATE_MAX_ATTEMPTS", 10))
        boot_win = max(1, _env_int("MEDIAMOP_BOOTSTRAP_RATE_WINDOW_SECONDS", 3600))
        enable_hsts = _env_bool("MEDIAMOP_SECURITY_ENABLE_HSTS", default=False)
        resolved_home = resolve_mediamop_home()
        fetcher_url = (os.environ.get("MEDIAMOP_FETCHER_BASE_URL") or "").strip() or None
        if fetcher_url and not fetcher_url.startswith(("http://", "https://")):
            fetcher_url = None
        return cls(
            env=env,
            database_url=url,
            log_level=level,
            cors_origins=cors,
            session_secret=session,
            session_cookie_name=cookie_name,
            session_cookie_secure=secure,
            session_cookie_samesite=samesite,
            session_idle_minutes=idle_min,
            session_absolute_days=abs_days,
            trusted_browser_origins_override=trusted_override,
            auth_login_rate_max_attempts=login_max,
            auth_login_rate_window_seconds=login_win,
            bootstrap_rate_max_attempts=boot_max,
            bootstrap_rate_window_seconds=boot_win,
            security_enable_hsts=enable_hsts,
            mediamop_home=str(resolved_home),
            fetcher_base_url=fetcher_url,
        )
