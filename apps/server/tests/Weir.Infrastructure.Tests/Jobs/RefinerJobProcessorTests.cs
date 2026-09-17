using System.Text.Json;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Ports of <c>process_one_refiner_job</c> tests from <c>test_refiner_worker_loop.py</c>,
/// <c>test_retired_job_kinds.py</c> and <c>test_worker_failures.py</c>, plus the .NET rule that unported
/// kinds are never claimed.
/// </summary>
public sealed class RefinerJobProcessorTests : IDisposable
{
    private static readonly DateTimeOffset T0 = JobsTestDatabase.T0;
    private readonly JobsTestDatabase _db = new();

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task Process_one_is_idle_when_no_jobs()
    {
        Assert.Equal(JobProcessOutcome.Idle, await _db.Processor().ProcessOneAsync("test-owner"));
    }

    [Fact]
    public async Task Process_one_completes_with_success_handler()
    {
        await _db.Store.EnqueueOrGetAsync("d1", "refiner.test.ok.v1", maxAttempts: 3);
        JobWorkContext? seen = null;
        var notifications = new RecordingNotifications();
        var processor = _db.Processor([new DelegateHandler("refiner.test.ok.v1", context => seen = context)], notifications: notifications);

        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));

        Assert.Equal(new JobWorkContext(1, "refiner.test.ok.v1", null, "w", 1, 3), seen);
        Assert.Equal(RefinerJobStatus.Completed, (await _db.Store.GetAsync(1))!.Status);
        Assert.Equal(["completed 1 refiner.test.ok.v1 willRetry=False"], notifications.Sent);
    }

    [Fact]
    public async Task Process_one_fail_path_on_handler_error()
    {
        await _db.Store.EnqueueOrGetAsync("d2", "refiner.test.bad.v1", maxAttempts: 1);
        var notifications = new RecordingNotifications();
        var processor = _db.Processor([new DelegateHandler("refiner.test.bad.v1", _ => throw new InvalidOperationException("boom"))], notifications: notifications);

        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Failed, row.Status);
        Assert.Contains("Refiner job failed", row.LastError, StringComparison.Ordinal);
        Assert.Contains("marked failed", row.LastError, StringComparison.Ordinal);
        Assert.Equal(["failed 1 refiner.test.bad.v1 willRetry=False"], notifications.Sent);
    }

    [Fact]
    public async Task Process_one_marks_a_failure_notification_retry_aware_when_another_attempt_follows()
    {
        // #540 item 6: the notification wording says a retry is coming instead of always claiming
        // retries are exhausted.
        await _db.Store.EnqueueOrGetAsync("d2b", "refiner.test.bad.v1", maxAttempts: 3);
        var notifications = new RecordingNotifications();
        var processor = _db.Processor([new DelegateHandler("refiner.test.bad.v1", _ => throw new InvalidOperationException("boom"))], notifications: notifications);

        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));

        Assert.Equal(RefinerJobStatus.Pending, (await _db.Store.GetAsync(1))!.Status);
        Assert.Equal(["failed 1 refiner.test.bad.v1 willRetry=True"], notifications.Sent);
    }

    [Fact]
    public async Task A_failure_with_attempts_left_says_it_will_be_tried_again()
    {
        await _db.Store.EnqueueOrGetAsync("a", "refiner.test.bad.v1", maxAttempts: 3);
        var processor = _db.Processor([new DelegateHandler("refiner.test.bad.v1", _ => throw new InvalidOperationException("boom"))]);

        await processor.ProcessOneAsync("w", now: T0);

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Pending, row.Status);
        Assert.Contains("try this job again shortly", row.LastError, StringComparison.Ordinal);
        Assert.DoesNotContain("marked failed", row.LastError, StringComparison.Ordinal);
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. Weir will try this job again shortly. Technical detail: InvalidOperationException: boom",
            row.LastError);
    }

    [Fact]
    public async Task An_unrecorded_handler_failure_writes_one_activity_entry_with_python_detail()
    {
        await _db.Store.EnqueueOrGetAsync(
            "c",
            "refiner.test.crash.v1",
            "{\"relative_media_path\": \" Films/Café.mkv \", \"library_id\": 4, \"media_scope\": \"tv\", \"trigger\": \"Webhook\", \"run_id\": \"r-1\"}",
            maxAttempts: 1);
        var recorder = new RecordingFailureRecorder(willRetry: null);
        var processor = _db.Processor([new DelegateHandler("refiner.test.crash.v1", _ => throw new InvalidOperationException("line one\n   line two"))], recorder);

        await processor.ProcessOneAsync("w", now: T0);

        var entry = Assert.Single(_db.ActivityEvents());
        Assert.Equal(ActivityEventTypes.RefinerWorkerFailure, entry.EventType);
        Assert.Equal("A Refiner job stopped with an error", entry.Title);
        Assert.Equal(
            "{\"job_id\":1,\"job_kind\":\"refiner.test.crash.v1\",\"failure_class\":\"unknown\"," +
            "\"message\":\"Refiner job failed: The job hit an unexpected error. This job is marked failed so it does not look successful.\"," +
            "\"next_action\":\"Review this job and use Start again after fixing the cause.\",\"retry_scheduled\":false,\"result\":\"failed\"," +
            "\"relative_media_path\":\"Films/Caf\\u00e9.mkv\",\"library_id\":4,\"trigger\":\"webhook\",\"run_id\":\"r-1\"}",
            entry.Detail);
        Assert.Equal("failed", entry.Result);
        var recorded = Assert.Single(recorder.Failures);
        Assert.Equal((4L, "tv", "Films/Café.mkv"), (recorded.LibraryId, recorded.MediaScope, recorded.RelativeMediaPath));
        Assert.Equal(1L, _db.Count("SELECT count(*) FROM activity_events WHERE library_id = 4 AND relative_path = 'Films/Café.mkv' AND \"trigger\" = 'webhook' AND run_key = 'run:r-1'"));
    }

    [Fact]
    public async Task A_retry_decided_by_the_failure_policy_is_reported_as_retrying()
    {
        await _db.Store.EnqueueOrGetAsync("r", "refiner.test.crash.v1", "{\"relative_media_path\": \"a.mkv\"}", maxAttempts: 1);
        var processor = _db.Processor([new DelegateHandler("refiner.test.crash.v1", _ => throw new InvalidOperationException("x"))], new RecordingFailureRecorder(willRetry: true));

        await processor.ProcessOneAsync("w", now: T0);

        using var detail = JsonDocument.Parse(Assert.Single(_db.ActivityEvents()).Detail!);
        Assert.True(detail.RootElement.GetProperty("retry_scheduled").GetBoolean());
        Assert.Equal("retrying", detail.RootElement.GetProperty("result").GetString());
    }

    [Fact]
    public async Task A_handler_that_recorded_its_own_failure_is_not_recorded_twice()
    {
        await _db.Store.EnqueueOrGetAsync("b", "refiner.test.recorded.v1", "{\"relative_media_path\": \"a.mkv\"}", maxAttempts: 1);
        var recorder = new RecordingFailureRecorder(willRetry: null);
        var processor = _db.Processor(
            [new DelegateHandler("refiner.test.recorded.v1", _ => throw new AlreadyRecordedFailureException("the output folder is not writable"))],
            recorder);

        await processor.ProcessOneAsync("w", now: T0);

        Assert.Empty(_db.ActivityEvents());
        Assert.Empty(recorder.Failures);
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. This job is marked failed so it does not look successful. Technical detail: AlreadyRecordedFailure: the output folder is not writable",
            (await _db.Store.GetAsync(1))!.LastError);
    }

    [Fact]
    public async Task Process_one_refuses_a_claimed_retired_row()
    {
        _db.InsertRawJob("legacy", "trimmer.radarr.cleanup_drive.v1");

        Assert.Equal(JobProcessOutcome.Processed, await _db.Processor([new DelegateHandler("refiner.test.other.v1", _ => { })]).ProcessOneAsync("t", now: T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Pending, row.Status);
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. Weir will try this job again shortly. Technical detail: RuntimeError: refiner worker refused a retired job_kind: 'trimmer.radarr.cleanup_drive.v1' (row id=1); nothing runs this kind any more",
            row.LastError);
    }

    [Fact]
    public async Task A_leftover_pruner_row_is_refused_until_its_attempts_are_used()
    {
        _db.InsertRawJob("legacy-pruner", "pruner.candidate_removal.preview.v1", maxAttempts: 2);
        var processor = _db.Processor();

        await processor.ProcessOneAsync("t", now: T0);
        Assert.Contains("refiner worker refused", (await _db.Store.GetAsync(1))!.LastError, StringComparison.Ordinal);
        await processor.ProcessOneAsync("t", now: T0.AddMinutes(1));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Failed, row.Status);
        Assert.Contains("marked failed", row.LastError, StringComparison.Ordinal);
        Assert.Empty(_db.ActivityEvents());
    }

    [Fact]
    public async Task Process_one_rejects_unprefixed_job_kind_row()
    {
        _db.InsertRawJob("legacy-unprefixed", "legacy.unprefixed");

        Assert.Equal(JobProcessOutcome.Processed, await _db.Processor([new DelegateHandler("refiner.test.other.v1", _ => { })]).ProcessOneAsync("t", 3600, T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Pending, row.Status);
        Assert.Contains("refiner.* prefix", row.LastError, StringComparison.Ordinal);
    }

    [Fact]
    public async Task An_unported_live_kind_is_never_claimed_by_a_dotnet_worker()
    {
        await _db.Store.EnqueueOrGetAsync("d3", "refiner.test.unknown.v1");

        Assert.Equal(JobProcessOutcome.Idle, await _db.Processor([new DelegateHandler("refiner.test.other.v1", _ => { })]).ProcessOneAsync("w", 3600, T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Pending, row.Status);
        Assert.Equal(0, row.AttemptCount);
        Assert.Null(row.LastError);
    }

    [Fact]
    public async Task Claiming_every_kind_fails_a_missing_handler_as_python_does()
    {
        await _db.Store.EnqueueOrGetAsync("d3", "refiner.test.unknown.v1");

        Assert.Equal(JobProcessOutcome.Processed, await _db.Processor(claimAllKinds: true).ProcessOneAsync("w", 3600, T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Pending, row.Status);
        Assert.Contains("refiner.test.unknown.v1", row.LastError, StringComparison.Ordinal);
        Assert.Contains("RefinerNoHandlerForJobKind", row.LastError, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Process_one_survives_complete_claim_raises()
    {
        await _db.Store.EnqueueOrGetAsync("d-complete-raise", "refiner.test.ok.v1", maxAttempts: 3);
        var processor = new RefinerJobProcessorWithComplete(_db, (_, _, _) => throw new InvalidOperationException("db write failed")).Processor;

        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.HandlerOkFinalizeFailed, row.Status);
        Assert.Equal(1, row.AttemptCount);
        Assert.Null(row.LeaseOwner);
        Assert.StartsWith("refiner_terminalization_failure:", row.LastError, StringComparison.Ordinal);
        Assert.Contains("db write failed", row.LastError, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Process_one_complete_refused_triggers_terminalization()
    {
        await _db.Store.EnqueueOrGetAsync("d-complete-false", "refiner.test.ok.v1", maxAttempts: 3);
        var processor = new RefinerJobProcessorWithComplete(_db, (_, _, _) => Task.FromResult(false)).Processor;

        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));

        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.HandlerOkFinalizeFailed, row.Status);
        Assert.Equal(
            "refiner_terminalization_failure: Refiner job failed: The job hit an unexpected error. The work ran, but Weir could not record that it finished. Technical detail: RuntimeError: complete_claimed_refiner_job refused (lease/state mismatch)",
            row.LastError);
    }

    [Fact]
    public async Task Terminalization_of_first_job_does_not_block_second_job_completion()
    {
        await _db.Store.EnqueueOrGetAsync("seq-a", "refiner.test.ok.v1", maxAttempts: 3);
        await _db.Store.EnqueueOrGetAsync("seq-b", "refiner.test.ok.v1", maxAttempts: 3);
        var processor = new RefinerJobProcessorWithComplete(_db, (id, owner, now) => id == 1
            ? throw new InvalidOperationException("first job complete failed")
            : _db.Store.CompleteClaimedAsync(id, owner, now)).Processor;

        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));
        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("w", 3600, T0));

        Assert.Equal(RefinerJobStatus.HandlerOkFinalizeFailed, (await _db.Store.GetAsync(1))!.Status);
        Assert.Equal(RefinerJobStatus.Completed, (await _db.Store.GetAsync(2))!.Status);
    }

    [Fact]
    public async Task A_long_handler_still_completes_against_the_claim_time()
    {
        // Python passes the claim-time `now` to complete, so a handler outliving its lease still completes.
        await _db.Store.EnqueueOrGetAsync("slow", "refiner.test.slow.v1");
        var processor = _db.Processor([new DelegateHandler("refiner.test.slow.v1", _ => _db.Clock.Now = T0.AddHours(3))]);

        await processor.ProcessOneAsync("w", 300, T0);

        Assert.Equal(RefinerJobStatus.Completed, (await _db.Store.GetAsync(1))!.Status);
    }

    [Fact]
    public async Task A_handler_stopped_by_shutdown_leaves_its_row_leased_for_recovery()
    {
        await _db.Store.EnqueueOrGetAsync("stop", "refiner.test.stop.v1");
        using var stopping = new CancellationTokenSource();
        var processor = _db.Processor([new DelegateHandler("refiner.test.stop.v1", async context =>
        {
            await stopping.CancelAsync();
            stopping.Token.ThrowIfCancellationRequested();
        })]);

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => processor.ProcessOneAsync("w", 300, T0, stopping.Token));

        Assert.Equal(RefinerJobStatus.Leased, (await _db.Store.GetAsync(1))!.Status);
    }

    [Fact]
    public async Task The_worker_claim_honours_the_schedule()
    {
        _db.SeedSuiteSettings();
        var library = _db.AddLibrary(scheduleGrid: new string('0', ScheduleGrid.SlotsPerWeek));
        await _db.Store.EnqueueOrGetAsync("gated", "refiner.test.ok.v1", $"{{\"library_id\": {library}}}");

        Assert.Equal(JobProcessOutcome.Idle, await _db.Processor([new DelegateHandler("refiner.test.ok.v1", _ => { })]).ProcessOneAsync("w", now: T0));
    }

    private sealed class RefinerJobProcessorWithComplete(JobsTestDatabase db, Func<long, string, DateTimeOffset, Task<bool>> complete)
    {
        public RefinerJobProcessor Processor { get; } = new(
            db.Store,
            new JobHandlerRegistry([new DelegateHandler("refiner.test.ok.v1", _ => { })]),
            new SqliteActivityWriter(db.Database),
            new NoUnhandledJobFailureRecorder(),
            new NoJobNotifications(),
            db.Clock,
            Microsoft.Extensions.Logging.Abstractions.NullLogger<RefinerJobProcessor>.Instance)
        {
            CompleteOverride = complete,
        };
    }

    private sealed class RecordingNotifications : IJobNotifications
    {
        public List<string> Sent { get; } = [];

        public void Dispatch(string moduleName, string eventKind, long jobId, string jobKind, bool willRetry = false) =>
            Sent.Add($"{eventKind} {jobId} {jobKind} willRetry={willRetry}");
    }

    private sealed class RecordingFailureRecorder(bool? willRetry) : IUnhandledJobFailureRecorder
    {
        public List<UnhandledJobFailure> Failures { get; } = [];

        public Task<bool?> RecordAsync(UnhandledJobFailure failure, CancellationToken cancellationToken)
        {
            Failures.Add(failure);
            return Task.FromResult(willRetry);
        }
    }
}
