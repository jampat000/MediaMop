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
from mediamop.modules.refiner.refiner_family_intervals import (
    clamp_refiner_min_file_age_seconds,
    clamp_refiner_schedule_interval_seconds,
)
from mediamop.modules.refiner.worker_limits import clamp_refiner_worker_count
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
    # Refiner ffprobe preflight depth (FileFlows-style Video File parity).
    refiner_probe_size_mb: int
    refiner_analyze_duration_seconds: int
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
    # Shared *arr HTTP (env: MEDIAMOP_ARR_*). SQLite operator settings may override per-request.
    arr_radarr_base_url: str | None
    arr_radarr_api_key: str | None
    arr_sonarr_base_url: str | None
    arr_sonarr_api_key: str | None

    @property
    def trusted_browser_origins(self) -> tuple[str, ...]:
        """Origins allowed for unsafe browser POST CSRF defense (Origin/Referer)."""

        if self.trusted_browser_origins_override:
            return self.trusted_browser_origins_override
        return self.cors_origins

    def arr_http_radarr_credentials(self) -> tuple[str | None, str | None]:
        """Radarr HTTP ``(base_url, api_key)`` from ``MEDIAMOP_ARR_RADARR_*`` at process start."""

        return (self.arr_radarr_base_url, self.arr_radarr_api_key)

    def arr_http_sonarr_credentials(self) -> tuple[str | None, str | None]:
        """Sonarr HTTP ``(base_url, api_key)`` from ``MEDIAMOP_ARR_SONARR_*`` at process start."""

        return (self.arr_sonarr_base_url, self.arr_sonarr_api_key)

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

        home_path, db_p, backup_p, log_p, temp_p = resolve_all_runtime_paths()
        ensure_runtime_directories(
            db_path=db_p,
            backup_dir=backup_p,
            log_dir=log_p,
            temp_dir=temp_p,
        )
        assert_sqlite_db_location_usable(db_p)
        db_url = sqlalchemy_sqlite_url(db_p)
        refiner_workers = clamp_refiner_worker_count(_env_int("MEDIAMOP_REFINER_WORKER_COUNT", 8))
        pruner_workers = clamp_pruner_worker_count(_env_int("MEDIAMOP_PRUNER_WORKER_COUNT", 1))
        pruner_preview_sched_enq = _env_bool("MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_ENQUEUE_ENABLED", True)
        pruner_preview_sched_scan_iv = max(
            10,
            min(300, _env_int("MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_SCAN_INTERVAL_SECONDS", 45)),
        )
        pruner_apply_on = _env_bool("MEDIAMOP_PRUNER_APPLY_ENABLED", False)
        pruner_plex_live_on = _env_bool("MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED", False)
        pruner_plex_live_abs_max = max(1, min(5000, _env_int("MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS", 150)))
        subber_workers = clamp_subber_worker_count(_env_int("MEDIAMOP_SUBBER_WORKER_COUNT", 1))
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
        refiner_probe_size_mb = max(1, min(1024, _env_int("MEDIAMOP_REFINER_PROBE_SIZE_MB", 10)))
        refiner_analyze_duration_seconds = max(
            1,
            min(300, _env_int("MEDIAMOP_REFINER_ANALYZE_DURATION_SECONDS", 10)),
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
        arr_radarr_base = (os.environ.get("MEDIAMOP_ARR_RADARR_BASE_URL") or "").strip()
        if arr_radarr_base and not arr_radarr_base.startswith(("http://", "https://")):
            arr_radarr_base = ""
        arr_radarr_key = (os.environ.get("MEDIAMOP_ARR_RADARR_API_KEY") or "").strip()
        arr_sonarr_base = (os.environ.get("MEDIAMOP_ARR_SONARR_BASE_URL") or "").strip()
        if arr_sonarr_base and not arr_sonarr_base.startswith(("http://", "https://")):
            arr_sonarr_base = ""
        arr_sonarr_key = (os.environ.get("MEDIAMOP_ARR_SONARR_API_KEY") or "").strip()

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
            refiner_worker_count=refiner_workers,
            pruner_worker_count=pruner_workers,
            pruner_preview_schedule_enqueue_enabled=pruner_preview_sched_enq,
            pruner_preview_schedule_scan_interval_seconds=pruner_preview_sched_scan_iv,
            pruner_apply_enabled=pruner_apply_on,
            pruner_plex_live_removal_enabled=pruner_plex_live_on,
            pruner_plex_live_abs_max_items=pruner_plex_live_abs_max,
            subber_worker_count=subber_workers,
            subber_library_scan_schedule_enqueue_enabled=subber_lib_scan_sched_enq,
            subber_library_scan_schedule_scan_interval_seconds=subber_lib_scan_sched_scan_iv,
            subber_upgrade_schedule_enqueue_enabled=subber_upgrade_sched_enq,
            refiner_supplied_payload_evaluation_schedule_enabled=refiner_payload_eval_on,
            refiner_supplied_payload_evaluation_schedule_interval_seconds=refiner_payload_eval_iv,
            refiner_watched_folder_remux_scan_dispatch_schedule_enabled=refiner_wf_scan_dispatch_on,
            refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds=refiner_wf_scan_dispatch_iv,
            refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs=refiner_wf_scan_periodic_remux_enq,
            refiner_probe_size_mb=refiner_probe_size_mb,
            refiner_analyze_duration_seconds=refiner_analyze_duration_seconds,
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
            arr_radarr_base_url=arr_radarr_base or None,
            arr_radarr_api_key=arr_radarr_key or None,
            arr_sonarr_base_url=arr_sonarr_base or None,
            arr_sonarr_api_key=arr_sonarr_key or None,
        )
