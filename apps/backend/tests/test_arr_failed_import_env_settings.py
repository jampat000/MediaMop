"""Failed import cleanup policy settings (env + MediaMopSettings seam)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.arr_failed_import.decision import decide_failed_import_cleanup_eligibility
from mediamop.modules.arr_failed_import.policy import default_failed_import_cleanup_policy
from mediamop.modules.arr_failed_import.env_settings import (
    AppFailedImportCleanupPolicySettings,
    RefinerFailedImportCleanupSettingsBundle,
    default_refiner_failed_import_cleanup_settings_bundle,
    load_refiner_failed_import_cleanup_settings_bundle,
)


def _clear_refiner_cleanup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = (
        "MEDIAMOP_REFINER_RADARR_CLEANUP_QUALITY",
        "MEDIAMOP_REFINER_RADARR_CLEANUP_UNMATCHED",
        "MEDIAMOP_REFINER_RADARR_CLEANUP_CORRUPT",
        "MEDIAMOP_REFINER_RADARR_CLEANUP_DOWNLOAD_FAILED",
        "MEDIAMOP_REFINER_RADARR_CLEANUP_IMPORT_FAILED",
        "MEDIAMOP_REFINER_SONARR_CLEANUP_QUALITY",
        "MEDIAMOP_REFINER_SONARR_CLEANUP_UNMATCHED",
        "MEDIAMOP_REFINER_SONARR_CLEANUP_CORRUPT",
        "MEDIAMOP_REFINER_SONARR_CLEANUP_DOWNLOAD_FAILED",
        "MEDIAMOP_REFINER_SONARR_CLEANUP_IMPORT_FAILED",
    )
    for k in keys:
        monkeypatch.delenv(k, raising=False)


def test_default_bundle_resolves_to_domain_default_policy_all_off() -> None:
    b = default_refiner_failed_import_cleanup_settings_bundle()
    assert b.radarr.to_failed_import_cleanup_policy() == default_failed_import_cleanup_policy()
    assert b.sonarr.to_failed_import_cleanup_policy() == default_failed_import_cleanup_policy()


def test_load_bundle_reads_radarr_env_independently_of_sonarr(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_refiner_cleanup_env(monkeypatch)
    monkeypatch.setenv("MEDIAMOP_REFINER_RADARR_CLEANUP_CORRUPT", "1")
    monkeypatch.setenv("MEDIAMOP_REFINER_SONARR_CLEANUP_IMPORT_FAILED", "true")
    b = load_refiner_failed_import_cleanup_settings_bundle()
    rp = b.radarr_policy()
    sp = b.sonarr_policy()
    assert rp.remove_corrupt_imports is True
    assert rp.remove_failed_imports is False
    assert sp.remove_failed_imports is True
    assert sp.remove_corrupt_imports is False


def test_pending_unknown_remain_non_destructive_via_resolved_radarr_policy() -> None:
    b = default_refiner_failed_import_cleanup_settings_bundle()
    p = b.radarr_policy()
    assert decide_failed_import_cleanup_eligibility("Downloaded - Waiting to Import", p).cleanup_eligible is False
    assert decide_failed_import_cleanup_eligibility("no known phrases", p).cleanup_eligible is False


def test_mediomop_settings_radarr_and_sonarr_policies_delegate_to_bundle() -> None:
    base = MediaMopSettings.load()
    bundle = RefinerFailedImportCleanupSettingsBundle(
        radarr=AppFailedImportCleanupPolicySettings(remove_quality_rejections=True),
        sonarr=AppFailedImportCleanupPolicySettings(remove_failed_downloads=True),
    )
    s = replace(base, refiner_failed_import_cleanup=bundle)
    assert s.radarr_failed_import_cleanup_policy().remove_quality_rejections is True
    assert s.radarr_failed_import_cleanup_policy().remove_failed_downloads is False
    assert s.sonarr_failed_import_cleanup_policy().remove_failed_downloads is True
    assert s.sonarr_failed_import_cleanup_policy().remove_quality_rejections is False
