"""Safe parsing of select integer env vars in WeirSettings.load."""

from __future__ import annotations

import pytest

from weir.core.config import WeirSettings


def test_session_ttl_integers_ignore_malformed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_SESSION_IDLE_MINUTES", "not-a-number")
    monkeypatch.setenv("WEIR_SESSION_ABSOLUTE_DAYS", "xyz")
    s = WeirSettings.load()
    assert s.session_idle_minutes == 20160
    assert s.session_absolute_days == 90


def test_session_ttl_integers_respect_valid_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_SESSION_IDLE_MINUTES", "60")
    monkeypatch.setenv("WEIR_SESSION_ABSOLUTE_DAYS", "7")
    s = WeirSettings.load()
    assert s.session_idle_minutes == 60
    assert s.session_absolute_days == 7


def test_session_ttl_clamps_to_at_least_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_SESSION_IDLE_MINUTES", "0")
    monkeypatch.setenv("WEIR_SESSION_ABSOLUTE_DAYS", "-5")
    s = WeirSettings.load()
    assert s.session_idle_minutes == 1
    assert s.session_absolute_days == 1


def test_credentialed_cors_rejects_wildcard_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="cannot include"):
        WeirSettings.load()


def test_trusted_proxy_ips_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_TRUSTED_PROXY_IPS", "10.0.0.1,172.18.0.0/16")
    s = WeirSettings.load()
    assert s.trusted_proxy_ips == ("10.0.0.1", "172.18.0.0/16")


def test_domain_settings_views_map_existing_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_SESSION_IDLE_MINUTES", "60")
    monkeypatch.setenv("WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "12")
    monkeypatch.setenv("WEIR_REFINER_WORKER_COUNT", "3")
    monkeypatch.setenv("WEIR_ARR_RADARR_BASE_URL", "http://radarr.local:7878")
    monkeypatch.setenv("WEIR_ARR_RADARR_API_KEY", "radarr-key")

    s = WeirSettings.load()

    assert s.session.idle_minutes == 60
    assert s.auth.login_rate_max_attempts == 12
    assert s.refiner.worker_count == 3
    assert s.arr.radarr_base_url == "http://radarr.local:7878"
    assert s.arr.radarr_api_key == "radarr-key"
