"""Stable ``event_type`` strings for persisted activity (append-only contract)."""

# Auth / platform
AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGOUT = "auth.logout"
AUTH_BOOTSTRAP_SUCCEEDED = "auth.bootstrap_succeeded"
AUTH_BOOTSTRAP_DENIED = "auth.bootstrap_denied"
AUTH_PASSWORD_CHANGED = "auth.password_changed"
AUTH_SESSIONS_REVOKED = "auth.sessions_revoked"
SYSTEM_RECONCILIATION_REPAIR = "system.reconciliation.repair"

# Shared *arr library (Sonarr/Radarr) — operator-triggered connection checks
ARR_LIBRARY_CONNECTION_TEST_SUCCEEDED = "arr_library.connection_test_succeeded"
ARR_LIBRARY_CONNECTION_TEST_FAILED = "arr_library.connection_test_failed"

# Refiner durable families (refiner_jobs)

REFINER_FILE_PROCESSING_PROGRESS = "refiner.file_processing_progress"
REFINER_FILE_REMUX_PASS_COMPLETED = "refiner.file_remux_pass_completed"
REFINER_WORK_TEMP_STALE_SWEEP_COMPLETED = "refiner.work_temp_stale_sweep_completed"
REFINER_FAILURE_CLEANUP_SWEEP_COMPLETED = "refiner.failure_cleanup_sweep_completed"
REFINER_WORKER_FAILURE = "refiner.worker_failure"
# A file MediaMop could not process was handed back unmodified rather than kept (#465). A distinct
# type, so it can never be counted as a completed pass or as space saved.
REFINER_FILE_PASSED_THROUGH = "refiner.file_passed_through"
REFINER_FILE_PASS_THROUGH_FAILED = "refiner.file_pass_through_failed"
# The opt-in reject policy: the manager accepted the report, or MediaMop fell back to handing the
# original back because rejecting could not be done safely.
REFINER_FILE_REJECTED = "refiner.file_rejected"
REFINER_FILE_REJECT_FELL_BACK = "refiner.file_reject_fell_back"
# A report sent to the media manager that handed a file over, so every report is visible.
REFINER_HANDOFF_REPORTED = "refiner.handoff_reported"
# The manager cancelled a hand-off MediaMop had not started (#480).
REFINER_HANDOFF_CANCELLED = "refiner.handoff_cancelled"

# Pruner (pruner_jobs + server instances)
PRUNER_CONNECTION_TEST_SUCCEEDED = "pruner.connection_test_succeeded"
PRUNER_CONNECTION_TEST_FAILED = "pruner.connection_test_failed"
PRUNER_PREVIEW_SUCCEEDED = "pruner.preview_succeeded"
PRUNER_PREVIEW_UNSUPPORTED = "pruner.preview_unsupported"
PRUNER_PREVIEW_FAILED = "pruner.preview_failed"
PRUNER_APPLY_LIBRARY_REMOVAL_COMPLETED = "pruner.apply_library_removal_completed"
PRUNER_APPLY_LIBRARY_REMOVAL_FAILED = "pruner.apply_library_removal_failed"
