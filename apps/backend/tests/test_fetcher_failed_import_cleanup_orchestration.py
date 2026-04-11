"""Failed import cleanup planning orchestration (dispatch only)."""

from __future__ import annotations

import pytest

from mediamop.modules.fetcher.failed_import_cleanup_orchestration import (
    FailedImportArrApp,
    FailedImportCleanupPlanningResult,
    parse_failed_import_arr_app,
    plan_failed_import_cleanup,
)
from mediamop.modules.arr_failed_import.policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    default_failed_import_cleanup_policy,
)
from mediamop.modules.fetcher.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupPlan,
    plan_radarr_failed_import_cleanup,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupPlan,
    plan_sonarr_failed_import_cleanup,
)


def _policy_only(key: FailedImportCleanupPolicyKey, on: bool) -> FailedImportCleanupPolicy:
    return FailedImportCleanupPolicy(
        remove_quality_rejections=(key is FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS and on),
        remove_unmatched_manual_import_rejections=(
            key is FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS and on
        ),
        remove_corrupt_imports=(key is FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS and on),
        remove_failed_downloads=(key is FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS and on),
        remove_failed_imports=(key is FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS and on),
    )


def test_orchestration_radarr_dispatches_to_radarr_planner() -> None:
    policy = _policy_only(FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS, on=True)
    blob = "Import failed"
    via = plan_failed_import_cleanup(
        FailedImportArrApp.RADARR,
        status_message_blob=blob,
        policy=policy,
        queue_item_id=55,
    )
    direct = plan_radarr_failed_import_cleanup(
        status_message_blob=blob,
        policy=policy,
        radarr_queue_item_id=55,
    )
    assert isinstance(via, RadarrFailedImportCleanupPlan)
    assert via == direct


def test_orchestration_sonarr_dispatches_to_sonarr_planner() -> None:
    policy = _policy_only(FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS, on=True)
    blob = "file is corrupt"
    via = plan_failed_import_cleanup(
        FailedImportArrApp.SONARR,
        status_message_blob=blob,
        policy=policy,
        queue_item_id=66,
    )
    direct = plan_sonarr_failed_import_cleanup(
        status_message_blob=blob,
        policy=policy,
        sonarr_queue_item_id=66,
    )
    assert isinstance(via, SonarrFailedImportCleanupPlan)
    assert via == direct


def test_orchestration_preserves_app_specific_plan_identity_union() -> None:
    policy = default_failed_import_cleanup_policy()
    r = plan_failed_import_cleanup(FailedImportArrApp.RADARR, status_message_blob="x", policy=policy)
    s = plan_failed_import_cleanup(FailedImportArrApp.SONARR, status_message_blob="x", policy=policy)
    assert type(r) is not type(s)
    assert isinstance(r, RadarrFailedImportCleanupPlan)
    assert isinstance(s, SonarrFailedImportCleanupPlan)
    _: FailedImportCleanupPlanningResult = r
    _: FailedImportCleanupPlanningResult = s


def test_parse_failed_import_arr_app_accepts_common_casing() -> None:
    assert parse_failed_import_arr_app("Radarr") is FailedImportArrApp.RADARR
    assert parse_failed_import_arr_app("  SONARR ") is FailedImportArrApp.SONARR


def test_parse_failed_import_arr_app_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown failed-import arr app"):
        parse_failed_import_arr_app("prowlarr")
