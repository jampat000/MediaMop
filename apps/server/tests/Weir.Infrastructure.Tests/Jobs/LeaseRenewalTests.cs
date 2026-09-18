using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// #540 item 1: nothing renewed a lease, so a handler running longer than its lease could be claimed by
/// a second worker while the first was still running it (two ffmpeg processes on the same file). A
/// heartbeat now renews the lease roughly every lease/3 while the handler runs. Proven here with a real
/// SQLite file, a genuinely long-running fake handler and a second worker polling in parallel on its own
/// connection, using the real clock so the renewal heartbeat's own timer is exercised (a fake
/// <c>TimeProvider</c> only overrides <c>GetUtcNow</c>; <c>Task.Delay</c> still waits in real time).
/// </summary>
[Collection(SerialTestGroup.Name)]
public sealed class LeaseRenewalTests : IDisposable
{
    private const string Kind = "processing.test.long_running.v1";
    private readonly JobsTestDatabase _db = new();

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task A_job_running_longer_than_its_lease_is_never_claimed_by_another_worker()
    {
        await _db.Store.EnqueueOrGetAsync("long-running", Kind, maxAttempts: 3);

        var runningWorkerRuns = 0;
        var intruderRuns = 0;
        var runningHandler = new DelegateHandler(Kind, async _ =>
        {
            Interlocked.Increment(ref runningWorkerRuns);
            await Task.Delay(TimeSpan.FromMilliseconds(1200));
        });
        var intruderHandler = new DelegateHandler(Kind, _ => Interlocked.Increment(ref intruderRuns));

        var runningProcessor = new ProcessingJobProcessor(
            new ProcessingJobStore(new SqliteDatabase(_db.DbPath, pooling: false), TimeProvider.System),
            new JobHandlerRegistry([runningHandler]),
            new RecordingActivityWriter(),
            new NoUnhandledJobFailureRecorder(),
            new NoJobNotifications(),
            TimeProvider.System,
            NullLogger<ProcessingJobProcessor>.Instance);
        var intruderProcessor = new ProcessingJobProcessor(
            new ProcessingJobStore(new SqliteDatabase(_db.DbPath, pooling: false), TimeProvider.System),
            new JobHandlerRegistry([intruderHandler]),
            new RecordingActivityWriter(),
            new NoUnhandledJobFailureRecorder(),
            new NoJobNotifications(),
            TimeProvider.System,
            NullLogger<ProcessingJobProcessor>.Instance);

        // A one-second lease; the handler runs well past it, so only a working renewal keeps it safe.
        var runningTask = runningProcessor.ProcessOneAsync("worker-running", leaseSeconds: 1);
        await Task.Delay(150); // Let the running worker claim before the intruder starts polling.

        var intruderOutcomes = new List<JobProcessOutcome>();
        var pollDeadline = DateTime.UtcNow.AddMilliseconds(1300);
        while (DateTime.UtcNow < pollDeadline)
        {
            intruderOutcomes.Add(await intruderProcessor.ProcessOneAsync("worker-intruder", leaseSeconds: 1));
            await Task.Delay(80);
        }

        var outcome = await runningTask;

        Assert.Equal(JobProcessOutcome.Processed, outcome);
        Assert.Equal(1, runningWorkerRuns);
        Assert.Equal(0, intruderRuns);
        Assert.All(intruderOutcomes, o => Assert.Equal(JobProcessOutcome.Idle, o));
        Assert.Equal(ProcessingJobStatus.Completed, (await _db.Store.GetAsync(1))!.Status);
    }

    [Fact]
    public async Task The_lease_is_visibly_renewed_ahead_of_its_original_expiry()
    {
        await _db.Store.EnqueueOrGetAsync("renewed", Kind, maxAttempts: 3);
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var handler = new DelegateHandler(Kind, async _ =>
        {
            started.TrySetResult();
            await release.Task;
        });
        var store = new ProcessingJobStore(new SqliteDatabase(_db.DbPath, pooling: false), TimeProvider.System);
        var processor = new ProcessingJobProcessor(
            store,
            new JobHandlerRegistry([handler]),
            new RecordingActivityWriter(),
            new NoUnhandledJobFailureRecorder(),
            new NoJobNotifications(),
            TimeProvider.System,
            NullLogger<ProcessingJobProcessor>.Instance);

        var runTask = processor.ProcessOneAsync("worker", leaseSeconds: 1);
        await started.Task.WaitAsync(TimeSpan.FromSeconds(5));
        var originalExpiry = (await _db.Store.GetAsync(1))!.LeaseExpiresAt;

        // Wait past the original one-second lease; the heartbeat (every ~1/3 s) should have pushed it out.
        await Task.Delay(TimeSpan.FromMilliseconds(1300));
        var renewedExpiry = (await _db.Store.GetAsync(1))!.LeaseExpiresAt;
        Assert.True(renewedExpiry > originalExpiry, $"expected {renewedExpiry} > {originalExpiry}");

        release.TrySetResult();
        Assert.Equal(JobProcessOutcome.Processed, await runTask);
    }
}
