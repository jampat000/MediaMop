"""Structural boundaries: Fetcher must not depend on Refiner DTO modules; *arr env names are Fetcher-owned."""

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


def test_fetcher_radarr_base_url_reads_mediomop_fetcher_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", "http://127.0.0.1:7878")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_API_KEY", "secret")
    s = MediaMopSettings.load()
    assert s.fetcher_radarr_base_url == "http://127.0.0.1:7878"
    assert s.fetcher_radarr_api_key == "secret"


def test_legacy_mediomop_refiner_arr_base_url_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_RADARR_BASE_URL", "http://legacy-wrong:7878")
    monkeypatch.delenv("MEDIAMOP_FETCHER_RADARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_FETCHER_RADARR_API_KEY", raising=False)
    s = MediaMopSettings.load()
    assert s.fetcher_radarr_base_url is None
