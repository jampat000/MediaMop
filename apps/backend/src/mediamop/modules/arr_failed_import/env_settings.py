"""Failed-import cleanup toggles loaded from the process environment.

Radarr and Sonarr each have their own toggle set so defaults and future persistence
can diverge without a shared blob.

Primary env names use ``MEDIAMOP_FAILED_IMPORT_*``. Legacy ``MEDIAMOP_REFINER_*_CLEANUP_*``
names for the same toggles are still read when the primary variable for a given toggle
is unset (empty string only — a set primary always wins). Precedence: **primary first**,
then legacy, then default off.

Primary pattern:

- ``MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_QUALITY``
- ``MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_UNMATCHED``
- … (same suffixes for Radarr / Sonarr)

Legacy (read only if primary key absent):

- ``MEDIAMOP_REFINER_RADARR_CLEANUP_QUALITY``, etc.

Truthy: ``1``, ``true``, ``yes``, ``on`` (case-insensitive). Falsy: ``0``, ``false``,
``no``, ``off``, or empty/unset for both primary and legacy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy


def _cleanup_toggle(new_key: str, legacy_key: str) -> bool:
    """Bool toggle: non-empty primary env wins; else non-empty legacy; else False."""

    if (os.environ.get(new_key) or "").strip() != "":
        raw = (os.environ.get(new_key) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        return False
    if (os.environ.get(legacy_key) or "").strip() != "":
        raw = (os.environ.get(legacy_key) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        return False
    return False


@dataclass(frozen=True, slots=True)
class AppFailedImportCleanupPolicySettings:
    """Failed import cleanup toggles for one *arr app (Radarr or Sonarr)."""

    remove_quality_rejections: bool = False
    remove_unmatched_manual_import_rejections: bool = False
    remove_corrupt_imports: bool = False
    remove_failed_downloads: bool = False
    remove_failed_imports: bool = False

    def to_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        return FailedImportCleanupPolicy(
            remove_quality_rejections=self.remove_quality_rejections,
            remove_unmatched_manual_import_rejections=self.remove_unmatched_manual_import_rejections,
            remove_corrupt_imports=self.remove_corrupt_imports,
            remove_failed_downloads=self.remove_failed_downloads,
            remove_failed_imports=self.remove_failed_imports,
        )


@dataclass(frozen=True, slots=True)
class FailedImportCleanupSettingsBundle:
    """App-separated cleanup policy settings; resolve with :meth:`radarr_policy` / :meth:`sonarr_policy`."""

    radarr: AppFailedImportCleanupPolicySettings
    sonarr: AppFailedImportCleanupPolicySettings

    def radarr_policy(self) -> FailedImportCleanupPolicy:
        return self.radarr.to_failed_import_cleanup_policy()

    def sonarr_policy(self) -> FailedImportCleanupPolicy:
        return self.sonarr.to_failed_import_cleanup_policy()


def _load_radarr_cleanup_settings() -> AppFailedImportCleanupPolicySettings:
    p_new = "MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_"
    p_leg = "MEDIAMOP_REFINER_RADARR_CLEANUP_"
    return AppFailedImportCleanupPolicySettings(
        remove_quality_rejections=_cleanup_toggle(p_new + "QUALITY", p_leg + "QUALITY"),
        remove_unmatched_manual_import_rejections=_cleanup_toggle(p_new + "UNMATCHED", p_leg + "UNMATCHED"),
        remove_corrupt_imports=_cleanup_toggle(p_new + "CORRUPT", p_leg + "CORRUPT"),
        remove_failed_downloads=_cleanup_toggle(p_new + "DOWNLOAD_FAILED", p_leg + "DOWNLOAD_FAILED"),
        remove_failed_imports=_cleanup_toggle(p_new + "IMPORT_FAILED", p_leg + "IMPORT_FAILED"),
    )


def _load_sonarr_cleanup_settings() -> AppFailedImportCleanupPolicySettings:
    p_new = "MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_"
    p_leg = "MEDIAMOP_REFINER_SONARR_CLEANUP_"
    return AppFailedImportCleanupPolicySettings(
        remove_quality_rejections=_cleanup_toggle(p_new + "QUALITY", p_leg + "QUALITY"),
        remove_unmatched_manual_import_rejections=_cleanup_toggle(p_new + "UNMATCHED", p_leg + "UNMATCHED"),
        remove_corrupt_imports=_cleanup_toggle(p_new + "CORRUPT", p_leg + "CORRUPT"),
        remove_failed_downloads=_cleanup_toggle(p_new + "DOWNLOAD_FAILED", p_leg + "DOWNLOAD_FAILED"),
        remove_failed_imports=_cleanup_toggle(p_new + "IMPORT_FAILED", p_leg + "IMPORT_FAILED"),
    )


def default_failed_import_cleanup_settings_bundle() -> FailedImportCleanupSettingsBundle:
    """All toggles off (no env read) — tests and manual ``MediaMopSettings`` construction."""
    off = AppFailedImportCleanupPolicySettings()
    return FailedImportCleanupSettingsBundle(radarr=off, sonarr=off)


def load_failed_import_cleanup_settings_bundle() -> FailedImportCleanupSettingsBundle:
    """Read cleanup toggles from the process environment (default all off)."""
    return FailedImportCleanupSettingsBundle(
        radarr=_load_radarr_cleanup_settings(),
        sonarr=_load_sonarr_cleanup_settings(),
    )
