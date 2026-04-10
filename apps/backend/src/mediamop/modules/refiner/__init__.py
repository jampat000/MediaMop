"""Refiner module — domain and future product surface.

Pass 1–2: ownership/blocking and anchors. Pass 3: *arr queue adapters. Pass 4–6: failed
import classification, policy, eligibility. Pass 7/7.5: Radarr and Sonarr cleanup
planning seams (separate modules). Pass 8: orchestration dispatch. Pass 9: env-backed Refiner cleanup policy settings on
``MediaMopSettings`` (Radarr vs Sonarr separated). Pass 10/10.5: Radarr and Sonarr
cleanup execution seams (separate modules; optional stdlib HTTP clients). Pass 11/11.5:
Radarr and Sonarr wired verticals (settings → plan → execute), separate modules.
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
