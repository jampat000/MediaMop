using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.Workers;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>Worker slots, heartbeats, history retention, periodic enqueue and the Activity writer.</summary>
public sealed class JobServicesTests : IDisposable
{
    private readonly JobsTestDatabase _db = new(keepSeedRows: true);

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task A_worker_slot_processes_a_job_then_stops_and_reports_stopped()
    {
        await _db.Store.EnqueueOrGetAsync("loop1", "processing.test.loop_ok.v1");
        var seen = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var heartbeats = new WorkerHeartbeats(TimeProvider.System);
        var service = WorkerService([new DelegateHandler("processing.test.loop_ok.v1", context => seen.TrySetResult(context.JobKind))], heartbeats, workerCount: 1);
        _db.Clock.Now = DateTimeOffset.UtcNow;

        await service.StartAsync(CancellationToken.None);
        Assert.Equal("processing.test.loop_ok.v1", await seen.Task.WaitAsync(TimeSpan.FromSeconds(10)));
        await WaitUntilAsync(async () => (await _db.Store.GetAsync(1))!.Status == ProcessingJobStatus.Completed);
        Assert.Equal("healthy", heartbeats.Snapshot([new("processing", 1)])[0].Status);
        await service.StopAsync(CancellationToken.None);

        var lane = heartbeats.Snapshot([new("processing", 1)])[0];
        Assert.Equal(("degraded", 1), (lane.Status, lane.StoppedWorkers));
    }

    [Fact]
    public async Task Slots_above_the_saved_files_at_once_value_stay_idle_but_keep_beating()
    {
        _db.Execute("UPDATE operator_settings SET max_concurrent_files = 3");
        var heartbeats = new WorkerHeartbeats(TimeProvider.System);
        var service = WorkerService([], heartbeats, workerCount: 8);

        await service.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => Task.FromResult(heartbeats.Snapshot([new("processing", 8)])[0].ActiveWorkers == 8));
        var lane = heartbeats.Snapshot([new("processing", 8)])[0];
        await service.StopAsync(CancellationToken.None);

