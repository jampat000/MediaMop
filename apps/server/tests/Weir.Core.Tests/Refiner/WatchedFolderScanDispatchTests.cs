using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;

namespace Weir.Core.Tests.Refiner;

/// <summary>Pure-logic port of the assertions in
/// <c>test_refiner_watched_folder_remux_scan_dispatch_evaluate.py</c> and the schedule-gate half of
/// <c>test_refiner_watched_folder_remux_scan_dispatch_periodic_enqueue.py</c>.</summary>
public sealed class WatchedFolderScanDispatchTests
{
    private static RefinerLibraryRecord Library(
        bool enabled = true,
        string mediaType = RefinerMediaScopes.Movie,
        bool scheduleEnabled = true,
        long minFileAgeSeconds = 60,
        long holdMinutes = 0) =>
        new()
        {
            Id = 1,
            Name = mediaType == RefinerMediaScopes.Tv ? "TV" : "Movies",
            MediaType = mediaType,
            Enabled = enabled,
            ScheduleEnabled = scheduleEnabled,
            MinFileAgeSeconds = minFileAgeSeconds,
            HoldMinutes = holdMinutes,
        };

    // --- #533: the gate the scheduler actually consults -----------------------------------------------

    [Fact]
    public void Scope_periodic_scan_enabled_reads_the_per_scope_database_toggle()
    {
        Assert.True(ScanDispatchScheduleGate.ScopePeriodicScanEnabled(movieScheduleEnabled: true, tvScheduleEnabled: false, RefinerMediaScopes.Movie));
        Assert.False(ScanDispatchScheduleGate.ScopePeriodicScanEnabled(movieScheduleEnabled: true, tvScheduleEnabled: false, RefinerMediaScopes.Tv));

        Assert.False(ScanDispatchScheduleGate.ScopePeriodicScanEnabled(movieScheduleEnabled: false, tvScheduleEnabled: false, RefinerMediaScopes.Movie));
        Assert.False(ScanDispatchScheduleGate.ScopePeriodicScanEnabled(movieScheduleEnabled: false, tvScheduleEnabled: false, RefinerMediaScopes.Tv));
    }

    [Fact]
    public void Library_periodic_scan_enabled_is_just_the_library_switch()
    {
        Assert.True(ScanDispatchScheduleGate.LibraryPeriodicScanEnabled(libraryEnabled: true));
        Assert.False(ScanDispatchScheduleGate.LibraryPeriodicScanEnabled(libraryEnabled: false));
    }

    // --- prerequisites ----------------------------------------------------------------------------------

    [Fact]
    public void Prerequisites_require_a_saved_watched_folder()
    {
        Assert.Equal(ScanDispatchPrerequisiteError.NoSavedWatchedFolder, ScanDispatchPrerequisites.Validate(null, "out", enqueueRemuxJobs: false));
        Assert.Equal(ScanDispatchPrerequisiteError.NoSavedWatchedFolder, ScanDispatchPrerequisites.Validate("  ", "out", enqueueRemuxJobs: true));
    }

    [Fact]
    public void Prerequisites_require_an_output_folder_only_when_live_remux_is_on()
    {
        Assert.Null(ScanDispatchPrerequisites.Validate("watched", null, enqueueRemuxJobs: false));
        Assert.Equal(ScanDispatchPrerequisiteError.MissingOutputForLiveRemux, ScanDispatchPrerequisites.Validate("watched", null, enqueueRemuxJobs: true));
        Assert.Null(ScanDispatchPrerequisites.Validate("watched", "out", enqueueRemuxJobs: true));
    }

    // --- watched-file dispatch verdict -------------------------------------------------------------------

    [Fact]
    public void Watched_file_dispatch_proceeds_when_no_row_blocks_it()
    {
        var outcome = WatchedFileDispatch.Evaluate([], new FileAnchorCandidate("Movie"));
        Assert.Equal(WatchedFileDispatchOutcome.Proceed, outcome.Verdict);
    }

    [Fact]
    public void Watched_file_dispatch_waits_upstream_when_a_row_is_actively_importing_it()
    {
        var view = new RefinerQueueRowView(AppliesToFile: true, IsUpstreamActive: true, IsImportPending: false);
        var row = new AttributedQueueRow("Radarr (4K)", view);
        var outcome = WatchedFileDispatch.Evaluate([row], new FileAnchorCandidate("Movie"));
        Assert.Equal(WatchedFileDispatchOutcome.WaitUpstream, outcome.Verdict);
        Assert.NotNull(outcome.BlockedReason);
        Assert.Equal("Radarr (4K)", outcome.BlockedConnection);
        Assert.Contains("Radarr (4K)", outcome.BlockedReason, StringComparison.Ordinal);
    }

