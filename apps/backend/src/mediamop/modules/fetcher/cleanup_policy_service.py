"""Fetcher failed-import cleanup policy — single source of truth in SQLite.

The singleton row ``id = 1`` holds runtime values. If it is missing, it is **seeded once** from the
process environment bundle (``MediaMopSettings.failed_import_cleanup_env`` at load time). After
that, all reads use the database row only — no ongoing env fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.fetcher.cleanup_policy_model import FetcherFailedImportCleanupPolicyRow
from mediamop.modules.arr_failed_import.env_settings import (
    AppFailedImportCleanupPolicySettings,
    FailedImportCleanupSettingsBundle,
)
from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy


@dataclass(frozen=True, slots=True)
class FailedImportDrivePolicySource:
    """Supplies Radarr and Sonarr policies for live download-queue drives."""

    bundle: FailedImportCleanupSettingsBundle

    def radarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        return self.bundle.radarr_policy()

    def sonarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        return self.bundle.sonarr_policy()


def _row_to_bundle(row: FetcherFailedImportCleanupPolicyRow) -> FailedImportCleanupSettingsBundle:
    return FailedImportCleanupSettingsBundle(
        radarr=AppFailedImportCleanupPolicySettings(
            remove_quality_rejections=row.radarr_remove_quality_rejections,
            remove_unmatched_manual_import_rejections=row.radarr_remove_unmatched_manual_import_rejections,
            remove_corrupt_imports=row.radarr_remove_corrupt_imports,
            remove_failed_downloads=row.radarr_remove_failed_downloads,
            remove_failed_imports=row.radarr_remove_failed_imports,
        ),
        sonarr=AppFailedImportCleanupPolicySettings(
            remove_quality_rejections=row.sonarr_remove_quality_rejections,
            remove_unmatched_manual_import_rejections=row.sonarr_remove_unmatched_manual_import_rejections,
            remove_corrupt_imports=row.sonarr_remove_corrupt_imports,
            remove_failed_downloads=row.sonarr_remove_failed_downloads,
            remove_failed_imports=row.sonarr_remove_failed_imports,
        ),
    )


def _new_row_from_env(env_bundle: FailedImportCleanupSettingsBundle) -> FetcherFailedImportCleanupPolicyRow:
    r, s = env_bundle.radarr, env_bundle.sonarr
    return FetcherFailedImportCleanupPolicyRow(
        id=1,
        radarr_remove_quality_rejections=r.remove_quality_rejections,
        radarr_remove_unmatched_manual_import_rejections=r.remove_unmatched_manual_import_rejections,
        radarr_remove_corrupt_imports=r.remove_corrupt_imports,
        radarr_remove_failed_downloads=r.remove_failed_downloads,
        radarr_remove_failed_imports=r.remove_failed_imports,
        sonarr_remove_quality_rejections=s.remove_quality_rejections,
        sonarr_remove_unmatched_manual_import_rejections=s.remove_unmatched_manual_import_rejections,
        sonarr_remove_corrupt_imports=s.remove_corrupt_imports,
        sonarr_remove_failed_downloads=s.remove_failed_downloads,
        sonarr_remove_failed_imports=s.remove_failed_imports,
    )


def load_fetcher_failed_import_cleanup_bundle(
    session: Session,
    env_bundle: FailedImportCleanupSettingsBundle,
) -> tuple[FailedImportCleanupSettingsBundle, FetcherFailedImportCleanupPolicyRow]:
    """Return Fetcher failed-import cleanup policy from the persisted singleton row (``id = 1``).

    **This is the only lazy-seed entry point** for that row: if the row is missing, it is
    inserted once from ``env_bundle`` (environment-derived defaults at call time). After the
    row exists, returned values always come from the database columns—there is no ongoing
    env merge.

    **Callers:** the Fetcher failed-import cleanup policy GET handler, PUT handler (via
    :func:`upsert_fetcher_failed_import_cleanup_policy`, which must call this first), and
    worker/job code that needs the policy **must** load through this function (or through
    ``upsert_*`` after a prior ``load_*`` in the same request/work unit). Do not bypass this
    by reading ``FetcherFailedImportCleanupPolicyRow`` directly and falling back to
    ``env_bundle`` elsewhere; that would reintroduce split-brain behavior.
    """

    row = session.get(FetcherFailedImportCleanupPolicyRow, 1)
    if row is not None:
        return _row_to_bundle(row), row

    # Sole place we seed id=1 from env; keep all runtime reads routed through load_* / upsert_*.
    with session.begin_nested():
        try:
            session.add(_new_row_from_env(env_bundle))
            session.flush()
        except IntegrityError:
            # Another writer created id=1 first (concurrent seed).
            pass

    row = session.get(FetcherFailedImportCleanupPolicyRow, 1)
    if row is None:
        msg = "fetcher failed-import cleanup policy singleton missing after seed"
        raise RuntimeError(msg)
    return _row_to_bundle(row), row


def upsert_fetcher_failed_import_cleanup_policy(
    session: Session,
    *,
    env_bundle: FailedImportCleanupSettingsBundle,
    radarr: AppFailedImportCleanupPolicySettings,
    sonarr: AppFailedImportCleanupPolicySettings,
) -> FetcherFailedImportCleanupPolicyRow:
    """Ensure the singleton row exists (seed from env if needed), then overwrite with operator values."""

    load_fetcher_failed_import_cleanup_bundle(session, env_bundle)
    row = session.get(FetcherFailedImportCleanupPolicyRow, 1)
    if row is None:
        msg = "fetcher failed-import cleanup policy row missing after load"
        raise RuntimeError(msg)

    row.radarr_remove_quality_rejections = radarr.remove_quality_rejections
    row.radarr_remove_unmatched_manual_import_rejections = radarr.remove_unmatched_manual_import_rejections
    row.radarr_remove_corrupt_imports = radarr.remove_corrupt_imports
    row.radarr_remove_failed_downloads = radarr.remove_failed_downloads
    row.radarr_remove_failed_imports = radarr.remove_failed_imports

    row.sonarr_remove_quality_rejections = sonarr.remove_quality_rejections
    row.sonarr_remove_unmatched_manual_import_rejections = sonarr.remove_unmatched_manual_import_rejections
    row.sonarr_remove_corrupt_imports = sonarr.remove_corrupt_imports
    row.sonarr_remove_failed_downloads = sonarr.remove_failed_downloads
    row.sonarr_remove_failed_imports = sonarr.remove_failed_imports

    session.flush()
    return row
