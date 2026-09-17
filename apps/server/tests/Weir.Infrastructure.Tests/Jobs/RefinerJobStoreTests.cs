using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>Ports of <c>test_refiner_jobs_claim.py</c>: enqueue dedupe, atomic claim, lease, complete, fail.</summary>
public sealed class RefinerJobStoreTests : IDisposable
{
    private const string Kind = "refiner.test.harness.v1";
    private static readonly DateTimeOffset T0 = JobsTestDatabase.T0;
    private readonly JobsTestDatabase _db = new();

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task Enqueue_duplicate_dedupe_key_returns_same_row()
    {
        var a = await _db.Store.EnqueueOrGetAsync("k1", Kind);
        var b = await _db.Store.EnqueueOrGetAsync("k1", Kind);

        Assert.Equal(a.Id, b.Id);
        Assert.Equal(1, _db.Count("SELECT count(*) FROM refiner_jobs"));
    }

    [Fact]
    public async Task Enqueue_writes_the_python_row_shape()
    {
        var job = await _db.Store.EnqueueOrGetAsync("shape", Kind, "{\"a\":1}", maxAttempts: 0, runnerCost: -4, priority: 7);

        Assert.Equal(RefinerJobStatus.Pending, job.Status);
        Assert.Equal(1, job.MaxAttempts);
        Assert.Equal(0, job.RunnerCost);
        Assert.Equal(7, job.Priority);
        Assert.Equal(0, job.AttemptCount);
        Assert.Null(job.LeaseOwner);
        Assert.Null(job.NotBefore);
        Assert.Equal("{\"a\":1}", job.PayloadJson);
    }

    [Fact]
    public async Task Concurrent_enqueue_same_dedupe_key_single_row()
    {
        using var barrier = new Barrier(8);
        var tasks = Enumerable.Range(0, 8).Select(_ => Task.Run(async () =>
        {
            barrier.SignalAndWait();
            return (await _db.Store.EnqueueOrGetAsync("race", Kind)).Id;
        })).ToArray();

        var ids = await Task.WhenAll(tasks);

        Assert.Single(ids.Distinct());
        Assert.Equal(1, _db.Count("SELECT count(*) FROM refiner_jobs"));
    }

    [Fact]
    public async Task Enqueue_refuses_retired_and_unprefixed_kinds()
    {
        await Assert.ThrowsAsync<ArgumentException>(() => _db.Store.EnqueueOrGetAsync("t", "pruner.candidate_removal.preview.v1"));
        await Assert.ThrowsAsync<ArgumentException>(() => _db.Store.EnqueueOrGetAsync("u", "bare.kind"));
        Assert.Equal(0, _db.Count("SELECT count(*) FROM refiner_jobs"));
    }

    [Fact]
    public async Task Second_claim_does_not_return_same_job_when_first_holds_lease()
    {
        await _db.Store.EnqueueOrGetAsync("solo", Kind);

        Assert.NotNull(await _db.Store.ClaimNextAsync("w1", T0.AddHours(1), T0));
        Assert.Null(await _db.Store.ClaimNextAsync("w2", T0.AddHours(1), T0));
    }

    [Fact]
    public async Task Expired_lease_can_be_reclaimed()
    {
        await _db.Store.EnqueueOrGetAsync("reclaim", Kind);
        var first = await _db.Store.ClaimNextAsync("w1", T0.AddSeconds(30), T0);
        Assert.NotNull(first);
        Assert.Equal(1, first.AttemptCount);

        var second = await _db.Store.ClaimNextAsync("w2", T0.AddHours(1), T0.AddMinutes(5));

        Assert.NotNull(second);
        Assert.Equal(first.Id, second.Id);
        Assert.Equal("w2", second.LeaseOwner);
        Assert.Equal(2, second.AttemptCount);
    }

    [Fact]
    public async Task Claim_writes_python_timestamp_text()
    {
        await _db.Store.EnqueueOrGetAsync("text", Kind);
        await _db.Store.ClaimNextAsync("w", T0.AddHours(1).AddTicks(1_234_567), T0);

        Assert.Equal("2026-04-10 13:00:00.123456+00:00", _db.Scalar("SELECT lease_expires_at FROM refiner_jobs"));
        Assert.Matches(@"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", (string)_db.Scalar("SELECT updated_at FROM refiner_jobs")!);
    }