    // --- resolution class weighting ------------------------------------------------------------------

    [Theory]
    [InlineData(1000L, null, "sd")]
    [InlineData(1280L, null, "720p")]
    [InlineData(1920L, null, "1080p")]
    [InlineData(3840L, null, "4k")]
    [InlineData(null, 600L, "sd")]
    [InlineData(null, 900L, "720p")]
    [InlineData(null, null, "undetermined")]
    public void Resolution_class_bands_by_width_then_falls_back_to_height(long? width, long? height, string expected) =>
        Assert.Equal(expected, RunnerUnits.ResolutionClassForDimensions(width, height));

    // --- file settling: same shape as observe_size_settling ---------------------------------------------

    [Fact]
    public void A_first_observation_is_always_settling()
    {
        var now = DateTimeOffset.UtcNow;
        var result = FileSettling.ObserveSizeSettling(Library(), null, null, 100, now);
        Assert.True(result.IsSettling);
    }

    [Fact]
    public void A_size_that_changed_since_the_last_scan_is_settling()
    {
        var now = DateTimeOffset.UtcNow;
        var result = FileSettling.ObserveSizeSettling(Library(), previousSizeBytes: 50, previousSizeChangedAt: now.AddSeconds(-5), currentSizeBytes: 100, now);
        Assert.True(result.IsSettling);
    }

    [Fact]
    public void A_size_unchanged_past_the_interval_is_stable()
    {
        var now = DateTimeOffset.UtcNow;
        var result = FileSettling.ObserveSizeSettling(Library(), previousSizeBytes: 100, previousSizeChangedAt: now.AddSeconds(-31), currentSizeBytes: 100, now);
        Assert.False(result.IsSettling);
    }

    [Fact]
    public void Ignoring_size_changes_never_settles()
    {
        var now = DateTimeOffset.UtcNow;
        var result = FileSettling.ObserveSizeSettling(Library() with { IgnoreSizeChanges = true }, null, null, 100, now);
        Assert.False(result.IsSettling);
    }

    // --- decide_file_state: reason order (disabled > paused > schedule > hold > blocked > unprocessed) ---

