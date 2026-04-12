"""Stable ``event_type`` strings for persisted activity (append-only contract)."""

# Auth / platform
AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGOUT = "auth.logout"
AUTH_BOOTSTRAP_SUCCEEDED = "auth.bootstrap_succeeded"
AUTH_BOOTSTRAP_DENIED = "auth.bootstrap_denied"

# Fetcher bridge (throttled in service — not per-request spam)
FETCHER_PROBE_SUCCEEDED = "fetcher.probe_succeeded"
FETCHER_PROBE_FAILED = "fetcher.probe_failed"

# Fetcher failed-import download-queue passes (one summary or failure row per run)
FETCHER_FAILED_IMPORT_RUN_STARTED = "fetcher.failed_import_run_started"
FETCHER_FAILED_IMPORT_PASS_QUEUED = "fetcher.failed_import_pass_queued"
FETCHER_FAILED_IMPORT_RUN_SUMMARY = "fetcher.failed_import_run_summary"
FETCHER_FAILED_IMPORT_RUN_FAILED = "fetcher.failed_import_run_failed"
FETCHER_FAILED_IMPORT_RECOVERED = "fetcher.failed_import_recovered"
FETCHER_JOB_RECOVERED_HANDLER_OK_FINALIZE = "fetcher.job_recovered_handler_ok_finalize"

# Fetcher Arr search (missing / upgrade) — summaries mirror audited Fetcher wording where practical.
FETCHER_ARR_SEARCH_MISSING_DISPATCHED = "fetcher.arr_search_missing_dispatched"
FETCHER_ARR_SEARCH_MISSING_ZERO_MANUAL = "fetcher.arr_search_missing_zero_manual"
FETCHER_ARR_SEARCH_UPGRADE_DISPATCHED = "fetcher.arr_search_upgrade_dispatched"
FETCHER_ARR_SEARCH_UPGRADE_ZERO_MANUAL = "fetcher.arr_search_upgrade_zero_manual"

# Refiner durable families (refiner_jobs)
REFINER_SUPPLIED_PAYLOAD_EVALUATION_COMPLETED = "refiner.supplied_payload_evaluation_completed"
REFINER_CANDIDATE_GATE_COMPLETED = "refiner.candidate_gate_completed"
