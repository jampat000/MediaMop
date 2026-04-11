"""Environment-backed settings — no secrets embedded in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mediamop.core.runtime_paths import (
    assert_sqlite_db_location_usable,
    ensure_runtime_directories,
    resolve_all_runtime_paths,
    sqlalchemy_sqlite_url,
)
from mediamop.modules.arr_failed_import.env_settings import (
    FailedImportCleanupSettingsBundle,
    load_failed_import_cleanup_settings_bundle,
)
from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy
from mediamop.modules.fetcher.fetcher_worker_limits import clamp_fetcher_worker_count
from mediamop.modules.refiner.worker_limits import clamp_refiner_worker_count


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


def _clamp_failed_import_cleanup_drive_schedule_interval_seconds(n: int) -> int:
    """Bound failed-import periodic enqueue interval (60s .. 7d) for SQLite / operator sanity."""

    return max(60, min(n, 7 * 24 * 3600))


@dataclass(frozen=True, slots=True)
class MediaMopSettings:
    """Runtime configuration loaded at process start."""

    env: str
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
    db_path: str
    backup_dir: str
    log_dir: str
    temp_dir: str
    sqlalchemy_database_url: str
    fetcher_base_url: str | None
    failed_import_cleanup_env: FailedImportCleanupSettingsBundle
    # 0 = no in-process Fetcher workers; 1 = default for failed-import drives; >1 = guarded (fetcher_worker_limits).
    fetcher_worker_count: int
    # 0 = no in-process Refiner workers (Refiner-owned refiner_jobs only); >0 when Refiner queues durable work.
    refiner_worker_count: int
    # Radarr/Sonarr HTTP for Fetcher-owned live failed-import cleanup drives (env: MEDIAMOP_FETCHER_*).
    fetcher_radarr_base_url: str | None
    fetcher_radarr_api_key: str | None
    fetcher_sonarr_base_url: str | None
    fetcher_sonarr_api_key: str | None
    failed_import_radarr_cleanup_drive_schedule_enabled: bool
    failed_import_radarr_cleanup_drive_schedule_interval_seconds: int
    failed_import_sonarr_cleanup_drive_schedule_enabled: bool
    failed_import_sonarr_cleanup_drive_schedule_interval_seconds: int

    @property
    def trusted_browser_origins(self) -> tuple[str, ...]:
        """Origins allowed for unsafe browser POST CSRF defense (Origin/Referer)."""

        if self.trusted_browser_origins_override:
            return self.trusted_browser_origins_override
        return self.cors_origins

    def radarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        """Resolved Radarr cleanup toggles (from env at load time)."""

        return self.failed_import_cleanup_env.radarr_policy()

    def sonarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        """Resolved Sonarr cleanup toggles (from env at load time)."""

        return self.failed_import_cleanup_env.sonarr_policy()

    @classmethod
    def load(cls) -> MediaMopSettings:
        _load_backend_dotenv_if_present()
        env = (os.environ.get("MEDIAMOP_ENV") or "development").strip().lower()
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
        fetcher_url = (os.environ.get("MEDIAMOP_FETCHER_BASE_URL") or "").strip() or None
        if fetcher_url and not fetcher_url.startswith(("http://", "https://")):
            fetcher_url = None

        home_path, db_p, backup_p, log_p, temp_p = resolve_all_runtime_paths()
        ensure_runtime_directories(
            db_path=db_p,
            backup_dir=backup_p,
            log_dir=log_p,
            temp_dir=temp_p,
        )
        assert_sqlite_db_location_usable(db_p)
        db_url = sqlalchemy_sqlite_url(db_p)
        failed_import_cleanup = load_failed_import_cleanup_settings_bundle()
        fetcher_workers = clamp_fetcher_worker_count(_env_int("MEDIAMOP_FETCHER_WORKER_COUNT", 1))
        refiner_workers = clamp_refiner_worker_count(_env_int("MEDIAMOP_REFINER_WORKER_COUNT", 0))
        radarr_base = (os.environ.get("MEDIAMOP_FETCHER_RADARR_BASE_URL") or "").strip()
        if radarr_base and not radarr_base.startswith(("http://", "https://")):
            radarr_base = ""
        radarr_key = (os.environ.get("MEDIAMOP_FETCHER_RADARR_API_KEY") or "").strip()
        sonarr_base = (os.environ.get("MEDIAMOP_FETCHER_SONARR_BASE_URL") or "").strip()
        if sonarr_base and not sonarr_base.startswith(("http://", "https://")):
            sonarr_base = ""
        sonarr_key = (os.environ.get("MEDIAMOP_FETCHER_SONARR_API_KEY") or "").strip()
        radarr_sched_on = _env_bool("MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", False)
        radarr_sched_iv = _clamp_failed_import_cleanup_drive_schedule_interval_seconds(
            _env_int("MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_DRIVE_SCHEDULE_INTERVAL_SECONDS", 3600),
        )
        sonarr_sched_on = _env_bool("MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", False)
        sonarr_sched_iv = _clamp_failed_import_cleanup_drive_schedule_interval_seconds(
            _env_int("MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_DRIVE_SCHEDULE_INTERVAL_SECONDS", 3600),
        )

        return cls(
            env=env,
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
            mediamop_home=str(home_path),
            db_path=str(db_p),
            backup_dir=str(backup_p),
            log_dir=str(log_p),
            temp_dir=str(temp_p),
            sqlalchemy_database_url=db_url,
            fetcher_base_url=fetcher_url,
            failed_import_cleanup_env=failed_import_cleanup,
            fetcher_worker_count=fetcher_workers,
            refiner_worker_count=refiner_workers,
            fetcher_radarr_base_url=radarr_base or None,
            fetcher_radarr_api_key=radarr_key or None,
            fetcher_sonarr_base_url=sonarr_base or None,
            fetcher_sonarr_api_key=sonarr_key or None,
            failed_import_radarr_cleanup_drive_schedule_enabled=radarr_sched_on,
            failed_import_radarr_cleanup_drive_schedule_interval_seconds=radarr_sched_iv,
            failed_import_sonarr_cleanup_drive_schedule_enabled=sonarr_sched_on,
            failed_import_sonarr_cleanup_drive_schedule_interval_seconds=sonarr_sched_iv,
        )