        Assert.Equal("healthy", lane.Status);
    }

    [Fact]
    public async Task Only_slots_below_the_files_at_once_value_take_work()
    {
        _db.Execute("UPDATE operator_settings SET max_concurrent_files = 2");
        for (var i = 0; i < 12; i++)
        {
            await _db.Store.EnqueueOrGetAsync($"j{i}", "processing.test.owner.v1");
        }

        var owners = new System.Collections.Concurrent.ConcurrentBag<string>();
        var service = WorkerService([new DelegateHandler("processing.test.owner.v1", context => owners.Add(context.LeaseOwner))], new WorkerHeartbeats(TimeProvider.System), workerCount: 8);
        _db.Clock.Now = DateTimeOffset.UtcNow;

        await service.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => Task.FromResult(_db.Count("SELECT count(*) FROM jobs WHERE status = 'completed'") == 12));
        await service.StopAsync(CancellationToken.None);

        Assert.Subset(new HashSet<string> { ProcessingWorkerService.LeaseOwner(0), ProcessingWorkerService.LeaseOwner(1) }, owners.ToHashSet());
    }

    [Fact]
    public async Task A_worker_survives_a_crashed_tick()
    {
        // A handler that throws on the claim path's own machinery is covered by the processor; here the
        // database disappears under the worker and comes back.
        await _db.Store.EnqueueOrGetAsync("after", "processing.test.after.v1");
        var ran = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        _db.Execute("ALTER TABLE jobs RENAME TO jobs_hidden");
        var service = WorkerService([new DelegateHandler("processing.test.after.v1", _ => ran.TrySetResult())], new WorkerHeartbeats(TimeProvider.System), workerCount: 1);
        _db.Clock.Now = DateTimeOffset.UtcNow;

        await service.StartAsync(CancellationToken.None);
        await Task.Delay(200);
        _db.Execute("ALTER TABLE jobs_hidden RENAME TO jobs");
        await ran.Task.WaitAsync(TimeSpan.FromSeconds(10));
        await service.StopAsync(CancellationToken.None);
    }

    [Fact]
    public void Lease_owners_name_host_process_and_slot()
    {
        Assert.Equal($"{System.Net.Dns.GetHostName()}-{Environment.ProcessId}-w3", ProcessingWorkerService.LeaseOwner(3));
    }

    [Fact]
    public async Task History_retention_prunes_old_terminal_rows_only()
    {
        _db.InsertRawJob("old-done", "processing.a.v1", ProcessingJobStatus.Completed);
        _db.InsertRawJob("old-failed", "processing.a.v1", ProcessingJobStatus.Failed);
        _db.InsertRawJob("old-cancelled", "processing.a.v1", ProcessingJobStatus.Cancelled);
        _db.InsertRawJob("old-finalize", "processing.a.v1", ProcessingJobStatus.HandlerOkFinalizeFailed);
        _db.InsertRawJob("old-pending", "processing.a.v1");
        _db.InsertRawJob("old-leased", "processing.a.v1", ProcessingJobStatus.Leased);
        _db.InsertRawJob("new-done", "processing.a.v1", ProcessingJobStatus.Completed);
        _db.Execute("UPDATE jobs SET updated_at = '2025-01-01 00:00:00' WHERE dedupe_key LIKE 'old-%'");
        _db.Execute("INSERT INTO activity_events (created_at, event_type, module, title) VALUES ('2025-01-01 00:00:00', 'x', 'processing', 'old'), (CURRENT_TIMESTAMP, 'x', 'processing', 'new')");

        var counts = await JobRowsRetention.RunTickAsync(_db.Store, 90, DateTimeOffset.UtcNow);

        Assert.Equal(4, counts.Processing);
        Assert.Equal(1, counts.Activity);
        Assert.Equal(5, counts.Total);
        Assert.Equal(["new-done", "old-leased", "old-pending"], (await _db.Store.ListAsync()).Select(j => j.DedupeKey).Order(StringComparer.Ordinal));
        Assert.Equal(1, _db.Count("SELECT count(*) FROM activity_events"));
    }

    [Fact]
    public async Task Activity_retention_of_zero_keeps_everything()
    {
        _db.Execute("UPDATE suite_settings SET activity_retention_days = 0");
        _db.Execute("INSERT INTO activity_events (created_at, event_type, module, title) VALUES ('2000-01-01 00:00:00', 'x', 'processing', 'old')");

        Assert.Equal(0, (await JobRowsRetention.RunTickAsync(_db.Store, 90, DateTimeOffset.UtcNow)).Activity);
    }

    [Fact]
    public async Task Periodic_enqueue_skips_families_this_server_cannot_run()
    {
        var enqueuer = new WorkTempStaleSweepEnqueuer(_db.Store, "movie", TimeSpan.FromMilliseconds(50), killSwitch: false);
        var service = new PeriodicEnqueueService([enqueuer], JobHandlerRegistry.Empty, TimeProvider.System, NullLogger<PeriodicEnqueueService>.Instance);

        await service.StartAsync(CancellationToken.None);
        await Task.Delay(300);
        await service.StopAsync(CancellationToken.None);

        Assert.Equal(0, _db.Count("SELECT count(*) FROM jobs"));
    }

    [Fact]
    public async Task Periodic_work_temp_sweep_enqueue_keeps_one_row_per_scope()
    {
        var registry = new JobHandlerRegistry([new DelegateHandler(PeriodicJobKinds.WorkTempStaleSweep, _ => { })]);
        IPeriodicEnqueuer[] enqueuers =
        [
            new WorkTempStaleSweepEnqueuer(_db.Store, "movie", TimeSpan.FromMilliseconds(20), killSwitch: false),
            new WorkTempStaleSweepEnqueuer(_db.Store, "TV", TimeSpan.FromMilliseconds(20), killSwitch: false),
        ];
        var service = new PeriodicEnqueueService(enqueuers, registry, TimeProvider.System, NullLogger<PeriodicEnqueueService>.Instance);

        await service.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => Task.FromResult(_db.Count("SELECT count(*) FROM jobs") == 2));
        await Task.Delay(150);
        await service.StopAsync(CancellationToken.None);

        var rows = (await _db.Store.ListAsync()).OrderBy(j => j.DedupeKey, StringComparer.Ordinal).ToList();
        Assert.Equal(
            [("processing.work_temp_stale_sweep:v1:movie", "{\"media_scope\":\"movie\",\"trigger\":\"scheduled\"}"),
             ("processing.work_temp_stale_sweep:v1:tv", "{\"media_scope\":\"tv\",\"trigger\":\"scheduled\"}")],
            rows.Select(r => (r.DedupeKey, r.PayloadJson!)));
    }

    [Fact]
    public async Task Periodic_families_honour_their_saved_switch_and_the_environment_kill_switch()
    {
        var sweep = new WorkTempStaleSweepEnqueuer(_db.Store, "movie", TimeSpan.FromMinutes(1), killSwitch: false);
        var killed = new WorkTempStaleSweepEnqueuer(_db.Store, "movie", TimeSpan.FromMinutes(1), killSwitch: true);
        var cleanup = new FailureCleanupSweepEnqueuer(_db.Store, "movie", TimeSpan.FromMinutes(1), killSwitch: false);

        Assert.True(await sweep.IsEnabledAsync(CancellationToken.None));
        Assert.False(await killed.IsEnabledAsync(CancellationToken.None));
        Assert.False(await cleanup.IsEnabledAsync(CancellationToken.None));
        _db.Execute("UPDATE operator_settings SET failure_cleanup_enabled = 1, work_temp_stale_sweep_enabled = 0");
        Assert.True(await cleanup.IsEnabledAsync(CancellationToken.None));
        Assert.False(await sweep.IsEnabledAsync(CancellationToken.None));
    }

    [Fact]
    public async Task A_failure_cleanup_sweep_still_queued_is_not_duplicated_and_says_so()
    {
        var enqueuer = new FailureCleanupSweepEnqueuer(_db.Store, "tv", TimeSpan.FromMinutes(1), killSwitch: false);

        await enqueuer.EnqueueOnceAsync(CancellationToken.None);
        await enqueuer.EnqueueOnceAsync(CancellationToken.None);

        var job = Assert.Single(await _db.Store.ListAsync());
        Assert.Equal(PeriodicJobKinds.TvFailureCleanupSweep, job.JobKind);
        Assert.Matches("^processing\\.tv_failure_cleanup_sweep:v1:[0-9a-f]{32}$", job.DedupeKey);
        Assert.Equal("{\"media_scope\":\"tv\",\"trigger\":\"scheduled\"}", job.PayloadJson);
        var entry = Assert.Single(_db.ActivityEvents());
        Assert.Equal(ActivityEventTypes.ProcessingFailureCleanupSweepCompleted, entry.EventType);
        Assert.Equal("Cleanup skipped for TV", entry.Title);
        Assert.Equal(
            $"{{\"media_scope\":\"tv\",\"cleanup_run_status\":\"skipped\",\"reason\":\"Previous cleanup job is still queued or running.\",\"existing_job_id\":{job.Id},\"result\":\"skipped\",\"trigger\":\"scheduled\"}}",
            entry.Detail);
        Assert.Equal("skipped", entry.Result);
    }

    [Fact]
    public async Task A_failing_periodic_enqueue_retries_after_its_cooldown()
    {
        var registry = new JobHandlerRegistry([new DelegateHandler("processing.flaky.v1", _ => { })]);
        var flaky = new FlakyEnqueuer();
        var service = new PeriodicEnqueueService([flaky], registry, TimeProvider.System, NullLogger<PeriodicEnqueueService>.Instance);

        await service.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => Task.FromResult(flaky.Calls >= 2), TimeSpan.FromSeconds(10));
        await service.StopAsync(CancellationToken.None);

        Assert.True(flaky.Calls >= 2);
    }

    [Fact]
    public async Task The_activity_writer_fills_the_classified_columns()
    {
        var writer = new SqliteActivityWriter(_db.Database);

        var id = await writer.RecordAsync(new ActivityEventDraft("processing.worker_failure", "processing", "t", "{\"result\":\"failed\",\"library_id\":2,\"relative_media_path\":\"x.mkv\",\"trigger\":\"retry\",\"run_id\":\"a\"}"));

        Assert.True(id > 0);
        Assert.Equal(1, _db.Count(
            "SELECT count(*) FROM activity_events WHERE id = @id AND result = 'failed' AND library_id = 2 AND relative_path = 'x.mkv' AND \"trigger\" = 'retry' AND run_key = 'run:a' AND created_at IS NOT NULL",
            ("@id", id)));
    }

    private ProcessingWorkerService WorkerService(IEnumerable<IJobHandler> handlers, WorkerHeartbeats heartbeats, int workerCount)
    {
        var options = Weir.Core.Configuration.WeirOptionsLoader.Load(new Weir.Core.Configuration.RuntimeEnvironment(
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["WEIR_HOME"] = _db.Home,
                ["WEIR_PROCESSING_WORKER_COUNT"] = workerCount.ToString(System.Globalization.CultureInfo.InvariantCulture),
            },
            OperatingSystem.IsWindows(),
            _db.Home,
            _db.Home));
        var timings = new WorkerLoopTimings { IdleSleep = TimeSpan.FromMilliseconds(50), TickErrorBackoff = TimeSpan.FromMilliseconds(50), ConcurrencyCacheTtl = TimeSpan.FromMilliseconds(100), LeaseSeconds = 3600 };
        var processor = new ProcessingJobProcessor(
            _db.Store,
            new JobHandlerRegistry(handlers),
            new SqliteActivityWriter(_db.Database),
            new NoUnhandledJobFailureRecorder(),
            new NoJobNotifications(),
            TimeProvider.System,
            NullLogger<ProcessingJobProcessor>.Instance);
        return new ProcessingWorkerService(processor, _db.Store, heartbeats, options, timings, TimeProvider.System, NullLogger<ProcessingWorkerService>.Instance);
    }

    private static async Task WaitUntilAsync(Func<Task<bool>> condition, TimeSpan? timeout = null)
    {
        var deadline = DateTime.UtcNow + (timeout ?? TimeSpan.FromSeconds(15));
        while (!await condition())
        {
            if (DateTime.UtcNow > deadline)
            {
                Assert.Fail("condition was not met in time");
            }

            await Task.Delay(20);
        }
    }

    private sealed class FlakyEnqueuer : IPeriodicEnqueuer
    {
        private int _calls;

        public int Calls => Volatile.Read(ref _calls);

        public string Name => "flaky";

        public string JobKind => "processing.flaky.v1";

        public TimeSpan Interval => TimeSpan.FromHours(1);

        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken) => Task.FromResult(true);

        public Task EnqueueOnceAsync(CancellationToken cancellationToken) =>
            Interlocked.Increment(ref _calls) == 1 ? throw new InvalidOperationException("first tick fails") : Task.CompletedTask;
    }
}
