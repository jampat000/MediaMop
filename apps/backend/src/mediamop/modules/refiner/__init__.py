"""Refiner module — MediaMop’s media refinement surface (movies and TV).

Implementation here still drives Radarr/Sonarr **download-queue** failed-import removal (per policy) via
``refiner_jobs``, in-process runners, and periodic enqueue — but **product-facing HTTP** for that
queue workflow lives under ``mediamop.modules.fetcher.failed_imports_api`` (Fetcher ownership).
Refiner-native disk-level stale-file cleanup (after importing is done) remains a separate future concern.

Radarr and Sonarr stay in separate Python modules wherever behavior can diverge.
"""

from __future__ import annotations

from mediamop.modules.refiner.arr_queue_plumbing import normalize_storage_path
from mediamop.modules.refiner.failed_import_classification import (
    FailedImportOutcome,
    classify_failed_import_message,
    normalize_failed_import_blob,
)
from mediamop.modules.refiner.failed_import_cleanup_decision import (
    FailedImportCleanupEligibilityDecision,
    FailedImportCleanupEligibilityReason,
    decide_failed_import_cleanup_eligibility,
)
from mediamop.modules.refiner.failed_import_cleanup_settings import (
    AppFailedImportCleanupPolicySettings,
    RefinerFailedImportCleanupSettingsBundle,
    default_refiner_failed_import_cleanup_settings_bundle,
    load_refiner_failed_import_cleanup_settings_bundle,
)
from mediamop.modules.refiner.failed_import_cleanup_orchestration import (
    FailedImportCleanupPlanningResult,
    RefinerArrApp,
    parse_refiner_arr_app,
    plan_failed_import_cleanup,
)
from mediamop.modules.refiner.failed_import_cleanup_policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    cleanup_policy_key_for_outcome,
    default_failed_import_cleanup_policy,
    is_failed_import_cleanup_enabled,
)
from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    TitleYearAnchor,
    extract_title_tokens_and_year,
    extract_title_year_anchor,
    file_is_owned_by_queue,
    normalize_titleish,
    row_owns_by_title_year_anchor,
    should_block_for_upstream,
    strip_packaging_tokens,
    title_year_anchors_match,
    tokenize_normalized,
)
from mediamop.modules.refiner.radarr_cleanup_execution import (
    RadarrFailedImportCleanupExecutionOutcome,
    RadarrQueueHttpClient,
    RadarrQueueOperations,
    execute_radarr_failed_import_cleanup_plan,
)
from mediamop.modules.refiner.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupAction,
    RadarrFailedImportCleanupPlan,
    plan_radarr_failed_import_cleanup,
)
from mediamop.modules.refiner.radarr_failed_import_cleanup_drive import (
    RadarrFailedImportCleanupDriveItemResult,
    RadarrQueueFetchOperations,
    RadarrQueueHttpFetchClient,
    drive_radarr_failed_import_cleanup_from_live_queue,
    radarr_queue_item_status_message_blob,
)
from mediamop.modules.refiner.radarr_failed_import_cleanup_vertical import (
    RadarrFailedImportCleanupSettingsSource,
    run_radarr_failed_import_cleanup_vertical,
)
from mediamop.modules.refiner.radarr_queue_adapter import map_radarr_queue_row_to_refiner_view
from mediamop.modules.refiner.sonarr_cleanup_execution import (
    SonarrFailedImportCleanupExecutionOutcome,
    SonarrQueueHttpClient,
    SonarrQueueOperations,
    execute_sonarr_failed_import_cleanup_plan,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupAction,
    SonarrFailedImportCleanupPlan,
    plan_sonarr_failed_import_cleanup,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_drive import (
    SonarrFailedImportCleanupDriveItemResult,
    SonarrQueueFetchOperations,
    SonarrQueueHttpFetchClient,
    drive_sonarr_failed_import_cleanup_from_live_queue,
    sonarr_queue_item_status_message_blob,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_vertical import (
    SonarrFailedImportCleanupSettingsSource,
    run_sonarr_failed_import_cleanup_vertical,
)
from mediamop.modules.refiner.sonarr_queue_adapter import map_sonarr_queue_row_to_refiner_view

__all__ = [
    "FailedImportCleanupEligibilityDecision",
    "FailedImportCleanupEligibilityReason",
    "decide_failed_import_cleanup_eligibility",
    "FailedImportCleanupPlanningResult",
    "AppFailedImportCleanupPolicySettings",
    "RefinerFailedImportCleanupSettingsBundle",
    "default_refiner_failed_import_cleanup_settings_bundle",
    "load_refiner_failed_import_cleanup_settings_bundle",
    "RefinerArrApp",
    "parse_refiner_arr_app",
    "plan_failed_import_cleanup",
    "FailedImportCleanupPolicy",
    "FailedImportCleanupPolicyKey",
    "cleanup_policy_key_for_outcome",
    "default_failed_import_cleanup_policy",
    "is_failed_import_cleanup_enabled",
    "FailedImportOutcome",
    "classify_failed_import_message",
    "normalize_failed_import_blob",
    "FileAnchorCandidate",
    "RadarrFailedImportCleanupAction",
    "RadarrFailedImportCleanupExecutionOutcome",
    "RadarrFailedImportCleanupPlan",
    "RadarrQueueHttpClient",
    "RadarrQueueOperations",
    "execute_radarr_failed_import_cleanup_plan",
    "RadarrFailedImportCleanupDriveItemResult",
    "RadarrQueueFetchOperations",
    "RadarrQueueHttpFetchClient",
    "drive_radarr_failed_import_cleanup_from_live_queue",
    "radarr_queue_item_status_message_blob",
    "RadarrFailedImportCleanupSettingsSource",
    "run_radarr_failed_import_cleanup_vertical",
    "plan_radarr_failed_import_cleanup",
    "map_radarr_queue_row_to_refiner_view",
    "SonarrFailedImportCleanupAction",
    "SonarrFailedImportCleanupExecutionOutcome",
    "SonarrFailedImportCleanupPlan",
    "SonarrQueueHttpClient",
    "SonarrQueueOperations",
    "execute_sonarr_failed_import_cleanup_plan",
    "SonarrFailedImportCleanupDriveItemResult",
    "SonarrQueueFetchOperations",
    "SonarrQueueHttpFetchClient",
    "drive_sonarr_failed_import_cleanup_from_live_queue",
    "sonarr_queue_item_status_message_blob",
    "SonarrFailedImportCleanupSettingsSource",
    "run_sonarr_failed_import_cleanup_vertical",
    "plan_sonarr_failed_import_cleanup",
    "map_sonarr_queue_row_to_refiner_view",
    "normalize_storage_path",
    "RefinerQueueRowView",
    "TitleYearAnchor",
    "extract_title_tokens_and_year",
    "extract_title_year_anchor",
    "file_is_owned_by_queue",
    "normalize_titleish",
    "row_owns_by_title_year_anchor",
    "should_block_for_upstream",
    "strip_packaging_tokens",
    "title_year_anchors_match",
    "tokenize_normalized",
]
