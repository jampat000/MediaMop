"""Environment-backed settings — no secrets embedded in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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
from mediamop.modules.refiner.refiner_family_intervals import (
    clamp_refiner_min_file_age_seconds,
    clamp_refiner_schedule_interval_seconds,
)
from mediamop.modules.refiner.worker_limits import clamp_refiner_worker_count
from mediamop.modules.broker.broker_worker_limits import clamp_broker_worker_count
from mediamop.modules.subber.worker_limits import clamp_subber_worker_count
from mediamop.modules.pruner.worker_limits import clamp_pruner_worker_count


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


def _expand_loopback_browser_origins_in_development(origins: tuple[str, ...]) -> tuple[str, ...]:
    """For each ``http(s)://localhost`` / ``127.0.0.1`` entry, also allow the other hostname (same port).

    Browsers treat these as different ``Origin`` values; operators constantly switch between them in dev.
    """

    if not origins:
        return origins
    ordered: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        s = raw.strip().rstrip("/")
        if not s or s in seen:
            return
        seen.add(s)
        ordered.append(s)

    for o in origins:
        add(o)
        parsed = urlparse(o.strip())
        if parsed.scheme not in ("http", "https"):
            continue
        host = (parsed.hostname or "").lower()
        if host == "localhost":
            alt_host = "127.0.0.1"
        elif host == "127.0.0.1":
            alt_host = "localhost"
        else:
            continue
        if parsed.port is not None:
            alt = f"{parsed.scheme}://{alt_host}:{parsed.port}"
        else:
            alt = f"{parsed.scheme}://{alt_host}"
        add(alt.rstrip("/"))

    return tuple(ordered)


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

    return clamp_failed_import_cleanup_drive_schedule_interval_seconds(n)


def clamp_failed_import_cleanup_drive_schedule_interval_seconds(n: int) -> int:
    """Public clamp for persisted failed-import cleanup drive intervals (API + SQLite policy row)."""

    return max(60, min(int(n), 7 * 24 * 3600))


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
    # 0 = no in-process Pruner workers (Pruner-owned pruner_jobs only); >0 when Pruner queues durable work.
    pruner_worker_count: int
    # Pruner per-scope scheduled preview enqueue loop (reads ``pruner_scope_settings``; independent of worker count).
    pruner_preview_schedule_enqueue_enabled: bool
    pruner_preview_schedule_scan_interval_seconds: int
    # Jellyfin + Emby Phase 3 apply: enqueue ``pruner.candidate_removal.apply.v1`` (default off).
    pruner_apply_enabled: bool
    # Deprecated: legacy ``MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED`` (Plex used to enqueue ``plex_live.v1``). Plex
    # missing-primary removal now uses preview snapshots + apply only; this flag is loaded for API visibility only.
    pruner_plex_live_removal_enabled: bool
    # Caps Plex ``missing_primary_media_reported`` preview-only collection (per-scope ``preview_max_items`` and a 5k
    # clamp). Env name keeps ``PLEX_LIVE`` for older installs; it does not re-enable live scan. Loaded from
    # MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS.
    pruner_plex_live_abs_max_items: int
    # 0 = no in-process Subber workers (Subber-owned subber_jobs only); >0 when Subber queues durable work.
    subber_worker_count: int
    # 0 = no in-process Broker workers (Broker-owned broker_jobs only); >0 when Broker queues durable work.
    broker_worker_count: int
    # Subber library scan periodic enqueue (reads ``subber_settings``; independent of worker count).
    subber_library_scan_schedule_enqueue_enabled: bool
    subber_library_scan_schedule_scan_interval_seconds: int
    # Subber subtitle-upgrade periodic enqueue — separate asyncio task from TV/Movies library scan schedules.
    subber_upgrade_schedule_enqueue_enabled: bool
    # Refiner supplied payload evaluation (``refiner.supplied_payload_evaluation.v1``) — Refiner-only schedule.
    refiner_supplied_payload_evaluation_schedule_enabled: bool
    refiner_supplied_payload_evaluation_schedule_interval_seconds: int
    # Refiner watched-folder remux scan dispatch (``refiner.watched_folder.remux_scan_dispatch.v1``) — Refiner-only
    # periodic enqueue (optional). Separate enable/interval from supplied payload evaluation (ADR-0009).
    refiner_watched_folder_remux_scan_dispatch_schedule_enabled: bool
    refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds: int
    refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs: bool
    refiner_watched_folder_min_file_age_seconds: int
    # Refiner Pass 3a — Movies output-folder cleanup minimum age (env at process start; not the watched-folder scan gate).
    refiner_movie_output_cleanup_min_age_seconds: int
    # Refiner Pass 3b — TV output-folder cleanup minimum age (direct-child episode media; env at process start).
    refiner_tv_output_cleanup_min_age_seconds: int
    # Refiner work/temp stale sweep (``refiner.work_temp_stale_sweep.v1``) — per-scope periodic enqueue.
    refiner_work_temp_stale_sweep_movie_schedule_enabled: bool
    refiner_work_temp_stale_sweep_movie_schedule_interval_seconds: int
    refiner_work_temp_stale_sweep_tv_schedule_enabled: bool
    refiner_work_temp_stale_sweep_tv_schedule_interval_seconds: int
    # Narrow exception: same minimum age applies to both scopes (same temp filename semantics).
    refiner_work_temp_stale_sweep_min_stale_age_seconds: int
    # Refiner Pass 4 — terminal failed remux cleanup sweep (Movies/TV independent schedule + grace).
    refiner_movie_failure_cleanup_schedule_enabled: bool
    refiner_movie_failure_cleanup_schedule_interval_seconds: int
    refiner_tv_failure_cleanup_schedule_enabled: bool
    refiner_tv_failure_cleanup_schedule_interval_seconds: int
    refiner_movie_failure_cleanup_grace_period_seconds: int
    refiner_tv_failure_cleanup_grace_period_seconds: int
    # Legacy env read for compatibility only; remux path resolution uses saved Refiner path settings (SQLite).
    refiner_remux_media_root: str | None
    # Radarr/Sonarr HTTP for Fetcher-owned live failed-import cleanup drives (env: MEDIAMOP_FETCHER_*).
    fetcher_radarr_base_url: str | None
    fetcher_radarr_api_key: str | None
    fetcher_sonarr_base_url: str | None
    fetcher_sonarr_api_key: str | None
    # Shared neutral *arr HTTP (env: MEDIAMOP_ARR_*). Refiner and Fetcher resolve via arr_http_*_credentials().
    arr_radarr_base_url: str | None
    arr_radarr_api_key: str | None
    arr_sonarr_base_url: str | None
    arr_sonarr_api_key: str | None
    failed_import_radarr_cleanup_drive_schedule_enabled: bool
    failed_import_radarr_cleanup_drive_schedule_interval_seconds: int
    failed_import_sonarr_cleanup_drive_schedule_enabled: bool
    failed_import_sonarr_cleanup_drive_schedule_interval_seconds: int
    # Fetcher Arr search (missing / upgrade) — env ``MEDIAMOP_FETCHER_*_{MISSING|UPGRADE}_SEARCH_ENABLED`` (not Refiner).
    fetcher_sonarr_missing_search_enabled: bool
    fetcher_sonarr_upgrade_search_enabled: bool
    fetcher_radarr_missing_search_enabled: bool
    fetcher_radarr_upgrade_search_enabled: bool
    # Four independent lanes: ``missing_search.{sonarr,radarr}.*`` and ``upgrade_search.{sonarr,radarr}.*``.
    # Each has its own batch limit, retry/cooldown minutes, and schedule window (no cross-lane coupling).
    fetcher_sonarr_missing_search_max_items_per_run: int
    fetcher_sonarr_missing_search_retry_delay_minutes: int
    fetcher_sonarr_missing_search_schedule_enabled: bool
    fetcher_sonarr_missing_search_schedule_days: str
    fetcher_sonarr_missing_search_schedule_start: str
    fetcher_sonarr_missing_search_schedule_end: str
    fetcher_sonarr_upgrade_search_max_items_per_run: int
    fetcher_sonarr_upgrade_search_retry_delay_minutes: int
    fetcher_sonarr_upgrade_search_schedule_enabled: bool
    fetcher_sonarr_upgrade_search_schedule_days: str
    fetcher_sonarr_upgrade_search_schedule_start: str
    fetcher_sonarr_upgrade_search_schedule_end: str
    fetcher_radarr_missing_search_max_items_per_run: int
    fetcher_radarr_missing_search_retry_delay_minutes: int
    fetcher_radarr_missing_search_schedule_enabled: bool
    fetcher_radarr_missing_search_schedule_days: str
    fetcher_radarr_missing_search_schedule_start: str
    fetcher_radarr_missing_search_schedule_end: str
    fetcher_radarr_upgrade_search_max_items_per_run: int
    fetcher_radarr_upgrade_search_retry_delay_minutes: int
    fetcher_radarr_upgrade_search_schedule_enabled: bool
    fetcher_radarr_upgrade_search_schedule_days: str
    fetcher_radarr_upgrade_search_schedule_start: str
    fetcher_radarr_upgrade_search_schedule_end: str
    fetcher_arr_search_schedule_timezone: str
    fetcher_sonarr_missing_search_schedule_interval_seconds: int
    fetcher_sonarr_upgrade_search_schedule_interval_seconds: int
    fetcher_radarr_missing_search_schedule_interval_seconds: int
    fetcher_radarr_upgrade_search_schedule_interval_seconds: int

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

    def arr_http_radarr_credentials(self) -> tuple[str | None, str | None]:
        """Radarr HTTP ``(base_url, api_key)`` from exactly one configured pair — never mixed.

        **Pair-level precedence:** If either ``arr_radarr_base_url`` or ``arr_radarr_api_key`` is
        non-None after load, both values are taken **only** from the ``MEDIAMOP_ARR_RADARR_*``
        fields (one may still be None if the operator omitted it). Otherwise both values are
        taken **only** from ``MEDIAMOP_FETCHER_RADARR_*``. Never combine an ARR URL with a
        Fetcher API key or the reverse.
        """

        arr_pair_active = self.arr_radarr_base_url is not None or self.arr_radarr_api_key is not None
        if arr_pair_active:
            return (self.arr_radarr_base_url, self.arr_radarr_api_key)
        return (self.fetcher_radarr_base_url, self.fetcher_radarr_api_key)

    def arr_http_sonarr_credentials(self) -> tuple[str | None, str | None]:
        """Sonarr HTTP ``(base_url, api_key)`` from exactly one configured pair — never mixed.

        Same **pair-level precedence** as :meth:`arr_http_radarr_credentials`, using
        ``MEDIAMOP_ARR_SONARR_*`` vs ``MEDIAMOP_FETCHER_SONARR_*``.
        """

        arr_pair_active = self.arr_sonarr_base_url is not None or self.arr_sonarr_api_key is not None
        if arr_pair_active:
            return (self.arr_sonarr_base_url, self.arr_sonarr_api_key)
        return (self.fetcher_sonarr_base_url, self.fetcher_sonarr_api_key)

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
        if env == "development":
            cors = _expand_loopback_browser_origins_in_development(cors)
            trusted_override = _expand_loopback_browser_origins_in_development(trusted_override)
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
        pruner_workers = clamp_pruner_worker_count(_env_int("MEDIAMOP_PRUNER_WORKER_COUNT", 0))
        pruner_preview_sched_enq = _env_bool("MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_ENQUEUE_ENABLED", True)
        pruner_preview_sched_scan_iv = max(
            10,
            min(300, _env_int("MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_SCAN_INTERVAL_SECONDS", 45)),
        )
        pruner_apply_on = _env_bool("MEDIAMOP_PRUNER_APPLY_ENABLED", False)
        pruner_plex_live_on = _env_bool("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", False)
        pruner_plex_live_abs_max = max(1, min(5000, _env_int("MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS", 150)))
        subber_workers = clamp_subber_worker_count(_env_int("MEDIAMOP_SUBBER_WORKER_COUNT", 0))
        broker_workers = clamp_broker_worker_count(_env_int("MEDIAMOP_BROKER_WORKER_COUNT", 0))
        subber_lib_scan_sched_enq = _env_bool("MEDIAMOP_SUBBER_LIBRARY_SCAN_SCHEDULE_ENQUEUE_ENABLED", True)
        subber_lib_scan_sched_scan_iv = max(
            10,
            min(300, _env_int("MEDIAMOP_SUBBER_LIBRARY_SCAN_SCHEDULE_SCAN_INTERVAL_SECONDS", 45)),
        )
        subber_upgrade_sched_enq = _env_bool("MEDIAMOP_SUBBER_UPGRADE_SCHEDULE_ENQUEUE_ENABLED", True)
        def _refiner_supplied_payload_eval_schedule_enabled() -> bool:
            new_k = "MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_ENABLED"
            old_k = "MEDIAMOP_REFINER_LIBRARY_AUDIT_PASS_SCHEDULE_ENABLED"
            if new_k in os.environ:
                return _env_bool(new_k, False)
            if old_k in os.environ:
                return _env_bool(old_k, False)
            return False

        def _refiner_supplied_payload_eval_schedule_interval_seconds() -> int:
            new_k = "MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_INTERVAL_SECONDS"
            old_k = "MEDIAMOP_REFINER_LIBRARY_AUDIT_PASS_SCHEDULE_INTERVAL_SECONDS"
            if new_k in os.environ:
                return clamp_refiner_schedule_interval_seconds(_env_int(new_k, 3600))
            if old_k in os.environ:
                return clamp_refiner_schedule_interval_seconds(_env_int(old_k, 3600))
            return clamp_refiner_schedule_interval_seconds(3600)

        refiner_payload_eval_on = _refiner_supplied_payload_eval_schedule_enabled()
        refiner_payload_eval_iv = _refiner_supplied_payload_eval_schedule_interval_seconds()
        refiner_wf_scan_dispatch_on = _env_bool(
            "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED",
            False,
        )
        refiner_wf_scan_dispatch_iv = clamp_refiner_schedule_interval_seconds(
            _env_int("MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_INTERVAL_SECONDS", 3600),
        )
        refiner_wf_scan_periodic_remux_enq = _env_bool(
            "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS",
            False,
        )
        refiner_min_file_age = clamp_refiner_min_file_age_seconds(
            _env_int("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", 300),
        )
        refiner_movie_output_min_age = max(
            3600,
            min(30 * 24 * 3600, _env_int("MEDIAMOP_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS", 48 * 3600)),
        )
        refiner_tv_output_min_age = max(
            3600,
            min(30 * 24 * 3600, _env_int("MEDIAMOP_REFINER_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS", 48 * 3600)),
        )
        _legacy_temp_sweep_sched_env = "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_ENABLED"
        _legacy_temp_sweep_iv_env = "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_INTERVAL_SECONDS"

        def _temp_sweep_movie_schedule_enabled() -> bool:
            k = "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED"
            if k in os.environ:
                return _env_bool(k, False)
            if _legacy_temp_sweep_sched_env in os.environ:
                return _env_bool(_legacy_temp_sweep_sched_env, False)
            return False

        def _temp_sweep_tv_schedule_enabled() -> bool:
            k = "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED"
            if k in os.environ:
                return _env_bool(k, False)
            if _legacy_temp_sweep_sched_env in os.environ:
                return _env_bool(_legacy_temp_sweep_sched_env, False)
            return False

        def _temp_sweep_movie_schedule_interval_seconds() -> int:
            k = "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_INTERVAL_SECONDS"
            if k in os.environ:
                return clamp_refiner_schedule_interval_seconds(_env_int(k, 3600))
            if _legacy_temp_sweep_iv_env in os.environ:
                return clamp_refiner_schedule_interval_seconds(_env_int(_legacy_temp_sweep_iv_env, 3600))
            return clamp_refiner_schedule_interval_seconds(3600)

        def _temp_sweep_tv_schedule_interval_seconds() -> int:
            k = "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_INTERVAL_SECONDS"
            if k in os.environ:
                return clamp_refiner_schedule_interval_seconds(_env_int(k, 3600))
            if _legacy_temp_sweep_iv_env in os.environ:
                return clamp_refiner_schedule_interval_seconds(_env_int(_legacy_temp_sweep_iv_env, 3600))
            return clamp_refiner_schedule_interval_seconds(3600)

        refiner_temp_sweep_movie_on = _temp_sweep_movie_schedule_enabled()
        refiner_temp_sweep_movie_iv = _temp_sweep_movie_schedule_interval_seconds()
        refiner_temp_sweep_tv_on = _temp_sweep_tv_schedule_enabled()
        refiner_temp_sweep_tv_iv = _temp_sweep_tv_schedule_interval_seconds()
        refiner_temp_sweep_min_stale = max(
            60,
            min(30 * 24 * 3600, _env_int("MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MIN_STALE_AGE_SECONDS", 86_400)),
        )
        refiner_movie_failure_cleanup_schedule_enabled = _env_bool(
            "MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED",
            False,
        )
        refiner_movie_failure_cleanup_schedule_interval_seconds = clamp_refiner_schedule_interval_seconds(
            _env_int("MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", 3600),
        )
        refiner_tv_failure_cleanup_schedule_enabled = _env_bool(
            "MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED",
            False,
        )
        refiner_tv_failure_cleanup_schedule_interval_seconds = clamp_refiner_schedule_interval_seconds(
            _env_int("MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", 3600),
        )
        refiner_movie_failure_cleanup_grace_period_seconds = max(
            300,
            min(604800, _env_int("MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", 1800)),
        )
        refiner_tv_failure_cleanup_grace_period_seconds = max(
            300,
            min(604800, _env_int("MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", 1800)),
        )
        refiner_remux_root = (os.environ.get("MEDIAMOP_REFINER_REMUX_MEDIA_ROOT") or "").strip()
        refiner_remux_media_root = str(Path(refiner_remux_root).expanduser()) if refiner_remux_root else None
        radarr_base = (os.environ.get("MEDIAMOP_FETCHER_RADARR_BASE_URL") or "").strip()
        if radarr_base and not radarr_base.startswith(("http://", "https://")):
            radarr_base = ""
        radarr_key = (os.environ.get("MEDIAMOP_FETCHER_RADARR_API_KEY") or "").strip()
        sonarr_base = (os.environ.get("MEDIAMOP_FETCHER_SONARR_BASE_URL") or "").strip()
        if sonarr_base and not sonarr_base.startswith(("http://", "https://")):
            sonarr_base = ""
        sonarr_key = (os.environ.get("MEDIAMOP_FETCHER_SONARR_API_KEY") or "").strip()
        arr_radarr_base = (os.environ.get("MEDIAMOP_ARR_RADARR_BASE_URL") or "").strip()
        if arr_radarr_base and not arr_radarr_base.startswith(("http://", "https://")):
            arr_radarr_base = ""
        arr_radarr_key = (os.environ.get("MEDIAMOP_ARR_RADARR_API_KEY") or "").strip()
        arr_sonarr_base = (os.environ.get("MEDIAMOP_ARR_SONARR_BASE_URL") or "").strip()
        if arr_sonarr_base and not arr_sonarr_base.startswith(("http://", "https://")):
            arr_sonarr_base = ""
        arr_sonarr_key = (os.environ.get("MEDIAMOP_ARR_SONARR_API_KEY") or "").strip()
        radarr_sched_on = _env_bool("MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", False)
        radarr_sched_iv = _clamp_failed_import_cleanup_drive_schedule_interval_seconds(
            _env_int("MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_DRIVE_SCHEDULE_INTERVAL_SECONDS", 3600),
        )
        sonarr_sched_on = _env_bool("MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", False)
        sonarr_sched_iv = _clamp_failed_import_cleanup_drive_schedule_interval_seconds(
            _env_int("MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_DRIVE_SCHEDULE_INTERVAL_SECONDS", 3600),
        )

        def _clamp_search_iv(n: int) -> int:
            return _clamp_failed_import_cleanup_drive_schedule_interval_seconds(n)

        def _arr_search_lane_enabled(primary: str, legacy: str, default: bool) -> bool:
            """Prefer lane-prefixed env; accept legacy ``*_SEARCH_{MISSING|UPGRADE}_*`` spelling for migration."""

            if primary in os.environ:
                return _env_bool(primary, default)
            if legacy in os.environ:
                return _env_bool(legacy, default)
            return default

        son_miss_on = _arr_search_lane_enabled(
            "MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_ENABLED",
            "MEDIAMOP_FETCHER_SONARR_SEARCH_MISSING_ENABLED",
            True,
        )
        son_up_on = _arr_search_lane_enabled(
            "MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_ENABLED",
            "MEDIAMOP_FETCHER_SONARR_SEARCH_UPGRADE_ENABLED",
            True,
        )
        rad_miss_on = _arr_search_lane_enabled(
            "MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_ENABLED",
            "MEDIAMOP_FETCHER_RADARR_SEARCH_MISSING_ENABLED",
            True,
        )
        rad_up_on = _arr_search_lane_enabled(
            "MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_ENABLED",
            "MEDIAMOP_FETCHER_RADARR_SEARCH_UPGRADE_ENABLED",
            True,
        )

        _retry_cap = 365 * 24 * 60
        _items_cap = 1000

        def _lane_max(primary: str, legacy: str, default: int) -> int:
            if (os.environ.get(primary) or "").strip():
                return max(1, min(_env_int(primary, default), _items_cap))
            return max(1, min(_env_int(legacy, default), _items_cap))

        def _lane_retry(primary: str, legacy: str, default: int) -> int:
            if (os.environ.get(primary) or "").strip():
                return max(1, min(_env_int(primary, default), _retry_cap))
            return max(1, min(_env_int(legacy, default), _retry_cap))

        def _lane_sched_on(primary: str, legacy_key: str, legacy_default: bool) -> bool:
            if (os.environ.get(primary) or "").strip() != "":
                return _env_bool(primary, legacy_default)
            return _env_bool(legacy_key, legacy_default)

        def _lane_sched_str(primary: str, legacy: str, default: str) -> str:
            if primary in os.environ:
                return (os.environ.get(primary) or "").strip()
            return (os.environ.get(legacy) or default).strip()

        son_max_legacy = "MEDIAMOP_FETCHER_SONARR_SEARCH_MAX_ITEMS_PER_RUN"
        rad_max_legacy = "MEDIAMOP_FETCHER_RADARR_SEARCH_MAX_ITEMS_PER_RUN"
        son_retry_legacy = "MEDIAMOP_FETCHER_SONARR_SEARCH_RETRY_DELAY_MINUTES"
        rad_retry_legacy = "MEDIAMOP_FETCHER_RADARR_SEARCH_RETRY_DELAY_MINUTES"
        son_sched_on_legacy = "MEDIAMOP_FETCHER_SONARR_SEARCH_SCHEDULE_ENABLED"
        son_days_legacy = "MEDIAMOP_FETCHER_SONARR_SEARCH_SCHEDULE_DAYS"
        son_start_legacy = "MEDIAMOP_FETCHER_SONARR_SEARCH_SCHEDULE_START"
        son_end_legacy = "MEDIAMOP_FETCHER_SONARR_SEARCH_SCHEDULE_END"
        rad_sched_on_legacy = "MEDIAMOP_FETCHER_RADARR_SEARCH_SCHEDULE_ENABLED"
        rad_days_legacy = "MEDIAMOP_FETCHER_RADARR_SEARCH_SCHEDULE_DAYS"
        rad_start_legacy = "MEDIAMOP_FETCHER_RADARR_SEARCH_SCHEDULE_START"
        rad_end_legacy = "MEDIAMOP_FETCHER_RADARR_SEARCH_SCHEDULE_END"

        son_miss_max = _lane_max("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_MAX_ITEMS_PER_RUN", son_max_legacy, 50)
        son_up_max = _lane_max("MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_MAX_ITEMS_PER_RUN", son_max_legacy, 50)
        rad_miss_max = _lane_max("MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_MAX_ITEMS_PER_RUN", rad_max_legacy, 50)
        rad_up_max = _lane_max("MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_MAX_ITEMS_PER_RUN", rad_max_legacy, 50)

        son_miss_retry = _lane_retry("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_RETRY_DELAY_MINUTES", son_retry_legacy, 1440)
        son_up_retry = _lane_retry("MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_RETRY_DELAY_MINUTES", son_retry_legacy, 1440)
        rad_miss_retry = _lane_retry("MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_RETRY_DELAY_MINUTES", rad_retry_legacy, 1440)
        rad_up_retry = _lane_retry("MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_RETRY_DELAY_MINUTES", rad_retry_legacy, 1440)

        son_miss_win_on = _lane_sched_on(
            "MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_ENABLED",
            son_sched_on_legacy,
            False,
        )
        son_up_win_on = _lane_sched_on(
            "MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_ENABLED",
            son_sched_on_legacy,
            False,
        )
        rad_miss_win_on = _lane_sched_on(
            "MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_ENABLED",
            rad_sched_on_legacy,
            False,
        )
        rad_up_win_on = _lane_sched_on(
            "MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_ENABLED",
            rad_sched_on_legacy,
            False,
        )

        son_miss_days = _lane_sched_str("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_DAYS", son_days_legacy, "")
        son_up_days = _lane_sched_str("MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_DAYS", son_days_legacy, "")
        rad_miss_days = _lane_sched_str("MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_DAYS", rad_days_legacy, "")
        rad_up_days = _lane_sched_str("MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_DAYS", rad_days_legacy, "")

        son_miss_start = _lane_sched_str(
            "MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_START",
            son_start_legacy,
            "00:00",
        )
        son_up_start = _lane_sched_str(
            "MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_START",
            son_start_legacy,
            "00:00",
        )
        rad_miss_start = _lane_sched_str(
            "MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_START",
            rad_start_legacy,
            "00:00",
        )
        rad_up_start = _lane_sched_str(
            "MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_START",
            rad_start_legacy,
            "00:00",
        )

        son_miss_end = _lane_sched_str(
            "MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_END",
            son_end_legacy,
            "23:59",
        )
        son_up_end = _lane_sched_str(
            "MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_END",
            son_end_legacy,
            "23:59",
        )
        rad_miss_end = _lane_sched_str(
            "MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_END",
            rad_end_legacy,
            "23:59",
        )
        rad_up_end = _lane_sched_str(
            "MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_END",
            rad_end_legacy,
            "23:59",
        )

        arr_tz = (os.environ.get("MEDIAMOP_FETCHER_ARR_SEARCH_SCHEDULE_TIMEZONE") or "UTC").strip() or "UTC"
        son_miss_iv = _clamp_search_iv(_env_int("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_INTERVAL_SECONDS", 3600))
        son_up_iv = _clamp_search_iv(_env_int("MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_INTERVAL_SECONDS", 3600))
        rad_miss_iv = _clamp_search_iv(_env_int("MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_INTERVAL_SECONDS", 3600))
        rad_up_iv = _clamp_search_iv(_env_int("MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_INTERVAL_SECONDS", 3600))

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
            pruner_worker_count=pruner_workers,
            pruner_preview_schedule_enqueue_enabled=pruner_preview_sched_enq,
            pruner_preview_schedule_scan_interval_seconds=pruner_preview_sched_scan_iv,
            pruner_apply_enabled=pruner_apply_on,
            pruner_plex_live_removal_enabled=pruner_plex_live_on,
            pruner_plex_live_abs_max_items=pruner_plex_live_abs_max,
            subber_worker_count=subber_workers,
            broker_worker_count=broker_workers,
            subber_library_scan_schedule_enqueue_enabled=subber_lib_scan_sched_enq,
            subber_library_scan_schedule_scan_interval_seconds=subber_lib_scan_sched_scan_iv,
            subber_upgrade_schedule_enqueue_enabled=subber_upgrade_sched_enq,
            refiner_supplied_payload_evaluation_schedule_enabled=refiner_payload_eval_on,
            refiner_supplied_payload_evaluation_schedule_interval_seconds=refiner_payload_eval_iv,
            refiner_watched_folder_remux_scan_dispatch_schedule_enabled=refiner_wf_scan_dispatch_on,
            refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds=refiner_wf_scan_dispatch_iv,
            refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs=refiner_wf_scan_periodic_remux_enq,
            refiner_watched_folder_min_file_age_seconds=refiner_min_file_age,
            refiner_movie_output_cleanup_min_age_seconds=refiner_movie_output_min_age,
            refiner_tv_output_cleanup_min_age_seconds=refiner_tv_output_min_age,
            refiner_work_temp_stale_sweep_movie_schedule_enabled=refiner_temp_sweep_movie_on,
            refiner_work_temp_stale_sweep_movie_schedule_interval_seconds=refiner_temp_sweep_movie_iv,
            refiner_work_temp_stale_sweep_tv_schedule_enabled=refiner_temp_sweep_tv_on,
            refiner_work_temp_stale_sweep_tv_schedule_interval_seconds=refiner_temp_sweep_tv_iv,
            refiner_work_temp_stale_sweep_min_stale_age_seconds=refiner_temp_sweep_min_stale,
            refiner_movie_failure_cleanup_schedule_enabled=refiner_movie_failure_cleanup_schedule_enabled,
            refiner_movie_failure_cleanup_schedule_interval_seconds=refiner_movie_failure_cleanup_schedule_interval_seconds,
            refiner_tv_failure_cleanup_schedule_enabled=refiner_tv_failure_cleanup_schedule_enabled,
            refiner_tv_failure_cleanup_schedule_interval_seconds=refiner_tv_failure_cleanup_schedule_interval_seconds,
            refiner_movie_failure_cleanup_grace_period_seconds=refiner_movie_failure_cleanup_grace_period_seconds,
            refiner_tv_failure_cleanup_grace_period_seconds=refiner_tv_failure_cleanup_grace_period_seconds,
            refiner_remux_media_root=refiner_remux_media_root,
            fetcher_radarr_base_url=radarr_base or None,
            fetcher_radarr_api_key=radarr_key or None,
            fetcher_sonarr_base_url=sonarr_base or None,
            fetcher_sonarr_api_key=sonarr_key or None,
            arr_radarr_base_url=arr_radarr_base or None,
            arr_radarr_api_key=arr_radarr_key or None,
            arr_sonarr_base_url=arr_sonarr_base or None,
            arr_sonarr_api_key=arr_sonarr_key or None,
            failed_import_radarr_cleanup_drive_schedule_enabled=radarr_sched_on,
            failed_import_radarr_cleanup_drive_schedule_interval_seconds=radarr_sched_iv,
            failed_import_sonarr_cleanup_drive_schedule_enabled=sonarr_sched_on,
            failed_import_sonarr_cleanup_drive_schedule_interval_seconds=sonarr_sched_iv,
            fetcher_sonarr_missing_search_enabled=son_miss_on,
            fetcher_sonarr_upgrade_search_enabled=son_up_on,
            fetcher_radarr_missing_search_enabled=rad_miss_on,
            fetcher_radarr_upgrade_search_enabled=rad_up_on,
            fetcher_sonarr_missing_search_max_items_per_run=son_miss_max,
            fetcher_sonarr_missing_search_retry_delay_minutes=son_miss_retry,
            fetcher_sonarr_missing_search_schedule_enabled=son_miss_win_on,
            fetcher_sonarr_missing_search_schedule_days=son_miss_days,
            fetcher_sonarr_missing_search_schedule_start=son_miss_start,
            fetcher_sonarr_missing_search_schedule_end=son_miss_end,
            fetcher_sonarr_upgrade_search_max_items_per_run=son_up_max,
            fetcher_sonarr_upgrade_search_retry_delay_minutes=son_up_retry,
            fetcher_sonarr_upgrade_search_schedule_enabled=son_up_win_on,
            fetcher_sonarr_upgrade_search_schedule_days=son_up_days,
            fetcher_sonarr_upgrade_search_schedule_start=son_up_start,
            fetcher_sonarr_upgrade_search_schedule_end=son_up_end,
            fetcher_radarr_missing_search_max_items_per_run=rad_miss_max,
            fetcher_radarr_missing_search_retry_delay_minutes=rad_miss_retry,
            fetcher_radarr_missing_search_schedule_enabled=rad_miss_win_on,
            fetcher_radarr_missing_search_schedule_days=rad_miss_days,
            fetcher_radarr_missing_search_schedule_start=rad_miss_start,
            fetcher_radarr_missing_search_schedule_end=rad_miss_end,
            fetcher_radarr_upgrade_search_max_items_per_run=rad_up_max,
            fetcher_radarr_upgrade_search_retry_delay_minutes=rad_up_retry,
            fetcher_radarr_upgrade_search_schedule_enabled=rad_up_win_on,
            fetcher_radarr_upgrade_search_schedule_days=rad_up_days,
            fetcher_radarr_upgrade_search_schedule_start=rad_up_start,
            fetcher_radarr_upgrade_search_schedule_end=rad_up_end,
            fetcher_arr_search_schedule_timezone=arr_tz,
            fetcher_sonarr_missing_search_schedule_interval_seconds=son_miss_iv,
            fetcher_sonarr_upgrade_search_schedule_interval_seconds=son_up_iv,
            fetcher_radarr_missing_search_schedule_interval_seconds=rad_miss_iv,
            fetcher_radarr_upgrade_search_schedule_interval_seconds=rad_up_iv,
        )
