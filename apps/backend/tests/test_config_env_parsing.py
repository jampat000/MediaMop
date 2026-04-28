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


def test_credentialed_cors_rejects_wildcard_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="cannot include"):
        MediaMopSettings.load()


def test_trusted_proxy_ips_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_TRUSTED_PROXY_IPS", "10.0.0.1,172.18.0.0/16")
    s = MediaMopSettings.load()
    assert s.trusted_proxy_ips == ("10.0.0.1", "172.18.0.0/16")


def test_domain_settings_views_map_existing_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "60")
    monkeypatch.setenv("MEDIAMOP_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "12")
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "3")
    monkeypatch.setenv("MEDIAMOP_PRUNER_WORKER_COUNT", "2")
    monkeypatch.setenv("MEDIAMOP_SUBBER_WORKER_COUNT", "4")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://radarr.local:7878")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "radarr-key")

    s = MediaMopSettings.load()

    assert s.session.idle_minutes == 60
    assert s.auth.login_rate_max_attempts == 12
    assert s.refiner.worker_count == 3
    assert s.pruner.worker_count == 2
    assert s.subber.worker_count == 4
    assert s.arr.radarr_base_url == "http://radarr.local:7878"
    assert s.arr.radarr_api_key == "radarr-key"
