using Weir.Core.Configuration;
using Weir.Core.Rules;

namespace Weir.Core.Processing;

/// <summary>The read-only Processing runtime snapshot (<c>ProcessingRuntimeSettingsOut</c>).</summary>
public sealed record ProcessingRuntimeSettings
{
    public required int InProcessProcessingWorkerCount { get; init; }
    public required bool InProcessWorkersDisabled { get; init; }
    public required bool InProcessWorkersEnabled { get; init; }
    public required string WorkerModeSummary { get; init; }
    public required string SqliteThroughputNote { get; init; }
    public required string ConfigurationNote { get; init; }
    public required string VisibilityNote { get; init; }
    public required IReadOnlyList<string> ProcessingMediaExtensions { get; init; }
    public required bool ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs { get; init; }
    public required int ProcessingProbeSizeMb { get; init; }
    public required int ProcessingAnalyzeDurationSeconds { get; init; }
    public required int ProcessingWatchedFolderMinFileAgeSeconds { get; init; }
    public required int ProcessingMovieOutputCleanupMinAgeSeconds { get; init; }
    public required string MovieOutputCleanupConfigurationNote { get; init; }
    public required int ProcessingTvOutputCleanupMinAgeSeconds { get; init; }
    public required string TvOutputCleanupConfigurationNote { get; init; }
    public required string WatchedFolderScanPeriodicConfigurationNote { get; init; }
    public required bool ProcessingWorkTempStaleSweepMovieScheduleEnabled { get; init; }
    public required int ProcessingWorkTempStaleSweepMovieScheduleIntervalSeconds { get; init; }
    public required bool ProcessingWorkTempStaleSweepTvScheduleEnabled { get; init; }
    public required int ProcessingWorkTempStaleSweepTvScheduleIntervalSeconds { get; init; }
    public required int ProcessingWorkTempStaleSweepMinStaleAgeSeconds { get; init; }
    public required bool ProcessingMovieFailureCleanupScheduleEnabled { get; init; }
    public required int ProcessingMovieFailureCleanupScheduleIntervalSeconds { get; init; }
    public required bool ProcessingTvFailureCleanupScheduleEnabled { get; init; }
    public required int ProcessingTvFailureCleanupScheduleIntervalSeconds { get; init; }
    public required int ProcessingMovieFailureCleanupGracePeriodSeconds { get; init; }
    public required int ProcessingTvFailureCleanupGracePeriodSeconds { get; init; }
    public required string FailureCleanupConfigurationNote { get; init; }
    public required string WorkTempStaleSweepPeriodicConfigurationNote { get; init; }
}

/// <summary>Port of <c>processing_runtime_visibility.py</c>: maps loaded settings to a DTO, no DB reads.</summary>
public static class RuntimeVisibility
{
    private const string SqliteThroughputNote =
        "Weir stores durable jobs on SQLite. Several workers can each claim a different jobs row, " +
        "but the database still serializes writes, so raising the count may not speed things up proportionally and can add contention.";

    private const string ConfigurationNote =
        "Concurrency is controlled by Processing → Libraries. Set Files at once to 1 for one active " +
        "file worker or up to 8 for parallel file work. No restart is needed after changing that setting.";

    private const string VisibilityNote =
        "Values reflect this API process startup configuration. They do not prove a worker is mid-job or that " +
        "another process is not also using the same database file.";

    private const string WatchedFolderScanPeriodicNote =
        "Periodic scanning for processing.watched_folder.remux_scan_dispatch.v1 is controlled per library (its own " +
        "enabled switch and scan interval, saved in the database and applied without a restart) and per scope on " +
        "the Processing → Libraries screen (Movies/TV periodic-scan switch). It can also be turned off " +
        "altogether, for every scope, with WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED in " +
        "the server's environment (default on; #533 — a manual scan still works with this off). Whether a periodic scan " +
        "that does run may also queue file work is the separate " +
        "WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS (default on). Restart the API " +
        "after changing either environment variable — both are read at process start only. " +
        "ffprobe preflight depth: WEIR_PROCESSING_PROBE_SIZE_MB and WEIR_PROCESSING_ANALYZE_DURATION_SECONDS in " +
        "the server's environment (read at startup; restart required).";

    private const string MovieOutputCleanupNote =
        "Movies output-folder cleanup (Pass 3a) after a successful Movies remux uses " +
        "WEIR_PROCESSING_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS in the server's environment (default 48 hours, clamped 1h..30d). " +
        "Restart the API after changing this value.";