    [Fact]
    public async Task Complete_only_succeeds_for_owning_lease()
    {
        await _db.Store.EnqueueOrGetAsync("done", Kind);
        var job = (await _db.Store.ClaimNextAsync("good", T0.AddHours(1), T0))!;

        Assert.False(await _db.Store.CompleteClaimedAsync(job.Id, "evil", T0));
        Assert.True(await _db.Store.CompleteClaimedAsync(job.Id, "good", T0));

        var row = (await _db.Store.GetAsync(job.Id))!;
        Assert.Equal(RefinerJobStatus.Completed, row.Status);
        Assert.Null(row.LeaseOwner);
        Assert.Null(row.LeaseExpiresAt);
        Assert.Null(row.LastError);
    }

    [Fact]
    public async Task Complete_fails_when_lease_expired_or_row_not_leased()
    {
        await _db.Store.EnqueueOrGetAsync("late", Kind);
        var job = (await _db.Store.ClaimNextAsync("w", T0.AddSeconds(10), T0))!;

        Assert.False(await _db.Store.CompleteClaimedAsync(job.Id, "w", T0.AddMinutes(30)));
        Assert.False(await _db.Store.CompleteClaimedAsync(9999, "w", T0));
        Assert.True(await _db.Store.CompleteClaimedAsync(job.Id, "w", T0.AddSeconds(10)));
        Assert.False(await _db.Store.CompleteClaimedAsync(job.Id, "w", T0));
    }

