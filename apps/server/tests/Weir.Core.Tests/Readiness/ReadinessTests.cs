using Weir.Core.Readiness;
using Weir.Core.Workers;

namespace Weir.Core.Tests.Readiness;

public sealed class ReadinessTests
{
    private static readonly KeyValuePair<string, int>[] EightProcessingWorkers = [new("processing", 8)];

    [Fact]
    public void Workers_that_never_started_read_as_degraded()
    {
        var lanes = new WorkerHeartbeats(new ManualTimeProvider()).Snapshot(EightProcessingWorkers);
        var lane = Assert.Single(lanes);
        Assert.Equal(
            new WorkerLaneHealth(
                "processing", 8, 0, 8, 0, "degraded",
                "Weir is not processing new work because 8 worker slots stopped responding. Restart Weir; queued work remains safe."),
            lane);
    }

    [Fact]
    public void Zero_expected_workers_read_as_disabled()
    {
        var lane = Assert.Single(new WorkerHeartbeats(new ManualTimeProvider()).Snapshot([new("processing", 0)]));
        Assert.Equal(
            new WorkerLaneHealth("processing", 0, 0, 0, 0, "disabled", "Weir is turned off in Settings, so no new background work will run."),
            lane);
    }

    [Fact]
    public void Heartbeats_are_healthy_until_stale_and_stopped_workers_count_separately()
    {
        var time = new ManualTimeProvider();
        var heartbeats = new WorkerHeartbeats(time);
        heartbeats.Started("processing", 0);
        heartbeats.Started("processing", 1);
        heartbeats.Started("processing", 5); // outside the expected slots, ignored

        Assert.Equal(
            new WorkerLaneHealth("processing", 2, 2, 0, 0, "healthy", "Weir worker heartbeats are current."),
            Assert.Single(heartbeats.Snapshot([new("processing", 2)])));

        time.Advance(TimeSpan.FromSeconds(361));
        heartbeats.Beat("processing", 0);
        var stale = Assert.Single(heartbeats.Snapshot([new("processing", 2)]));
        Assert.Equal((1, 1, 0, "degraded"), (stale.ActiveWorkers, stale.StaleWorkers, stale.StoppedWorkers, stale.Status));

        heartbeats.Stopped("processing", 1);
        var stopped = Assert.Single(heartbeats.Snapshot([new("processing", 2)]));
        Assert.Equal((1, 0, 1, "degraded"), (stopped.ActiveWorkers, stopped.StaleWorkers, stopped.StoppedWorkers, stopped.Status));
        Assert.Contains("because 1 worker slot stopped responding.", stopped.Detail, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("processing", "Processing")]
    [InlineData("media_managers", "Media_Managers")]
    [InlineData("PROCESSING", "Processing")]
    public void Module_titles_follow_python_title(string module, string expected) =>
        Assert.Equal(expected, WorkerHeartbeats.TitleCase(module));

    [Fact]
    public void Ready_when_database_workers_and_watcher_are_ready()
    {
        var report = ReadinessBuilder.Build(
            new ReadinessInputs(TimeSpan.FromMilliseconds(1234.5678), true, true, [Healthy()], ReadinessBuilder.NoWatchedLibraries),
            "2.6.6");
        Assert.True(report.Ready);
        Assert.Equal("ready", report.Status);
        Assert.Equal("2.6.6", report.Version);
        Assert.Equal(1.235, report.StartupSeconds);
        Assert.Equal(
            [
                new ReadinessStep("database", "ready", "Local database is connected and migrations are complete."),
                new ReadinessStep("workers", "ready", "Background workers and schedules are ready."),
                new ReadinessStep("filesystem_watcher", "ready", "No libraries are being watched for filesystem events."),
            ],
            report.Steps);
    }

    [Fact]
    public void Failed_after_startup_when_workers_are_degraded()
    {
        var workers = new WorkerHeartbeats(new ManualTimeProvider()).Snapshot(EightProcessingWorkers);
        var report = ReadinessBuilder.Build(new ReadinessInputs(TimeSpan.Zero, true, true, workers, ReadinessBuilder.NoWatchedLibraries), "1.0.0");
        Assert.False(report.Ready);
        Assert.Equal("failed", report.Status);
        Assert.Equal(new ReadinessStep("workers", "failed", "One or more background workers are stale or stopped."), report.Steps[1]);
        Assert.Equal(workers, report.WorkerHealth);
    }

    [Fact]
    public void Starting_before_startup_completes()
    {
        var report = ReadinessBuilder.Build(new ReadinessInputs(TimeSpan.FromSeconds(-1), false, false, null, ReadinessBuilder.NoWatchedLibraries), "1.0.0");
        Assert.False(report.Ready);
        Assert.Equal("starting", report.Status);
        Assert.Equal(0.0, report.StartupSeconds);
        Assert.Equal(new ReadinessStep("database", "starting", "Weir is preparing the local database."), report.Steps[0]);
        Assert.Equal(new ReadinessStep("workers", "starting", "Weir is starting background workers and schedules."), report.Steps[1]);
        Assert.Empty(report.WorkerHealth);
    }

    [Fact]
    public void Database_failure_after_startup_and_watcher_failure()
    {
        var report = ReadinessBuilder.Build(new ReadinessInputs(TimeSpan.Zero, false, true, null, (false, "watcher broke")), "1.0.0");
        Assert.Equal("failed", report.Status);
        Assert.Equal(new ReadinessStep("database", "failed", "Weir could not verify the local database connection."), report.Steps[0]);
        Assert.Equal(new ReadinessStep("workers", "ready", "Background workers and schedules are ready."), report.Steps[1]);
        Assert.Equal(new ReadinessStep("filesystem_watcher", "failed", "watcher broke"), report.Steps[2]);
    }

    [Fact]
    public void Health_reports_the_database_dependency()
    {
        Assert.Equal("ok", HealthReport.FromDatabase(true).Status);
        Assert.Equal("ok", HealthReport.FromDatabase(true).Dependencies["database"]);
        Assert.Equal("unhealthy", HealthReport.FromDatabase(false).Status);
        Assert.Equal("failed", HealthReport.FromDatabase(false).Dependencies["database"]);
        Assert.False(HealthReport.FromDatabase(false).IsOk);
    }

    private static WorkerLaneHealth Healthy() => new("processing", 1, 1, 0, 0, "healthy", "Weir worker heartbeats are current.");
}
