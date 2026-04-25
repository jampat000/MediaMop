"""Stable ``event_type`` strings for persisted activity (append-only contract)."""

# Auth / platform
AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGOUT = "auth.logout"
AUTH_BOOTSTRAP_SUCCEEDED = "auth.bootstrap_succeeded"
AUTH_BOOTSTRAP_DENIED = "auth.bootstrap_denied"
AUTH_PASSWORD_CHANGED = "auth.password_changed"

# Shared *arr library (Sonarr/Radarr) — operator-triggered connection checks
ARR_LIBRARY_CONNECTION_TEST_SUCCEEDED = "arr_library.connection_test_succeeded"
ARR_LIBRARY_CONNECTION_TEST_FAILED = "arr_library.connection_test_failed"

# Refiner durable families (refiner_jobs)
REFINER_SUPPLIED_PAYLOAD_EVALUATION_COMPLETED = "refiner.supplied_payload_evaluation_completed"

SUBBER_SUBTITLE_SEARCH_COMPLETED = "subber.subtitle_search_completed"
SUBBER_LIBRARY_SCAN_ENQUEUED = "subber.library_scan_enqueued"
SUBBER_LIBRARY_SYNC_COMPLETED = "subber.library_sync_completed"
SUBBER_WEBHOOK_IMPORT_ENQUEUED = "subber.webhook_import_enqueued"
SUBBER_SUBTITLE_UPGRADE_COMPLETED = "subber.subtitle_upgrade_completed"
REFINER_CANDIDATE_GATE_COMPLETED = "refiner.candidate_gate_completed"
REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_COMPLETED = "refiner.watched_folder_remux_scan_dispatch_completed"
REFINER_FILE_PROCESSING_PROGRESS = "refiner.file_processing_progress"
REFINER_FILE_REMUX_PASS_COMPLETED = "refiner.file_remux_pass_completed"
REFINER_WORK_TEMP_STALE_SWEEP_COMPLETED = "refiner.work_temp_stale_sweep_completed"
REFINER_FAILURE_CLEANUP_SWEEP_COMPLETED = "refiner.failure_cleanup_sweep_completed"

# Pruner (pruner_jobs + server instances)
PRUNER_CONNECTION_TEST_SUCCEEDED = "pruner.connection_test_succeeded"
PRUNER_CONNECTION_TEST_FAILED = "pruner.connection_test_failed"
PRUNER_PREVIEW_SUCCEEDED = "pruner.preview_succeeded"
PRUNER_PREVIEW_UNSUPPORTED = "pruner.preview_unsupported"
PRUNER_PREVIEW_FAILED = "pruner.preview_failed"
PRUNER_APPLY_LIBRARY_REMOVAL_COMPLETED = "pruner.apply_library_removal_completed"
PRUNER_APPLY_LIBRARY_REMOVAL_FAILED = "pruner.apply_library_removal_failed"