    [Fact]
    public async Task Fail_requeues_until_max_attempts_then_failed()
    {
        await _db.Store.EnqueueOrGetAsync("retry", Kind, maxAttempts: 2);
        long id = 0;
        for (var round = 0; round < 2; round++)
        {
            // Advance the clock enough to clear the not_before backoff of the previous failure.
            var now = T0.AddSeconds(round * 60);
            var job = await _db.Store.ClaimNextAsync("w", T0.AddHours(1), now);
            Assert.NotNull(job);
            Assert.Equal(round + 1, job.AttemptCount);
            id = job.Id;
            Assert.True(await _db.Store.FailClaimedAsync(id, "w", $"e{round}", now));
        }

        Assert.Null(await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0));
        var row = (await _db.Store.GetAsync(id))!;
        Assert.Equal(RefinerJobStatus.Failed, row.Status);
        Assert.Equal("e1", row.LastError);
        Assert.Null(row.NotBefore);
    }

    [Fact]
    public async Task A_failed_attempt_waits_out_its_backoff_before_it_can_be_claimed_again()
    {
        await _db.Store.EnqueueOrGetAsync("backoff", Kind, maxAttempts: 5);
        var job = (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!;
        Assert.True(await _db.Store.FailClaimedAsync(job.Id, "w", "boom", T0));

        Assert.Equal("2026-04-10 12:00:30.000000", _db.Scalar("SELECT not_before FROM refiner_jobs"));
        Assert.Null(await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0.AddSeconds(29)));
        Assert.NotNull(await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0.AddSeconds(30).AddTicks(10)));
        Assert.True(await _db.Store.FailClaimedAsync(job.Id, "w", "boom", T0.AddSeconds(31)));
        Assert.Equal("2026-04-10 12:01:31.000000", _db.Scalar("SELECT not_before FROM refiner_jobs"));
    }

    [Fact]
    public async Task Fail_refuses_a_wrong_owner_or_expired_lease()
    {
        await _db.Store.EnqueueOrGetAsync("guard", Kind);
        var job = (await _db.Store.ClaimNextAsync("good", T0.AddSeconds(5), T0))!;

        Assert.False(await _db.Store.FailClaimedAsync(job.Id, "evil", "x", T0));
        Assert.False(await _db.Store.FailClaimedAsync(job.Id, "good", "x", T0.AddSeconds(6)));
        Assert.Equal(RefinerJobStatus.Leased, (await _db.Store.GetAsync(job.Id))!.Status);
    }

    [Fact]
    public async Task Fail_leased_after_complete_failure_sets_handler_ok_finalize_failed()
    {
        await _db.Store.EnqueueOrGetAsync("term-fail", Kind);
        var job = (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!;
        Assert.Equal(1, job.AttemptCount);

        Assert.True(await _db.Store.FailLeasedAfterCompleteFailureAsync(job.Id, "w", "refiner_terminalization_failure: synthetic", T0));

        var row = (await _db.Store.GetAsync(job.Id))!;
        Assert.Equal(RefinerJobStatus.HandlerOkFinalizeFailed, row.Status);
        Assert.Equal(1, row.AttemptCount);
        Assert.Null(row.LeaseOwner);
        Assert.Contains("synthetic", row.LastError, StringComparison.Ordinal);
        Assert.Null(await _db.Store.ClaimNextAsync("w2", T0.AddHours(1), T0));
    }

    [Fact]
    public async Task Handler_ok_finalize_failed_row_is_not_claimable()
    {
        await _db.Store.EnqueueOrGetAsync("finalize-stuck", Kind);
        _db.Execute("UPDATE refiner_jobs SET status = 'handler_ok_finalize_failed', lease_owner = NULL, lease_expires_at = NULL WHERE id = 1");

        Assert.Null(await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0));
    }

    [Fact]
    public async Task Fail_leased_after_complete_failure_rejects_wrong_owner_and_bounds_the_error()
    {
        await _db.Store.EnqueueOrGetAsync("term-owner", Kind);
        var job = (await _db.Store.ClaimNextAsync("good", T0.AddHours(1), T0))!;

        Assert.False(await _db.Store.FailLeasedAfterCompleteFailureAsync(job.Id, "evil", "x", T0));
        Assert.True(await _db.Store.FailLeasedAfterCompleteFailureAsync(job.Id, "good", new string('e', 12_000), T0));
        Assert.Equal(10_000, (await _db.Store.GetAsync(job.Id))!.LastError!.Length);
    }

    [Fact]
    public async Task Recover_handler_ok_finalize_failed_to_completed()
    {
        await _db.Store.EnqueueOrGetAsync("recover-ok", Kind);
        var job = (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!;
        await _db.Store.FailLeasedAfterCompleteFailureAsync(job.Id, "w", "refiner_terminalization_failure: synthetic", T0);

        Assert.Equal(JobActionOutcome.Ok, await _db.Store.RecoverHandlerOkFinalizeFailedToCompletedAsync(job.Id, "tester", T0));

        var row = (await _db.Store.GetAsync(job.Id))!;
        Assert.Equal(RefinerJobStatus.Completed, row.Status);
        Assert.Equal(
            "refiner_terminalization_failure: synthetic\n--- manual_recover_finalize_failure: marked completed at 2026-04-10T12:00:00Z by tester " +
            "(handler was not re-run; row was handler_ok_finalize_failed).",
            row.LastError);
        Assert.Null(row.LeaseOwner);
    }

    [Fact]
    public async Task Recover_finalize_rejects_wrong_status_and_missing_job()
    {
        await _db.Store.EnqueueOrGetAsync("recover-wrong", Kind);
        var job = (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!;

        Assert.Equal(JobActionOutcome.WrongStatus, await _db.Store.RecoverHandlerOkFinalizeFailedToCompletedAsync(job.Id, "x", T0));
        Assert.Equal(JobActionOutcome.NotFound, await _db.Store.RecoverHandlerOkFinalizeFailedToCompletedAsync(99999, "x"));
    }

    [Fact]
    public async Task Two_workers_claim_different_jobs()
    {
        await _db.Store.EnqueueOrGetAsync("a", Kind);
        await _db.Store.EnqueueOrGetAsync("b", Kind);
        using var barrier = new Barrier(2);

        var claims = await Task.WhenAll(Enumerable.Range(0, 2).Select(index => Task.Run(async () =>
        {
            barrier.SignalAndWait();
            return (await _db.Store.ClaimNextAsync($"t{index}", T0.AddHours(1), T0))?.Id;
        })));

        Assert.Equal(2, claims.Where(id => id is not null).Distinct().Count());
    }

    [Fact]
    public async Task Cancel_pending_tombstones_dedupe_so_fresh_enqueue_reuses_key()
    {
        var job = await _db.Store.EnqueueOrGetAsync("reuse-me", Kind);

        Assert.Equal(JobActionOutcome.Ok, await _db.Store.CancelPendingAsync(job.Id));

        var old = (await _db.Store.GetAsync(job.Id))!;
        Assert.Equal(RefinerJobStatus.Cancelled, old.Status);
        Assert.Equal($"reuse-me:cancelled:{job.Id}", old.DedupeKey);
        Assert.Equal("Cancelled by operator before a worker claimed this job.", old.LastError);
        var fresh = await _db.Store.EnqueueOrGetAsync("reuse-me", Kind);
        Assert.NotEqual(job.Id, fresh.Id);
        Assert.Equal("reuse-me", fresh.DedupeKey);
        Assert.Equal(RefinerJobStatus.Pending, fresh.Status);
        Assert.Equal(JobActionOutcome.WrongStatus, await _db.Store.CancelPendingAsync(job.Id));
        Assert.Equal(JobActionOutcome.NotFound, await _db.Store.CancelPendingAsync(12345));
    }

    [Fact]
    public async Task Move_to_top_raises_a_pending_job_above_everything_waiting()
    {
        var first = await _db.Store.EnqueueOrGetAsync("p1", Kind, priority: 3);
        var second = await _db.Store.EnqueueOrGetAsync("p2", Kind);
        var third = await _db.Store.EnqueueOrGetAsync("p3", Kind);

        Assert.Equal(JobActionOutcome.Ok, await _db.Store.MoveToTopAsync(third.Id));
        Assert.Equal(JobActionOutcome.Ok, await _db.Store.MoveToTopAsync(second.Id));

        Assert.Equal(second.Id, (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!.Id);
        Assert.Equal(third.Id, (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!.Id);
        Assert.Equal(first.Id, (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!.Id);
        Assert.Equal(JobActionOutcome.WrongStatus, await _db.Store.MoveToTopAsync(first.Id));
        Assert.Equal(JobActionOutcome.NotFound, await _db.Store.MoveToTopAsync(404));
    }

    [Fact]
    public async Task Claim_order_is_priority_then_id()
    {
        await _db.Store.EnqueueOrGetAsync("low", Kind);
        var high = await _db.Store.EnqueueOrGetAsync("high", Kind, priority: 5);

        Assert.Equal(high.Id, (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0))!.Id);
    }

    [Fact]
    public async Task Claimable_kinds_leave_unhandled_live_kinds_pending_but_take_refused_kinds()
    {
        _db.InsertRawJob("unported", "refiner.file.remux_pass.v1");
        _db.InsertRawJob("retired", "trimmer.legacy.v1");
        _db.InsertRawJob("unprefixed", "legacy.unprefixed");
        _db.InsertRawJob("upper", "Refiner.case.v1");
        _db.InsertRawJob("handled", "refiner.handled.v1");
        var kinds = new ClaimableKinds(["refiner.handled.v1"], IncludeRefusedKinds: true);

        var claimed = new List<string>();
        while (await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0, kinds: kinds) is { } job)
        {
            claimed.Add(job.JobKind);
        }

        Assert.Equal(["trimmer.legacy.v1", "legacy.unprefixed", "Refiner.case.v1", "refiner.handled.v1"], claimed);
        Assert.Equal(RefinerJobStatus.Pending, (string?)_db.Scalar("SELECT status FROM refiner_jobs WHERE dedupe_key = 'unported'"));
        Assert.Null(await _db.Store.ClaimNextAsync("w", T0.AddHours(1), T0, kinds: new ClaimableKinds([], IncludeRefusedKinds: false)));
    }

    [Fact]
    public async Task Metrics_see_claims_completions_failures_and_queue_depth()
    {
        var metrics = new RecordingMetrics();
        var store = new RefinerJobStore(_db.Database, _db.Clock, metrics);
        await store.EnqueueOrGetAsync("m1", Kind, maxAttempts: 1);
        await store.EnqueueOrGetAsync("m2", Kind);
        var a = (await store.ClaimNextAsync("w", T0.AddHours(1), T0))!;
        await store.CompleteClaimedAsync(a.Id, "w", T0);
        var b = (await store.ClaimNextAsync("w", T0.AddHours(1), T0))!;
        await store.FailClaimedAsync(b.Id, "w", "x", T0);

        Assert.Equal(["started", "completed", "started"], metrics.Events);
        Assert.Equal([1, 2, 2, 1, 1, 1], metrics.Depths);
    }

    private sealed class RecordingMetrics : IJobQueueMetrics
    {
        public List<string> Events { get; } = [];

        public List<int> Depths { get; } = [];

        public void RecordJobEvent(string moduleName, string jobEvent) => Events.Add(jobEvent);

        public void SetQueueDepth(string moduleName, int depth) => Depths.Add(depth);
    }
}