    private const string TvOutputCleanupNote =
        "TV output-folder cleanup (Pass 3b) after a successful TV remux uses " +
        "WEIR_PROCESSING_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS in the server's environment (default 48 hours, clamped 1h..30d). " +
        "Restart the API after changing this value.";

    private const string FailureCleanupNote =
        "The Pass 4 failed-remux cleanup sweep uses separate Movies and TV timers and grace periods in " +
        "the server's environment. Only terminal failed remux rows are eligible, and failure age uses jobs.updated_at. Restart required.";

    private const string WorkTempStaleSweepPeriodicNote =
        "Optional periodic enqueue for processing.work_temp_stale_sweep.v1 is per scope (Movies vs TV) in " +
        "the server's environment. Each tick enqueues one durable job per enabled scope. Restart the API after changing any of these.";

    public static ProcessingRuntimeSettings From(WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        var n = options.ProcessingWorkerCount;
        var disabled = n == 0;
        var summary = disabled
            ? "In-process workers are off (0). jobs rows stay queued until you set WEIR_PROCESSING_WORKER_COUNT to at least 1 and restart this API."
            : n == 1
                ? "Weir has one available jobs worker slot. Processing → Libraries controls the active Files at once value."
                : $"{n} in-process worker slots are available. Processing → Libraries decides how many of those jobs slots may process files at once.";

        return new ProcessingRuntimeSettings
        {
            InProcessProcessingWorkerCount = n,
            InProcessWorkersDisabled = disabled,
            InProcessWorkersEnabled = !disabled,
            WorkerModeSummary = summary,
            SqliteThroughputNote = SqliteThroughputNote,
            ConfigurationNote = ConfigurationNote,
            VisibilityNote = VisibilityNote,
            ProcessingMediaExtensions = RemuxRules.MediaExtensionsSorted(),
            ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs = options.ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs,
            ProcessingProbeSizeMb = options.ProcessingProbeSizeMb,
            ProcessingAnalyzeDurationSeconds = options.ProcessingAnalyzeDurationSeconds,
            ProcessingWatchedFolderMinFileAgeSeconds = options.ProcessingWatchedFolderMinFileAgeSeconds,
            ProcessingMovieOutputCleanupMinAgeSeconds = options.ProcessingMovieOutputCleanupMinAgeSeconds,
            MovieOutputCleanupConfigurationNote = MovieOutputCleanupNote,
            ProcessingTvOutputCleanupMinAgeSeconds = options.ProcessingTvOutputCleanupMinAgeSeconds,
            TvOutputCleanupConfigurationNote = TvOutputCleanupNote,
            WatchedFolderScanPeriodicConfigurationNote = WatchedFolderScanPeriodicNote,
            ProcessingWorkTempStaleSweepMovieScheduleEnabled = options.ProcessingWorkTempStaleSweepMovieScheduleEnabled,
            ProcessingWorkTempStaleSweepMovieScheduleIntervalSeconds = options.ProcessingWorkTempStaleSweepMovieScheduleIntervalSeconds,
            ProcessingWorkTempStaleSweepTvScheduleEnabled = options.ProcessingWorkTempStaleSweepTvScheduleEnabled,
            ProcessingWorkTempStaleSweepTvScheduleIntervalSeconds = options.ProcessingWorkTempStaleSweepTvScheduleIntervalSeconds,
            ProcessingWorkTempStaleSweepMinStaleAgeSeconds = options.ProcessingWorkTempStaleSweepMinStaleAgeSeconds,
            ProcessingMovieFailureCleanupScheduleEnabled = options.ProcessingMovieFailureCleanupScheduleEnabled,
            ProcessingMovieFailureCleanupScheduleIntervalSeconds = options.ProcessingMovieFailureCleanupScheduleIntervalSeconds,
            ProcessingTvFailureCleanupScheduleEnabled = options.ProcessingTvFailureCleanupScheduleEnabled,
            ProcessingTvFailureCleanupScheduleIntervalSeconds = options.ProcessingTvFailureCleanupScheduleIntervalSeconds,
            ProcessingMovieFailureCleanupGracePeriodSeconds = options.ProcessingMovieFailureCleanupGracePeriodSeconds,
            ProcessingTvFailureCleanupGracePeriodSeconds = options.ProcessingTvFailureCleanupGracePeriodSeconds,
            FailureCleanupConfigurationNote = FailureCleanupNote,
            WorkTempStaleSweepPeriodicConfigurationNote = WorkTempStaleSweepPeriodicNote,
        };
    }
}
