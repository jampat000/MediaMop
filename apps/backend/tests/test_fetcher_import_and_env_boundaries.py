"""Structural boundaries: Fetcher must not depend on Refiner DTO modules; *arr env wiring."""

from __future__ import annotations

import importlib.util

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.schemas_recover_finalize import RecoverFinalizeFailureIn


def test_refiner_schemas_recovery_module_removed() -> None:
    assert importlib.util.find_spec("mediamop.modules.refiner.schemas_recovery") is None


def test_fetcher_recover_schemas_live_under_fetcher_package() -> None:
    row = RecoverFinalizeFailureIn(confirm=True, csrf_token="t")
    assert row.confirm is True


def test_fetcher_radarr_base_url_reads_mediamop_prefixed_fetcher_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://127.0.0.1:7878")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "secret")
    s = MediaMopSettings.load()
    assert s.fetcher_radarr_base_url == "http://127.0.0.1:7878"
    assert s.fetcher_radarr_api_key == "secret"


def test_legacy_refiner_radarr_base_url_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_RADARR_BASE_URL", "http://legacy-wrong:7878")
    monkeypatch.delenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_FETCHER_RADARR_API_KEY", raising=False)
    s = MediaMopSettings.load()
    assert s.fetcher_radarr_base_url is None


def test_fetcher_arr_search_lane_enable_prefers_missing_search_prefixed_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_ENABLED", "0")
    monkeypatch.delenv("MEDIAMOP_FETCHER_SONARR_SEARCH_MISSING_ENABLED", raising=False)
    s = MediaMopSettings.load()
    assert s.fetcher_sonarr_missing_search_enabled is False


def test_fetcher_arr_search_lane_enable_legacy_search_missing_env_still_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_ENABLED", raising=False)
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_SEARCH_MISSING_ENABLED", "0")
    s = MediaMopSettings.load()
    assert s.fetcher_sonarr_missing_search_enabled is False


def test_fetcher_sonarr_missing_search_enable_canonical_wins_when_legacy_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical ``MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_ENABLED`` must override legacy when both are set."""

    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_SEARCH_MISSING_ENABLED", "1")
    s = MediaMopSettings.load()
    assert s.fetcher_sonarr_missing_search_enabled is False


def test_fetcher_sonarr_missing_search_enable_canonical_true_wins_over_legacy_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_ENABLED", "1")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_SEARCH_MISSING_ENABLED", "0")
    s = MediaMopSettings.load()
    assert s.fetcher_sonarr_missing_search_enabled is True


def test_mediamop_arr_radarr_env_loads_distinct_from_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://arr-neutral:7878")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "arr-key")
    monkeypatch.delenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_FETCHER_RADARR_API_KEY", raising=False)
    s = MediaMopSettings.load()
    assert s.arr_radarr_base_url == "http://arr-neutral:7878"
    assert s.arr_radarr_api_key == "arr-key"


def test_arr_http_radarr_credentials_prefers_neutral_over_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://arr.example")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "ak")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://fetcher.example")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "fk")
    s = MediaMopSettings.load()
    base, key = s.arr_http_radarr_credentials()
    assert base == "http://arr.example"
    assert key == "ak"


def test_arr_http_radarr_credentials_canonical_arr_pair_wins_when_fetcher_pair_also_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0008 §6: both full pairs configured — neutral ``MEDIAMOP_ARR_RADARR_*`` wins entirely."""

    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://canonical-arr")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "arr-secret")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://legacy-fetcher")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "fetcher-secret")
    s = MediaMopSettings.load()
    base, key = s.arr_http_radarr_credentials()
    assert base == "http://canonical-arr"
    assert key == "arr-secret"


def test_arr_http_radarr_credentials_pair_level_half_arr_url_only_no_fetcher_key_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pair-level rule: partial ARR pair does not take Fetcher API key (no per-field mixing)."""

    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://arr-url-only")
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_API_KEY", raising=False)
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://fetcher")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "fetcher-key")
    s = MediaMopSettings.load()
    base, key = s.arr_http_radarr_credentials()
    assert base == "http://arr-url-only"
    assert key is None


def test_arr_http_radarr_credentials_pair_level_half_arr_key_only_no_fetcher_url_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_BASE_URL", raising=False)
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "arr-key-only")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://fetcher-only")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "fk")
    s = MediaMopSettings.load()
    base, key = s.arr_http_radarr_credentials()
    assert base is None
    assert key == "arr-key-only"


def test_arr_http_radarr_credentials_falls_back_to_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_API_KEY", raising=False)
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://fallback:7878")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "fb")
    s = MediaMopSettings.load()
    base, key = s.arr_http_radarr_credentials()
    assert base == "http://fallback:7878"
    assert key == "fb"


def test_mediamop_arr_sonarr_env_loads_distinct_from_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_BASE_URL", "http://arr-neutral:8989")
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_API_KEY", "arr-sonarr-key")
    monkeypatch.delenv("MEDIAMOP_FETCHER_SONARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_FETCHER_SONARR_API_KEY", raising=False)
    s = MediaMopSettings.load()
    assert s.arr_sonarr_base_url == "http://arr-neutral:8989"
    assert s.arr_sonarr_api_key == "arr-sonarr-key"


def test_arr_http_sonarr_credentials_prefers_neutral_over_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_BASE_URL", "http://arr.example")
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_API_KEY", "ak")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_BASE_URL", "http://fetcher.example")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_API_KEY", "fk")
    s = MediaMopSettings.load()
    base, key = s.arr_http_sonarr_credentials()
    assert base == "http://arr.example"
    assert key == "ak"


def test_arr_http_sonarr_credentials_canonical_arr_pair_wins_when_fetcher_pair_also_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_BASE_URL", "http://canonical-arr")
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_API_KEY", "arr-secret")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_BASE_URL", "http://legacy-fetcher")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_API_KEY", "fetcher-secret")
    s = MediaMopSettings.load()
    base, key = s.arr_http_sonarr_credentials()
    assert base == "http://canonical-arr"
    assert key == "arr-secret"


def test_arr_http_sonarr_credentials_pair_level_half_arr_url_only_no_fetcher_key_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_BASE_URL", "http://arr-url-only")
    monkeypatch.delenv("MEDIAMOP_ARR_SONARR_API_KEY", raising=False)
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_BASE_URL", "http://fetcher")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_API_KEY", "fetcher-key")
    s = MediaMopSettings.load()
    base, key = s.arr_http_sonarr_credentials()
    assert base == "http://arr-url-only"
    assert key is None


def test_arr_http_sonarr_credentials_pair_level_half_arr_key_only_no_fetcher_url_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MEDIAMOP_ARR_SONARR_BASE_URL", raising=False)
    monkeypatch.setenv("MEDIAMOP_ARR_SONARR_API_KEY", "arr-key-only")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_BASE_URL", "http://fetcher-only")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_API_KEY", "fk")
    s = MediaMopSettings.load()
    base, key = s.arr_http_sonarr_credentials()
    assert base is None
    assert key == "arr-key-only"


def test_arr_http_sonarr_credentials_falls_back_to_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_ARR_SONARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_ARR_SONARR_API_KEY", raising=False)
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_BASE_URL", "http://fallback:8989")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_API_KEY", "fb")
    s = MediaMopSettings.load()
    base, key = s.arr_http_sonarr_credentials()
    assert base == "http://fallback:8989"
    assert key == "fb"
