"""Failed-import cleanup toggles loaded from the process environment.

Radarr and Sonarr each have their own toggle set so defaults and future persistence
can diverge without a shared blob.

Env variable names retain the historical ``MEDIAMOP_REFINER_*`` prefix (deployment
compatibility). The module lives under ``arr_failed_import`` because these toggles are
*arr download-queue policy*, not Refiner disk refinement.

Env pattern (each defaults off when unset):

- ``MEDIAMOP_REFINER_RADARR_CLEANUP_QUALITY``
- ``MEDIAMOP_REFINER_RADARR_CLEANUP_UNMATCHED``
- ``MEDIAMOP_REFINER_RADARR_CLEANUP_CORRUPT``
- ``MEDIAMOP_REFINER_RADARR_CLEANUP_DOWNLOAD_FAILED``
- ``MEDIAMOP_REFINER_RADARR_CLEANUP_IMPORT_FAILED``

- ``MEDIAMOP_REFINER_SONARR_CLEANUP_QUALITY`` (and same suffixes)

Truthy: ``1``, ``true``, ``yes``, ``on`` (case-insensitive). Falsy: ``0``, ``false``,
``no``, ``off``, or empty/unset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy

_RADARR_ENV_PREFIX = "MEDIAMOP_REFINER_RADARR_CLEANUP_"
_SONARR_ENV_PREFIX = "MEDIAMOP_REFINER_SONARR_CLEANUP_"


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


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


# Historical type name (MediaMopSettings field and older call sites).
RefinerFailedImportCleanupSettingsBundle = FailedImportCleanupSettingsBundle


def _load_app_cleanup_settings(prefix: str) -> AppFailedImportCleanupPolicySettings:
    return AppFailedImportCleanupPolicySettings(
        remove_quality_rejections=_env_bool(prefix + "QUALITY"),
        remove_unmatched_manual_import_rejections=_env_bool(prefix + "UNMATCHED"),
        remove_corrupt_imports=_env_bool(prefix + "CORRUPT"),
        remove_failed_downloads=_env_bool(prefix + "DOWNLOAD_FAILED"),
        remove_failed_imports=_env_bool(prefix + "IMPORT_FAILED"),
    )


def default_failed_import_cleanup_settings_bundle() -> FailedImportCleanupSettingsBundle:
    """All toggles off (no env read) — tests and manual ``MediaMopSettings`` construction."""
    off = AppFailedImportCleanupPolicySettings()
    return FailedImportCleanupSettingsBundle(radarr=off, sonarr=off)


def load_failed_import_cleanup_settings_bundle() -> FailedImportCleanupSettingsBundle:
    """Read cleanup toggles from the process environment (default all off)."""
    return FailedImportCleanupSettingsBundle(
        radarr=_load_app_cleanup_settings(_RADARR_ENV_PREFIX),
        sonarr=_load_app_cleanup_settings(_SONARR_ENV_PREFIX),
    )


def default_refiner_failed_import_cleanup_settings_bundle() -> FailedImportCleanupSettingsBundle:
    """Alias of :func:`default_failed_import_cleanup_settings_bundle`."""

    return default_failed_import_cleanup_settings_bundle()


def load_refiner_failed_import_cleanup_settings_bundle() -> FailedImportCleanupSettingsBundle:
    """Alias of :func:`load_failed_import_cleanup_settings_bundle`."""

    return load_failed_import_cleanup_settings_bundle()
