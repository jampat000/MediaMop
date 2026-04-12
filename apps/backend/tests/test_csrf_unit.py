"""CSRF token signing and optional app wiring (no live database required)."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.modules.arr_failed_import.env_settings import (
    default_failed_import_cleanup_settings_bundle,
)
from mediamop.platform.auth.csrf import (
    issue_csrf_token,
    validate_browser_post_origin,
    verify_csrf_token,
)


def _csrf_settings(**overrides: object) -> MediaMopSettings:
    home = Path(tempfile.gettempdir()) / "mediamop-csrf-unit"
    db = home / "data" / "mediamop.sqlite3"
    base = dict(
        env="development",
        log_level="INFO",
        cors_origins=(),
        session_secret="x",
        session_cookie_name="mediamop_session",
        session_cookie_secure=False,
        session_cookie_samesite="lax",
        session_idle_minutes=720,
        session_absolute_days=14,
        trusted_browser_origins_override=(),
        auth_login_rate_max_attempts=30,
        auth_login_rate_window_seconds=60,
        bootstrap_rate_max_attempts=10,
        bootstrap_rate_window_seconds=3600,
        security_enable_hsts=False,
        mediamop_home=str(home),
        db_path=str(db),
        backup_dir=str(home / "backups"),
        log_dir=str(home / "logs"),
        temp_dir=str(home / "temp"),
        sqlalchemy_database_url="sqlite:///" + db.as_posix(),
        fetcher_base_url=None,
        failed_import_cleanup_env=default_failed_import_cleanup_settings_bundle(),
        fetcher_worker_count=1,
        refiner_worker_count=0,
        trimmer_worker_count=0,
        subber_worker_count=0,
        fetcher_radarr_base_url=None,
        fetcher_radarr_api_key=None,
        fetcher_sonarr_base_url=None,
        fetcher_sonarr_api_key=None,
        arr_radarr_base_url=None,
        arr_radarr_api_key=None,
        arr_sonarr_base_url=None,
        arr_sonarr_api_key=None,
        failed_import_radarr_cleanup_drive_schedule_enabled=False,
        failed_import_radarr_cleanup_drive_schedule_interval_seconds=3600,
        failed_import_sonarr_cleanup_drive_schedule_enabled=False,
        failed_import_sonarr_cleanup_drive_schedule_interval_seconds=3600,
        fetcher_sonarr_missing_search_enabled=True,
        fetcher_sonarr_upgrade_search_enabled=True,
        fetcher_radarr_missing_search_enabled=True,
        fetcher_radarr_upgrade_search_enabled=True,
        fetcher_sonarr_missing_search_max_items_per_run=50,
        fetcher_sonarr_missing_search_retry_delay_minutes=1440,
        fetcher_sonarr_missing_search_schedule_enabled=False,
        fetcher_sonarr_missing_search_schedule_days="",
        fetcher_sonarr_missing_search_schedule_start="00:00",
        fetcher_sonarr_missing_search_schedule_end="23:59",
        fetcher_sonarr_upgrade_search_max_items_per_run=50,
        fetcher_sonarr_upgrade_search_retry_delay_minutes=1440,
        fetcher_sonarr_upgrade_search_schedule_enabled=False,
        fetcher_sonarr_upgrade_search_schedule_days="",
        fetcher_sonarr_upgrade_search_schedule_start="00:00",
        fetcher_sonarr_upgrade_search_schedule_end="23:59",
        fetcher_radarr_missing_search_max_items_per_run=50,
        fetcher_radarr_missing_search_retry_delay_minutes=1440,
        fetcher_radarr_missing_search_schedule_enabled=False,
        fetcher_radarr_missing_search_schedule_days="",
        fetcher_radarr_missing_search_schedule_start="00:00",
        fetcher_radarr_missing_search_schedule_end="23:59",
        fetcher_radarr_upgrade_search_max_items_per_run=50,
        fetcher_radarr_upgrade_search_retry_delay_minutes=1440,
        fetcher_radarr_upgrade_search_schedule_enabled=False,
        fetcher_radarr_upgrade_search_schedule_days="",
        fetcher_radarr_upgrade_search_schedule_start="00:00",
        fetcher_radarr_upgrade_search_schedule_end="23:59",
        fetcher_arr_search_schedule_timezone="UTC",
        fetcher_sonarr_missing_search_schedule_interval_seconds=3600,
        fetcher_sonarr_upgrade_search_schedule_interval_seconds=3600,
        fetcher_radarr_missing_search_schedule_interval_seconds=3600,
        fetcher_radarr_upgrade_search_schedule_interval_seconds=3600,
        refiner_supplied_payload_evaluation_schedule_enabled=False,
        refiner_supplied_payload_evaluation_schedule_interval_seconds=3600,
        refiner_remux_media_root=None,
    )
    base.update(overrides)
    return MediaMopSettings(**base)  # type: ignore[arg-type]


def test_issue_and_verify_csrf() -> None:
    secret = "unit-test-csrf-secret-key-32chars-minimum!"
    t = issue_csrf_token(secret)
    assert verify_csrf_token(secret, t) is True
    assert verify_csrf_token("wrong-secret", t) is False
    assert verify_csrf_token(secret, "tampered") is False


def _request_with_headers(items: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": items,
        }
    )


def test_origin_skipped_when_no_trusted_list() -> None:
    settings = _csrf_settings(cors_origins=())
    req = _request_with_headers([])
    validate_browser_post_origin(req, settings)  # no-op


def test_origin_enforced_when_configured() -> None:
    from fastapi import HTTPException

    settings = _csrf_settings(cors_origins=("http://127.0.0.1:8782",))
    good = _request_with_headers([(b"origin", b"http://127.0.0.1:8782")])
    validate_browser_post_origin(good, settings)
    bad = _request_with_headers([(b"origin", b"http://evil.test")])
    try:
        validate_browser_post_origin(bad, settings)
        raise AssertionError("expected 403")
    except HTTPException as e:
        assert e.status_code == 403


def test_origin_uses_trusted_browser_origins_override() -> None:
    from fastapi import HTTPException

    settings = _csrf_settings(
        trusted_browser_origins_override=("http://127.0.0.1:9000",),
    )
    good = _request_with_headers([(b"origin", b"http://127.0.0.1:9000")])
    validate_browser_post_origin(good, settings)
    bad = _request_with_headers([(b"origin", b"http://127.0.0.1:8782")])
    with pytest.raises(HTTPException) as excinfo:
        validate_browser_post_origin(bad, settings)
    assert excinfo.value.status_code == 403


def test_auth_csrf_endpoint_503_without_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid loading real apps/backend/.env (would repopulate the secret after delenv).
    monkeypatch.setattr(
        "mediamop.core.config._load_backend_dotenv_if_present",
        lambda: None,
    )
    monkeypatch.delenv("MEDIAMOP_SESSION_SECRET", raising=False)
    app = create_app()
    with TestClient(app) as cli:
        r = cli.get("/api/v1/auth/csrf")
    assert r.status_code == 503
