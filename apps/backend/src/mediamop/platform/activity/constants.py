"""Stable ``event_type`` strings for persisted activity (append-only contract)."""

# Auth / platform
AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGOUT = "auth.logout"
AUTH_BOOTSTRAP_SUCCEEDED = "auth.bootstrap_succeeded"
AUTH_BOOTSTRAP_DENIED = "auth.bootstrap_denied"
AUTH_PASSWORD_CHANGED = "auth.password_changed"
SYSTEM_RECONCILIATION_REPAIR = "system.reconciliation.repair"

# Shared *arr library (Sonarr/Radarr) — operator-triggered connection checks
ARR_LIBRARY_CONNECTION_TEST_SUCCEEDED = "arr_library.connection_test_succeeded"
ARR_LIBRARY_CONNECTION_TEST_FAILED = "arr_library.connection_test_failed"

# Refiner durable families (refiner_jobs)

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
