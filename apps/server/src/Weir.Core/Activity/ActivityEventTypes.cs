namespace Weir.Core.Activity;

/// <summary>
/// Stable <c>event_type</c> strings for persisted activity, an append-only contract (port of
/// <c>weir.platform.activity.constants</c>). Every value must match the Python module exactly.
/// </summary>
public static class ActivityEventTypes
{
    // Auth / platform
    public const string AuthLoginSucceeded = "auth.login_succeeded";
    public const string AuthLoginFailed = "auth.login_failed";
    public const string AuthLogout = "auth.logout";
    public const string AuthBootstrapSucceeded = "auth.bootstrap_succeeded";
    public const string AuthBootstrapDenied = "auth.bootstrap_denied";
    public const string AuthPasswordChanged = "auth.password_changed";
    public const string AuthUsernameChanged = "auth.username_changed";
    public const string AuthSessionsRevoked = "auth.sessions_revoked";
    public const string SystemReconciliationRepair = "system.reconciliation.repair";

    // Shared *arr library (Sonarr/Radarr): operator-triggered connection checks
    public const string ArrLibraryConnectionTestSucceeded = "arr_library.connection_test_succeeded";
    public const string ArrLibraryConnectionTestFailed = "arr_library.connection_test_failed";

    // Refiner durable families (refiner_jobs)
    public const string RefinerFileProcessingProgress = "refiner.file_processing_progress";
    public const string RefinerFileRemuxPassCompleted = "refiner.file_remux_pass_completed";
    public const string RefinerWorkTempStaleSweepCompleted = "refiner.work_temp_stale_sweep_completed";
    public const string RefinerFailureCleanupSweepCompleted = "refiner.failure_cleanup_sweep_completed";
    public const string RefinerWorkerFailure = "refiner.worker_failure";

    /// <summary>A file Weir could not process was handed back unmodified rather than kept (#465).</summary>
    public const string RefinerFilePassedThrough = "refiner.file_passed_through";
    public const string RefinerFilePassThroughFailed = "refiner.file_pass_through_failed";

    /// <summary>The opt-in reject policy: the manager accepted the report.</summary>
    public const string RefinerFileRejected = "refiner.file_rejected";

    /// <summary>The opt-in reject policy: Weir handed the original back because rejecting could not be done safely.</summary>
    public const string RefinerFileRejectFellBack = "refiner.file_reject_fell_back";

    /// <summary>A report sent to the media manager that handed a file over.</summary>
    public const string RefinerHandoffReported = "refiner.handoff_reported";

    /// <summary>The manager cancelled a hand-off Weir had not started (#480).</summary>
    public const string RefinerHandoffCancelled = "refiner.handoff_cancelled";

    /// <summary>An operator queued a hand-picked track choice for a held file (#501).</summary>
    public const string RefinerFileManualPlanQueued = "refiner.file_manual_plan_queued";
}