    [Fact]
    public void A_disabled_library_wins_over_every_other_reason()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(enabled: false), inScheduleWindow: false, fileAgeSeconds: 0, pausedReason: "paused", pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: true, settlingReason: null, settlingStableAt: null, accessProblem: "locked",
            blockedByConnection: "Radarr", minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.Disabled, verdict.Status);
    }

    [Fact]
    public void A_suite_pause_reports_out_of_schedule_with_the_pause_reason()
    {
        var now = DateTimeOffset.UtcNow;
        var verdict = FileStateDecision.DecideFileState(
            Library(), inScheduleWindow: true, fileAgeSeconds: 1000, pausedReason: "Processing is paused.", pausedUntil: now.AddHours(1),
            windowReopensAt: null, sizeIsSettling: false, settlingReason: null, settlingStableAt: null, accessProblem: null,
            blockedByConnection: null, minimumAgeSeconds: null, now: now);
        Assert.Equal(RefinerFileStatuses.OutOfSchedule, verdict.Status);
        Assert.Equal("Processing is paused.", verdict.Reason);
    }

    [Fact]
    public void Outside_the_schedule_window_reports_out_of_schedule()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(scheduleEnabled: true), inScheduleWindow: false, fileAgeSeconds: 1000, pausedReason: null, pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: false, settlingReason: null, settlingStableAt: null, accessProblem: null,
            blockedByConnection: null, minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.OutOfSchedule, verdict.Status);
    }

    [Fact]
    public void A_settling_file_is_on_hold_before_the_access_probe_even_runs()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(), inScheduleWindow: true, fileAgeSeconds: 1000, pausedReason: null, pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: true, settlingReason: "still growing", settlingStableAt: null, accessProblem: "locked",
            blockedByConnection: null, minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.OnHold, verdict.Status);
        Assert.Equal("still growing", verdict.Reason);
    }

    [Fact]
    public void A_file_younger_than_the_minimum_age_is_on_hold()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(minFileAgeSeconds: 60), inScheduleWindow: true, fileAgeSeconds: 5, pausedReason: null, pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: false, settlingReason: null, settlingStableAt: null, accessProblem: null,
            blockedByConnection: null, minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.OnHold, verdict.Status);
    }

    [Fact]
    public void An_access_problem_holds_the_file()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(minFileAgeSeconds: 0), inScheduleWindow: true, fileAgeSeconds: 1000, pausedReason: null, pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: false, settlingReason: null, settlingStableAt: null, accessProblem: "still locked",
            blockedByConnection: null, minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.OnHold, verdict.Status);
        Assert.Equal("still locked", verdict.Reason);
    }

    [Fact]
    public void A_manager_holding_the_file_blocks_it_upstream()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(minFileAgeSeconds: 0), inScheduleWindow: true, fileAgeSeconds: 1000, pausedReason: null, pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: false, settlingReason: null, settlingStableAt: null, accessProblem: null,
            blockedByConnection: "Radarr", minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.BlockedUpstream, verdict.Status);
        Assert.Equal("Radarr", verdict.BlockedByConnection);
    }

    [Fact]
    public void A_file_clearing_every_gate_is_unprocessed_and_eligible()
    {
        var verdict = FileStateDecision.DecideFileState(
            Library(minFileAgeSeconds: 0), inScheduleWindow: true, fileAgeSeconds: 1000, pausedReason: null, pausedUntil: null,
            windowReopensAt: null, sizeIsSettling: false, settlingReason: null, settlingStableAt: null, accessProblem: null,
            blockedByConnection: null, minimumAgeSeconds: null, now: DateTimeOffset.UtcNow);
        Assert.Equal(RefinerFileStatuses.Unprocessed, verdict.Status);
        Assert.True(verdict.Eligible);
    }

    // --- library admission rejection -------------------------------------------------------------------

    private static readonly LibraryAdmissionRules NoRules = new(
        MediaExtensions: new HashSet<string>(), ExcludeMarkers: new HashSet<string>(), IncludePatterns: [], ExcludePatterns: [],
        MinFileSizeMb: 0, MaxFileSizeMb: 0, RejectedFileAction: "leave", MinFileAgeSeconds: 0,
        CreatedAfter: null, CreatedBefore: null, ModifiedAfter: null, ModifiedBefore: null, ExcludeHidden: false, TopLevelOnly: false);

    [Fact]
    public void A_file_below_the_minimum_size_is_rejected()
    {
        var rules = NoRules with { MinFileSizeMb = 100 };
        var rejection = LibraryAdmission.Rejection("a.mkv", "a.mkv", new CandidateFileFacts(10 * 1024 * 1024, null, null), rules);
        Assert.NotNull(rejection);
        Assert.Equal("skipped_below_minimum_file_size", rejection!.Counter);
    }

    [Fact]
    public void A_file_above_the_maximum_size_is_rejected()
    {
        var rules = NoRules with { MaxFileSizeMb = 10 };
        var rejection = LibraryAdmission.Rejection("a.mkv", "a.mkv", new CandidateFileFacts(100 * 1024 * 1024, null, null), rules);
        Assert.NotNull(rejection);
        Assert.Equal("skipped_above_maximum_file_size", rejection!.Counter);
    }

    [Fact]
    public void A_file_not_matching_include_patterns_is_rejected()
    {
        var rules = NoRules with { IncludePatterns = ["*.mp4"] };
        var rejection = LibraryAdmission.Rejection("Movie/a.mkv", "a.mkv", new CandidateFileFacts(1024, null, null), rules);
        Assert.NotNull(rejection);
        Assert.Equal("skipped_by_include_pattern", rejection!.Counter);
    }

    [Fact]
    public void A_file_matching_exclude_patterns_is_rejected()
    {
        var rules = NoRules with { ExcludePatterns = ["*sample*"] };
        var rejection = LibraryAdmission.Rejection("Movie/a.sample.mkv", "a.sample.mkv", new CandidateFileFacts(1024, null, null), rules);
        Assert.NotNull(rejection);
        Assert.Equal("skipped_by_exclude_pattern", rejection!.Counter);
    }

    [Fact]
    public void A_file_matching_every_rule_is_admitted()
    {
        var rejection = LibraryAdmission.Rejection("Movie/a.mkv", "a.mkv", new CandidateFileFacts(1024 * 1024, null, null), NoRules);
        Assert.Null(rejection);
    }

    [Theory]
    [InlineData("Movie/a.mkv", "*.mkv", true)]
    [InlineData("Movie/a.mp4", "*.mkv", false)]
    [InlineData("a.mkv", "a?mkv", true)]
    [InlineData("axmkv", "a?mkv", true)]
    [InlineData("abmkv", "a?mkv", true)]
    [InlineData("cat.mkv", "[cb]at.mkv", true)]
    [InlineData("dog.mkv", "[cb]at.mkv", false)]
    public void Fnmatch_style_glob_matches_shell_patterns(string value, string pattern, bool expected) =>
        Assert.Equal(expected, LibraryAdmission.FnMatch(value, pattern));
}
