using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Observability;
using Weir.Core.Time;

namespace Weir.Core.Tests.Jobs;

/// <summary>
/// Job kind guard, worker failure wording (#488), backoff and recovery wording. Expected strings were
/// produced by the Python reference (<c>weir.platform.jobs.worker_failures</c>, <c>jobs_ops</c>, <c>job_kind_guard</c>).
/// </summary>
public sealed class JobRulesTests
{
    private const string LegacyTrimmerJob = "trimmer.radarr.cleanup_drive.v1";
    private const string LegacySubberJob = "subber.subtitle_search.tv.v1";
    private const string LegacyPrunerJob = "pruner.candidate_removal.preview.v1";

    [Theory]
    [InlineData(LegacyTrimmerJob, true)]
    [InlineData(LegacySubberJob, true)]
    [InlineData(LegacyPrunerJob, true)]
    [InlineData("refiner.supplied_payload_evaluation.v1", true)]
    [InlineData("refiner.candidate_gate.v1", true)]
    [InlineData("refiner.file.remux_pass.v1", false)]
    [InlineData("Trimmer.x", false)] // case-sensitive, like str.startswith
    [InlineData("bare.kind", false)]
    public void Retired_prefixes_are_recognised(string kind, bool retired)
    {
        Assert.Equal(retired, JobKindGuard.IsRetired(kind));
    }

