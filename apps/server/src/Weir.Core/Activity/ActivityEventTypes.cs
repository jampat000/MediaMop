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

    // Processing durable families (jobs)
    public const string ProcessingFileProcessingProgress = "processing.file_processing_progress";
    public const string ProcessingFileRemuxPassCompleted = "processing.file_remux_pass_completed";
    public const string ProcessingWorkTempStaleSweepCompleted = "processing.work_temp_stale_sweep_completed";
    public const string ProcessingFailureCleanupSweepCompleted = "processing.failure_cleanup_sweep_completed";
    public const string ProcessingWorkerFailure = "processing.worker_failure";

    /// <summary>A file Weir could not process was handed back unmodified rather than kept (#465).</summary>
    public const string ProcessingFilePassedThrough = "processing.file_passed_through";
    public const string ProcessingFilePassThroughFailed = "processing.file_pass_through_failed";

    /// <summary>The opt-in reject policy: the manager accepted the report.</summary>
    public const string ProcessingFileRejected = "processing.file_rejected";

    /// <summary>The opt-in reject policy: Weir handed the original back because rejecting could not be done safely.</summary>
    public const string ProcessingFileRejectFellBack = "processing.file_reject_fell_back";

    /// <summary>A report sent to the media manager that handed a file over.</summary>
    public const string ProcessingHandoffReported = "processing.handoff_reported";

    /// <summary>The manager cancelled a hand-off Weir had not started (#480).</summary>
    public const string ProcessingHandoffCancelled = "processing.handoff_cancelled";

    /// <summary>An operator queued a hand-picked track choice for a held file (#501).</summary>
    public const string ProcessingFileManualPlanQueued = "processing.file_manual_plan_queued";
}

/// <summary>
/// Library mode's (#505) event types: cleaning files already in a library, in place. Deliberately kept out of
/// <see cref="ActivityEventTypes"/>, whose <c>Event_types_match_the_python_constants_exactly</c> test requires every member
/// to have a matching Python constant — library mode is .NET only (same as the #506 safe swap it uses), so there is no
/// Python family to match.
/// </summary>
public static class LibraryActivityEventTypes
{
    public const string ScanCompleted = "library.scan_completed";
    public const string FileCleaned = "library.file_cleaned";
    public const string FileSkipped = "library.file_skipped";
    public const string FileFailed = "library.file_failed";
}
