using Weir.Core.Configuration;
using Weir.Core.Rules;

namespace Weir.Core.Refiner;

/// <summary>The read-only Refiner runtime snapshot (<c>RefinerRuntimeSettingsOut</c>).</summary>
public sealed record RefinerRuntimeSettings
{
    public required int InProcessRefinerWorkerCount { get; init; }
    public required bool InProcessWorkersDisabled { get; init; }
    public required bool InProcessWorkersEnabled { get; init; }
    public required string WorkerModeSummary { get; init; }
    public required string SqliteThroughputNote { get; init; }
    public required string ConfigurationNote { get; init; }
    public required string VisibilityNote { get; init; }
    public required IReadOnlyList<string> RefinerMediaExtensions { get; init; }
    public required bool RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs { get; init; }
    public required int RefinerProbeSizeMb { get; init; }
    public required int RefinerAnalyzeDurationSeconds { get; init; }
    public required int RefinerWatchedFolderMinFileAgeSeconds { get; init; }
    public required int RefinerMovieOutputCleanupMinAgeSeconds { get; init; }
    public required string MovieOutputCleanupConfigurationNote { get; init; }
    public required int RefinerTvOutputCleanupMinAgeSeconds { get; init; }
    public required string TvOutputCleanupConfigurationNote { get; init; }
    public required string WatchedFolderScanPeriodicConfigurationNote { get; init; }
    public required bool RefinerWorkTempStaleSweepMovieScheduleEnabled { get; init; }
    public required int RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds { get; init; }
    public required bool RefinerWorkTempStaleSweepTvScheduleEnabled { get; init; }
    public required int RefinerWorkTempStaleSweepTvScheduleIntervalSeconds { get; init; }
    public required int RefinerWorkTempStaleSweepMinStaleAgeSeconds { get; init; }
    public required bool RefinerMovieFailureCleanupScheduleEnabled { get; init; }
    public required int RefinerMovieFailureCleanupScheduleIntervalSeconds { get; init; }
    public required bool RefinerTvFailureCleanupScheduleEnabled { get; init; }
    public required int RefinerTvFailureCleanupScheduleIntervalSeconds { get; init; }
    public required int RefinerMovieFailureCleanupGracePeriodSeconds { get; init; }
    public required int RefinerTvFailureCleanupGracePeriodSeconds { get; init; }
    public required string FailureCleanupConfigurationNote { get; init; }
    public required string WorkTempStaleSweepPeriodicConfigurationNote { get; init; }
}

/// <summary>Port of <c>refiner_runtime_visibility.py</c>: maps loaded settings to a DTO, no DB reads.</summary>
public static class RuntimeVisibility
{
    private const string SqliteThroughputNote =
        "Weir stores durable jobs on SQLite. Several workers can each claim a different refiner_jobs row, " +
        "but the database still serializes writes, so raising the count may not speed things up proportionally and can add contention.";

    private const string ConfigurationNote =
        "Concurrency is controlled by Processing → Libraries. Set Files at once to 1 for one active " +
        "file worker or up to 8 for parallel file work. No restart is needed after changing that setting.";

    private const string VisibilityNote =
        "Values reflect this API process startup configuration. They do not prove a worker is mid-job or that " +
        "another process is not also using the same database file.";

    private const string WatchedFolderScanPeriodicNote =
        "Periodic scanning for refiner.watched_folder.remux_scan_dispatch.v1 is controlled per library (its own " +
        "enabled switch and scan interval, saved in the database and applied without a restart) and per scope on " +
        "the Processing → Libraries screen (Movies/TV periodic-scan switch). It can also be turned off " +
        "altogether, for every scope, with WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED in " +
        "the server's environment (default on; #533 — a manual scan still works with this off). Whether a periodic scan " +
        "that does run may also queue file work is the separate " +
        "WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS (default on). Restart the API " +
        "after changing either environment variable — both are read at process start only. " +
        "ffprobe preflight depth: WEIR_REFINER_PROBE_SIZE_MB and WEIR_REFINER_ANALYZE_DURATION_SECONDS in " +
        "the server's environment (read at startup; restart required).";

    private const string MovieOutputCleanupNote =
        "Movies output-folder cleanup (Pass 3a) after a successful Movies remux uses " +
        "WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS in the server's environment (default 48 hours, clamped 1h..30d). " +
        "Restart the API after changing this value.";