    [Fact]
    public void Enqueue_refuses_retired_and_unprefixed_kinds_with_python_wording()
    {
        Assert.Equal(
            "refiner_enqueue_or_get_job refuses a retired job_kind (got 'pruner.candidate_removal.preview.v1')",
            Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateEnqueueJobKind(LegacyPrunerJob)).Message);
        Assert.StartsWith("refiner_enqueue_or_get_job refuses", Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateEnqueueJobKind("trimmer.legacy.v1")).Message, StringComparison.Ordinal);
        Assert.StartsWith("refiner_enqueue_or_get_job refuses", Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateEnqueueJobKind(LegacySubberJob)).Message, StringComparison.Ordinal);
        Assert.Equal(
            "refiner_enqueue_or_get_job requires job_kind to start with 'refiner.' (got 'bare.kind')",
            Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateEnqueueJobKind("bare.kind")).Message);
        Assert.Equal(
            "refiner_enqueue_or_get_job requires job_kind to start with 'refiner.' (got \"it's\")",
            Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateEnqueueJobKind("it's")).Message);
        JobKindGuard.ValidateEnqueueJobKind("refiner.test.harness.v1");
    }

    [Fact]
    public void Handler_registry_keys_must_be_live_refiner_kinds()
    {
        Assert.Equal(
            "Refiner worker handler registry keys must start with 'refiner.' and must not use a retired prefix (offending keys: ['bare.kind', 'trimmer.x'])",
            Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateHandlerRegistry(["bare.kind", "trimmer.x", "refiner.ok"])).Message);
        Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateHandlerRegistry([LegacyPrunerJob]));
        Assert.Throws<ArgumentException>(() => JobKindGuard.ValidateHandlerRegistry([LegacySubberJob]));
        JobKindGuard.ValidateHandlerRegistry(["refiner.test.mechanics.v1"]);
    }

    [Fact]
    public void The_handler_registry_rejects_bad_and_duplicate_kinds_and_lists_its_kinds()
    {
        Assert.Throws<ArgumentException>(() => new JobHandlerRegistry([new NamedHandler(LegacyTrimmerJob)]));
        Assert.Throws<ArgumentException>(() => new JobHandlerRegistry([new NamedHandler("refiner.a.v1"), new NamedHandler("refiner.a.v1")]));
        var registry = new JobHandlerRegistry([new NamedHandler("refiner.b.v1"), new NamedHandler("refiner.a.v1")]);
        Assert.Equal(["refiner.a.v1", "refiner.b.v1"], registry.JobKinds);
        Assert.True(registry.Contains("refiner.a.v1"));
        Assert.Null(registry.Find("refiner.c.v1"));
        Assert.Empty(JobHandlerRegistry.Empty.JobKinds);
    }

    [Fact]
    public void Refused_kind_wording_names_no_queue_kind_where_a_person_reads()
    {
        var error = WorkerFailures.RefusedJobError("Refiner", "refused job_kind 'trimmer.x.v1' (row id=4)", willRetry: false);

        Assert.DoesNotContain("trimmer.x.v1", error.Split(" Technical detail:")[0], StringComparison.Ordinal);
        Assert.Contains("trimmer.x.v1", error, StringComparison.Ordinal);
        Assert.Contains("marked failed", error, StringComparison.Ordinal);
    }

    [Fact]
    public void Worker_failure_wording_matches_python_exactly()
    {
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. Weir will try this job again shortly. Technical detail: RuntimeError: refiner worker refused a retired job_kind: 'trimmer.radarr.cleanup_drive.v1' (row id=7); nothing runs this kind any more",
            WorkerFailures.RefusedJobError("Refiner", WorkerFailures.RetiredKindReason(LegacyTrimmerJob, 7), willRetry: true));
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. This job is marked failed so it does not look successful. Technical detail: RuntimeError: refiner worker refused job_kind missing required refiner.* prefix: 'legacy.unprefixed' (row id=2); enqueue only refiner-owned kinds",
            WorkerFailures.RefusedJobError("Refiner", WorkerFailures.UnprefixedKindReason("legacy.unprefixed", 2), willRetry: false));
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. Weir will try this job again shortly. Technical detail: RuntimeError: boom",
            WorkerFailures.StoredError(WorkerFailures.JobFailure("Refiner", FailureMessages.RuntimeError("boom"), willRetry: true)));
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. This job is marked failed so it does not look successful. Technical detail: RuntimeError: boom",
            WorkerFailures.StoredError(WorkerFailures.JobFailure("Refiner", FailureMessages.RuntimeError("boom"), willRetry: false)));
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. Weir will try this job again shortly. Technical detail: RefinerNoHandlerForJobKind: no Refiner job handler registered for job_kind='refiner.test.unknown.v1'",
            WorkerFailures.StoredError(WorkerFailures.JobFailure("Refiner", WorkerFailures.NoHandler("refiner.test.unknown.v1"), willRetry: true)));
        Assert.Equal(
            "Refiner job failed: Weir could not use the saved credentials. This job is marked failed so it does not look successful. Next action: Re-enter the the provider credentials and run the connection test again. Technical detail: RuntimeError: api_key=[redacted] token: [redacted]",
            WorkerFailures.StoredError(WorkerFailures.JobFailure("Refiner", FailureMessages.RuntimeError("api_key=abc123 token: xyz"), willRetry: false)));
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. This job is marked failed so it does not look successful. Technical detail: AlreadyRecordedFailure: the output folder is not writable",
            WorkerFailures.StoredError(WorkerFailures.JobFailure("Refiner", FailureMessages.FromDotNet(new AlreadyRecordedFailureException("the output folder is not writable")), willRetry: false)));
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. The work ran, but Weir could not record that it finished. Technical detail: RuntimeError: complete_claimed_refiner_job refused (lease/state mismatch)",
            WorkerFailures.StoredError(FailureMessages.FromException(
                "Refiner",
                "job",
                FailureMessages.RuntimeError("complete_claimed_refiner_job refused (lease/state mismatch)"),
                continuation: "The work ran, but Weir could not record that it finished.")));
        Assert.Equal(
            "Refiner job failed: Weir could not use a file or folder it needed. This job is marked failed so it does not look successful. Next action: Check that the file or folder still exists and that Weir can read and write it. Technical detail: FileNotFoundError: gone",
            WorkerFailures.StoredError(WorkerFailures.JobFailure("Refiner", FailureMessages.FromDotNet(new FileNotFoundException("gone")), willRetry: false)));
    }

    [Fact]
    public void Stored_errors_are_bounded_to_ten_thousand_characters()
    {
        var failure = WorkerFailures.JobFailure("Refiner", FailureMessages.RuntimeError(new string('x', 20_000)), willRetry: false);
        Assert.Equal(1000, failure.TechnicalDetail!.Length);
        Assert.True(WorkerFailures.StoredError(failure with { Message = new string('m', 12_000) }).Length == 10_000);
    }

    [Fact]
    public void A_retry_is_coming_only_while_attempts_remain()
    {
        Assert.True(WorkerFailures.RetryComing(1, 3));
        Assert.True(WorkerFailures.RetryComing(2, 3));
        Assert.False(WorkerFailures.RetryComing(3, 3));
        Assert.False(WorkerFailures.RetryComing(4, 3));
    }

    [Theory]
    [InlineData(1, 30)]
    [InlineData(2, 60)]
    [InlineData(3, 120)]
    [InlineData(4, 240)]
    [InlineData(5, 480)]
    [InlineData(6, 960)]
    [InlineData(7, 1800)]
    [InlineData(40, 1800)]
    [InlineData(0, 15)]
    public void Retry_backoff_doubles_from_thirty_seconds_to_a_half_hour_cap(int attemptCount, double seconds)
    {
        Assert.Equal(seconds, JobQueueRules.RetryBackoffSeconds(attemptCount));
    }

    [Fact]
    public void Cancelled_dedupe_keys_become_tombstones_within_the_column_limit()
    {
        Assert.Equal("reuse-me:cancelled:12", JobQueueRules.TombstoneCancelledDedupeKey("reuse-me", 12));
        var longKey = JobQueueRules.TombstoneCancelledDedupeKey(new string('k', 600), 12345);
        Assert.Equal(512, longKey.Length);
        Assert.Equal(new string('k', 512 - ":cancelled:12345".Length) + ":cancelled:12345", longKey);
    }

    [Fact]
    public void Recovering_a_finalize_failure_appends_an_audit_line()
    {
        var at = new DateTimeOffset(2026, 4, 10, 12, 0, 0, TimeSpan.Zero);
        Assert.Equal(
            "refiner_terminalization_failure: synthetic\n--- manual_recover_finalize_failure: marked completed at 2026-04-10T12:00:00Z by tester " +
            "(handler was not re-run; row was handler_ok_finalize_failed).",
            JobQueueRules.RecoveredFinalizeFailureError("refiner_terminalization_failure: synthetic", at, "tester"));
        Assert.StartsWith("manual_recover_finalize_failure: marked completed at 2026-04-10T12:00:00.000500Z", JobQueueRules.RecoveredFinalizeFailureError("  ", at.AddTicks(5000), "x"), StringComparison.Ordinal);
    }

    [Fact]
    public void Python_isoformat_omits_zero_microseconds_and_keeps_the_offset()
    {
        var at = new DateTimeOffset(2026, 4, 10, 13, 0, 0, TimeSpan.Zero);
        Assert.Equal("2026-04-10 13:00:00+00:00", PyDateTime.FromDateTimeOffset(at).IsoFormat(' '));
        Assert.Equal("2026-04-10T13:00:00.123456+00:00", PyDateTime.FromDateTimeOffset(at.AddTicks(1_234_567)).IsoFormat('T'));
        Assert.Equal("2026-04-10T13:00:00-05:30", PyDateTime.FromDateTimeOffset(new DateTimeOffset(2026, 4, 10, 13, 0, 0, new TimeSpan(-5, -30, 0))).IsoFormat('T'));
    }

    [Fact]
    public void Startup_recovery_requeues_while_attempts_remain_and_fails_the_final_attempt()
    {
        var now = new DateTimeOffset(2026, 4, 29, 12, 0, 0, TimeSpan.Zero);

        var requeue = StartupJobRecovery.Decide(1, 3, now);
        Assert.Equal(RefinerJobStatus.Pending, requeue.Status);
        Assert.Equal(
            "Refiner job was interrupted by a Weir restart. Recovered at 2026-04-29T12:00:00+00:00 and queued for another safe attempt.",
            requeue.LastError);

        var failed = StartupJobRecovery.Decide(3, 3, now);
        Assert.Equal(RefinerJobStatus.Failed, failed.Status);
        Assert.Equal(
            "Refiner job was interrupted by a Weir restart after its final attempt. Recovered at 2026-04-29T12:00:00+00:00 and marked failed so the operator can inspect it.",
            failed.LastError);

        // max_attempts below one counts as one.
        Assert.False(StartupJobRecovery.Decide(1, 0, now).Requeued);
        Assert.True(StartupJobRecovery.Decide(0, 0, now).Requeued);
    }

    [Fact]
    public void Worker_slot_count_and_schedule_intervals_clamp_like_python()
    {
        Assert.Equal(1, WeirOptionsLoader.ClampRefinerWorkerCount(-1));
        Assert.Equal(0, WeirOptionsLoader.ClampRefinerWorkerCount(0));
        Assert.Equal(1, WeirOptionsLoader.ClampRefinerWorkerCount(1));
        Assert.Equal(8, WeirOptionsLoader.ClampRefinerWorkerCount(8));
        Assert.Equal(8, WeirOptionsLoader.ClampRefinerWorkerCount(9));
        Assert.Equal(60, WeirOptionsLoader.ClampRefinerScheduleIntervalSeconds(5));
        Assert.Equal(604_800, WeirOptionsLoader.ClampRefinerScheduleIntervalSeconds(10_000_000));
        Assert.Equal(0, WeirOptionsLoader.ClampRefinerMinFileAgeSeconds(-5));
    }

    [Fact]
    public void Periodic_schedule_counts_missed_runs_and_caps_its_sleep()
    {
        Assert.Equal(0, PeriodicSchedule.MissedDueRunCount(100, 100, 60));
        Assert.Equal(2, PeriodicSchedule.MissedDueRunCount(250, 100, 60));
        Assert.Equal(150, PeriodicSchedule.MissedDueRunCount(250, 100, 0.5)); // interval floor of one second
        Assert.Equal(0.25, PeriodicSchedule.NextSchedulerSleepSeconds(100, 50, 400, 60));
        Assert.Equal(60, PeriodicSchedule.NextSchedulerSleepSeconds(100, 500, 400, 60));
        Assert.Equal(10, PeriodicSchedule.NextSchedulerSleepSeconds(100, 110, 400, 60));
        Assert.Equal(10, PeriodicSchedule.WatchedFolderScanIntervalSeconds(1));
        Assert.Equal(300, PeriodicSchedule.WatchedFolderScanIntervalSeconds(null));
        Assert.Equal(604_800, PeriodicSchedule.WatchedFolderScanIntervalSeconds(10_000_000));
    }

    private sealed class NamedHandler(string kind) : IJobHandler
    {
        public string JobKind => kind;

        public Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken) => Task.CompletedTask;
    }
}
