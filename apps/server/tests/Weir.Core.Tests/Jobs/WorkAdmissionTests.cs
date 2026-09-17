using Weir.Core.Activity;
using Weir.Core.Jobs;

namespace Weir.Core.Tests.Jobs;

/// <summary>
/// The pure half of <c>refiner_work_admission</c> (pause, library windows, per-library caps, runner budget),
/// the remux temp name patterns (#534) and activity classification.
/// </summary>
public sealed class WorkAdmissionTests
{
    private const string Remux = "refiner.file.remux_pass.v1";
    private const string Scan = "refiner.watched_folder.remux_scan_dispatch.v1";
    private static readonly DateTimeOffset Now = ScheduleGridTests.Now;

    [Fact]
    public void A_pause_with_no_expiry_stays_paused()
    {
        var state = PauseState.Resolve(true, null, true, Now);

        Assert.True(state.Paused);
        Assert.False(state.Expired);
        Assert.Contains("when you resume it", state.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void A_pause_expires_on_its_own_without_a_background_task()
    {
        var state = PauseState.Resolve(true, Now.AddMinutes(-1), true, Now);

        Assert.False(state.Paused);
        Assert.True(state.Expired);
        Assert.Equal(string.Empty, state.Reason);
    }

    [Fact]
    public void A_pause_that_has_not_yet_expired_is_still_a_pause_and_says_when()
    {
        var state = PauseState.Resolve(true, Now.AddHours(2), true, Now);

        Assert.True(state.Paused);
        Assert.Equal("Processing is paused. Weir will start work again automatically at 2026-08-26 16:00 UTC.", state.Reason);
    }

    [Fact]
    public void An_unpaused_suite_drops_the_until_time()
    {
        Assert.Equal(new PauseState(false, null, false), PauseState.Resolve(false, Now.AddHours(1), false, Now));
    }

    [Fact]
    public void Detection_job_kinds_are_recognised()
    {
        Assert.True(WorkAdmissionRules.IsDetectionJobKind(Scan));
        Assert.False(WorkAdmissionRules.IsDetectionJobKind(Remux));
    }

    [Fact]
    public void Admission_allows_only_detection_while_paused_with_scanning_on()
    {
        var paused = new WorkAdmission(new PauseState(true, null, true), new HashSet<long>());
        Assert.True(paused.AllowsJobKind(Scan));
        Assert.False(paused.AllowsJobKind(Remux));
        Assert.True(paused.BlocksProcessing);
        Assert.False(paused.BlocksDetection);

        var stopped = paused with { Pause = new PauseState(true, null, false) };
        Assert.False(stopped.AllowsJobKind(Scan));
        Assert.True(stopped.BlocksDetection);
    }

    [Fact]
    public void Without_suite_settings_nothing_is_blocked_but_the_budget_is_zero()
    {
        var admission = WorkAdmissionRules.Evaluate(null, null, [], [Library(1) with { Enabled = false }], Now);

        Assert.False(admission.Pause.Paused);
        Assert.True(admission.Pause.ScanWhilePaused);
        Assert.Empty(admission.BlockedLibraryIds);
        Assert.Equal(0, admission.AvailableUnits);
        Assert.Equal("UTC", admission.TimezoneName);
    }

    [Fact]
    public void Closed_disabled_and_full_libraries_are_blocked()
    {
        var suite = new SuitePauseSettings("  ", false, null, true);
        LibraryAdmissionSnapshot[] libraries =
        [
            Library(1),
            Library(2) with { ScheduleGrid = new string('0', ScheduleGrid.SlotsPerWeek) },
            Library(3) with { Enabled = false },
            Library(4) with { MaxConcurrentFiles = 2 },
            Library(5) with { MaxConcurrentFiles = 0 },
            Library(6) with { ScheduleEnabled = false, ScheduleGrid = new string('0', ScheduleGrid.SlotsPerWeek) },
        ];
        LeasedJobSnapshot[] leased =
        [
            new(1, "{\"library_id\": 4}"),
            new(1, "{\"library_id\": 4}"),
            new(0, "{\"library_id\": 5}"),
            new(2, "not json"),
        ];

        var admission = WorkAdmissionRules.Evaluate(suite, null, leased, libraries, Now);

        Assert.Equal([2L, 3L, 4L, 5L], admission.BlockedLibraryIds.Order());
        Assert.Equal("UTC", admission.TimezoneName);
        // Default budget: capacity 4, four units in use.
        Assert.Equal(0, admission.AvailableUnits);
        Assert.Equal(4, admission.Capacity);
    }

    [Fact]
    public void The_budget_counts_leased_runner_costs_against_capacity()
    {
        var budget = RunnerBudget.FromSettings(6, 0, 0, 1, 2, 0);
        var admission = WorkAdmissionRules.Evaluate(
            new SuitePauseSettings("UTC", false, null, true),
            budget,
            [new LeasedJobSnapshot(2, null), new LeasedJobSnapshot(-3, null)],
            [],
            Now);

        Assert.Equal(4, admission.AvailableUnits);
        Assert.Equal(6, admission.Capacity);
        Assert.Equal(2, budget.CostFor("4K "));
        Assert.Equal(0, budget.CostFor("8k"));
        Assert.Equal(0, budget.CostFor(null));
        Assert.Equal(4, RunnerBudget.FromSettings(0, 0, 0, 0, 0, 0).Capacity);
        Assert.Equal(1, RunnerBudget.FromSettings(-2, -1, 0, 0, 0, 0).Capacity);
        Assert.Equal(0, RunnerBudget.FromSettings(4, -1, 0, 0, 0, 0).CostFor("sd"));
    }

    [Fact]
    public void Library_windows_fall_back_to_days_and_hours_without_a_grid()
    {
        var hoursLimited = Library(1) with { ScheduleHoursLimited = true, ScheduleDays = "Wed", ScheduleStart = "09:00", ScheduleEnd = "13:00" };
        Assert.False(WorkAdmissionRules.LibraryWindowOpen(hoursLimited, "UTC", Now));
        Assert.True(WorkAdmissionRules.LibraryWindowOpen(hoursLimited with { ScheduleEnd = "" }, "UTC", Now));
        Assert.True(WorkAdmissionRules.LibraryWindowOpen(hoursLimited with { ScheduleHoursLimited = false }, "UTC", Now));
        Assert.Null(WorkAdmissionRules.LibraryWindowReopensAt(hoursLimited, "UTC", Now));
        Assert.Equal(
            Now.AddMinutes(15),
            WorkAdmissionRules.LibraryWindowReopensAt(hoursLimited with { ScheduleGrid = new string('1', ScheduleGrid.SlotsPerWeek) }, "UTC", Now));
    }

    [Theory]
    [InlineData("{\"library_id\": 7}", 7L)]
    [InlineData("{\"library_id\": true}", 1L)]
    [InlineData("{\"library_id\": 7.0}", null)]
    [InlineData("{\"library_id\": \"7\"}", null)]
    [InlineData("[7]", null)]
    [InlineData("", null)]
    [InlineData("{", null)]
    public void Library_ids_are_read_from_payloads_as_python_reads_them(string payload, long? expected)
    {
        Assert.Equal(expected, JobPayload.LibraryIdForAdmission(payload));
    }

    [Theory]
    [InlineData("Film.refiner.ab12_x9z.mkv", true)]
    [InlineData("Film.2020.1080p.refiner.qwertyui.mp4", true)]
    [InlineData("dry-run-ffmpeg-destination-placeholder.mkv", true)]
    [InlineData("Film.refiner.notes.txt", false)]
    [InlineData("Film.refiner.ABCDEFGH.mkv", false)]
    [InlineData("Film.refiner.abcdefg.mkv", false)]
    [InlineData("Film.refiner.abcdefghi.mkv", false)]
    [InlineData("Film.mkv", false)]
    [InlineData(".refiner.abcdefgh.mkv", false)]
    [InlineData("Film.refiner.abcdefgh", false)]
    [InlineData("planned-ffmpeg-destination-placeholder.mkv", false)]
    public void Only_names_weir_creates_count_as_remux_temp_output(string name, bool matches)
    {
        Assert.Equal(matches, WeirTempFiles.IsRemuxTempName(name));
    }

    [Fact]
    public void Temp_names_for_one_source_follow_mkstemp_with_the_source_stem_and_suffix()
    {
        var pattern = WeirTempFiles.RemuxTempNameFor("Movies/Film (2020)/Film (2020).mp4");
        Assert.Matches(pattern, "Film (2020).refiner.a1b2c3d4.mp4");
        Assert.DoesNotMatch(pattern, "Film (2020).refiner.a1b2c3d4.mkv");
        Assert.DoesNotMatch(pattern, "Other.refiner.a1b2c3d4.mp4");
        Assert.DoesNotMatch(pattern, "Film (2020).mp4");

        // No suffix: mkstemp was given ".mkv".
        Assert.Matches(WeirTempFiles.RemuxTempNameFor(@"tv\Show\episode"), "episode.refiner.zzzzzzzz.mkv");
        Assert.Equal(("archive.tar", ".gz"), WeirTempFiles.PythonStemAndSuffix("archive.tar.gz"));
        Assert.Equal((".hidden", string.Empty), WeirTempFiles.PythonStemAndSuffix(".hidden"));
    }

    [Theory]
    [InlineData(".movie.mkv.abc.partial", true)]
    [InlineData("..partial", true)]
    [InlineData(".partial", false)]
    [InlineData("movie.partial", false)]
    [InlineData(".movie.mkv", false)]
    public void Partial_outputs_match_the_hidden_partial_glob(string name, bool matches)
    {
        Assert.Equal(matches, WeirTempFiles.IsPartialOutputName(name, ignoreCase: false));
    }

    [Fact]
    public void Activity_facts_are_lifted_from_the_detail()
    {
        var facts = ActivityFacts.Classify(
            ActivityEventTypes.RefinerWorkerFailure,
            "{\"job_id\":3,\"result\":\"Retrying\",\"trigger\":\" Scheduled \",\"library_id\":4,\"relative_media_path\":\" a/b.mkv \",\"run_id\":9}");
        Assert.Equal(new ActivityFacts("scheduled", "retrying", 4, "a/b.mkv", "run:9"), facts);

        Assert.Equal(new ActivityFacts(null, "failed", null, null, null), ActivityFacts.Classify(ActivityEventTypes.RefinerWorkerFailure, null));
        Assert.Equal(new ActivityFacts("manual", "failed", null, null, "run:True"), ActivityFacts.Classify("auth.login", "{\"ok\":false,\"library_id\":true,\"run_id\":true}"));
        Assert.Equal("skipped", ActivityFacts.Classify(ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "{\"result\":\"skipped\"}").Result);
        // Python's word order: "failure" (in the event type's name) is checked before "completed".
        Assert.Equal("failed", ActivityFacts.Classify(ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "not json").Result);
    }

    private static LibraryAdmissionSnapshot Library(long id) =>
        new(id, Enabled: true, ScheduleEnabled: true, ScheduleGrid: string.Empty, ScheduleHoursLimited: false, ScheduleDays: string.Empty,
            ScheduleStart: "00:00", ScheduleEnd: "23:59", MaxConcurrentFiles: 1);
}