    private const string TvOutputCleanupNote =
        "TV output-folder cleanup (Pass 3b) after a successful TV remux uses " +
        "WEIR_REFINER_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS in the server's environment (default 48 hours, clamped 1h..30d). " +
        "Restart the API after changing this value.";

    private const string FailureCleanupNote =
        "The Pass 4 failed-remux cleanup sweep uses separate Movies and TV timers and grace periods in " +
        "the server's environment. Only terminal failed remux rows are eligible, and failure age uses refiner_jobs.updated_at. Restart required.";

    private const string WorkTempStaleSweepPeriodicNote =
        "Optional periodic enqueue for refiner.work_temp_stale_sweep.v1 is per scope (Movies vs TV) in " +
        "the server's environment. Each tick enqueues one durable job per enabled scope. Restart the API after changing any of these.";

    public static RefinerRuntimeSettings From(WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        var n = options.RefinerWorkerCount;
        var disabled = n == 0;
        var summary = disabled
            ? "In-process workers are off (0). refiner_jobs rows stay queued until you set WEIR_REFINER_WORKER_COUNT to at least 1 and restart this API."
            : n == 1
                ? "Weir has one available refiner_jobs worker slot. Processing → Libraries controls the active Files at once value."
                : $"{n} in-process worker slots are available. Processing → Libraries decides how many of those refiner_jobs slots may process files at once.";

        return new RefinerRuntimeSettings
        {
            InProcessRefinerWorkerCount = n,
            InProcessWorkersDisabled = disabled,
            InProcessWorkersEnabled = !disabled,
            WorkerModeSummary = summary,
            SqliteThroughputNote = SqliteThroughputNote,
            ConfigurationNote = ConfigurationNote,
            VisibilityNote = VisibilityNote,
            RefinerMediaExtensions = RemuxRules.MediaExtensionsSorted(),
            RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs = options.RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs,
            RefinerProbeSizeMb = options.RefinerProbeSizeMb,
            RefinerAnalyzeDurationSeconds = options.RefinerAnalyzeDurationSeconds,
            RefinerWatchedFolderMinFileAgeSeconds = options.RefinerWatchedFolderMinFileAgeSeconds,
            RefinerMovieOutputCleanupMinAgeSeconds = options.RefinerMovieOutputCleanupMinAgeSeconds,
            MovieOutputCleanupConfigurationNote = MovieOutputCleanupNote,
            RefinerTvOutputCleanupMinAgeSeconds = options.RefinerTvOutputCleanupMinAgeSeconds,
            TvOutputCleanupConfigurationNote = TvOutputCleanupNote,
            WatchedFolderScanPeriodicConfigurationNote = WatchedFolderScanPeriodicNote,
            RefinerWorkTempStaleSweepMovieScheduleEnabled = options.RefinerWorkTempStaleSweepMovieScheduleEnabled,
            RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds = options.RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds,
            RefinerWorkTempStaleSweepTvScheduleEnabled = options.RefinerWorkTempStaleSweepTvScheduleEnabled,
            RefinerWorkTempStaleSweepTvScheduleIntervalSeconds = options.RefinerWorkTempStaleSweepTvScheduleIntervalSeconds,
            RefinerWorkTempStaleSweepMinStaleAgeSeconds = options.RefinerWorkTempStaleSweepMinStaleAgeSeconds,
            RefinerMovieFailureCleanupScheduleEnabled = options.RefinerMovieFailureCleanupScheduleEnabled,
            RefinerMovieFailureCleanupScheduleIntervalSeconds = options.RefinerMovieFailureCleanupScheduleIntervalSeconds,
            RefinerTvFailureCleanupScheduleEnabled = options.RefinerTvFailureCleanupScheduleEnabled,
            RefinerTvFailureCleanupScheduleIntervalSeconds = options.RefinerTvFailureCleanupScheduleIntervalSeconds,
            RefinerMovieFailureCleanupGracePeriodSeconds = options.RefinerMovieFailureCleanupGracePeriodSeconds,
            RefinerTvFailureCleanupGracePeriodSeconds = options.RefinerTvFailureCleanupGracePeriodSeconds,
            FailureCleanupConfigurationNote = FailureCleanupNote,
            WorkTempStaleSweepPeriodicConfigurationNote = WorkTempStaleSweepPeriodicNote,
        };
    }
}
