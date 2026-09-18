using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Processing;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Proof of the #533 fix: the periodic watched-folder scheduler must honour the per-scope
/// <c>movie_schedule_enabled</c>/<c>tv_schedule_enabled</c> switch — the one an operator actually sees and
/// toggles — and never schedule a periodic scan for a scope while it is off, over a short interval; a
/// manual scan is unaffected because it never calls into this scheduler at all.
/// </summary>
public sealed class ProcessingWatchedFolderScanDispatchScheduleTaskTests
{
    /// <summary><c>StoreFixture</c> runs the real migrations, which seed a Movies/TV library each
    /// (ADR-0014) — point the seeded Movies library at these folders rather than creating a second one.</summary>
    private static async Task<long> CreateLibraryAsync(StoreFixture store, string watched, string output, long scanIntervalSeconds = 10)
    {
        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var seeded = await LibraryStore.SeededForScopeAsync(uow, ProcessingMediaScopes.Movie) ?? throw new InvalidOperationException("No seeded Movies library.");
        var updated = await LibraryStore.UpdateAsync(uow, seeded, new ProcessingLibraryInput
        {
            Name = seeded.Name,
            MediaType = ProcessingMediaScopes.Movie,
            WatchedFolder = watched,
            OutputFolder = output,
            ScanIntervalSeconds = scanIntervalSeconds,
        });
        await uow.CommitAsync();
        return updated.Id;
    }

    private static async Task SetMovieScheduleEnabledAsync(StoreFixture store, bool enabled)
    {
        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var row = await OperatorSettingsStore.EnsureAsync(uow);
        await OperatorSettingsStore.UpdateAsync(uow, row, row with { MovieScheduleEnabled = enabled });
        await uow.CommitAsync();
    }

    [Fact]
    public async Task With_the_global_env_kill_switch_off_no_periodic_scan_is_ever_enqueued_even_though_everything_else_is_ready()
    {
        // The scope switch and the library are both left ready (enabled=true is the default for both):
        // only WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED stands in the way.
        using var store = new StoreFixture(
            ("WEIR_CREDENTIALS_SECRET", "schedule-task-tests-secret-kill"),
            ("WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED", "0"));
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        await CreateLibraryAsync(store, watched, output, scanIntervalSeconds: 10);

        var jobStore = new ProcessingJobStore(store.Database, store.Clock);
        var task = new ProcessingWatchedFolderScanDispatchScheduleTask(store.Database, store.Options, jobStore, store.Clock, NullLogger<ProcessingWatchedFolderScanDispatchScheduleTask>.Instance);

        for (var i = 0; i < 5; i++)
        {
            await task.RunOnceAsync(CancellationToken.None);
            store.Clock.Set(store.Clock.GetUtcNow() + TimeSpan.FromSeconds(15));
        }

        var count = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.watched_folder.remux_scan_dispatch.v1'");
        Assert.Equal(0, count);
    }

    [Fact]
    public async Task With_the_scope_schedule_switch_off_no_periodic_scan_is_ever_enqueued()
    {
        using var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "schedule-task-tests-secret"));
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        await CreateLibraryAsync(store, watched, output, scanIntervalSeconds: 10);
        await SetMovieScheduleEnabledAsync(store, enabled: false);

        var jobStore = new ProcessingJobStore(store.Database, store.Clock);
        var task = new ProcessingWatchedFolderScanDispatchScheduleTask(store.Database, store.Options, jobStore, store.Clock, NullLogger<ProcessingWatchedFolderScanDispatchScheduleTask>.Instance);

        // Several ticks spanning well past the library's 10s scan interval: still nothing queued.
        for (var i = 0; i < 5; i++)
        {
            await task.RunOnceAsync(CancellationToken.None);
            store.Clock.Set(store.Clock.GetUtcNow() + TimeSpan.FromSeconds(15));
        }

        var count = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.watched_folder.remux_scan_dispatch.v1'");
        Assert.Equal(0, count);
    }

    [Fact]
    public async Task With_the_scope_schedule_switch_on_a_periodic_scan_is_enqueued_on_the_librarys_own_interval()
    {
        using var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "schedule-task-tests-secret-2"));
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        await CreateLibraryAsync(store, watched, output, scanIntervalSeconds: 10);
        await SetMovieScheduleEnabledAsync(store, enabled: true);

        var jobStore = new ProcessingJobStore(store.Database, store.Clock);
        var task = new ProcessingWatchedFolderScanDispatchScheduleTask(store.Database, store.Options, jobStore, store.Clock, NullLogger<ProcessingWatchedFolderScanDispatchScheduleTask>.Instance);

        await task.RunOnceAsync(CancellationToken.None);

        var count = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.watched_folder.remux_scan_dispatch.v1'");
        Assert.Equal(1, count);
    }

    [Fact]
    public async Task A_disabled_library_is_never_scheduled_regardless_of_the_scope_switch()
    {
        using var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "schedule-task-tests-secret-3"));
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        var libraryId = await CreateLibraryAsync(store, watched, output);
        await using (var uow = await UnitOfWork.OpenAsync(store.Database))
        {
            var library = await LibraryStore.GetAsync(uow, libraryId) ?? throw new InvalidOperationException();
            await LibraryStore.UpdateAsync(uow, library, new ProcessingLibraryInput { Name = library.Name, MediaType = library.MediaType, WatchedFolder = watched, OutputFolder = output, Enabled = false });
            await uow.CommitAsync();
        }

        await SetMovieScheduleEnabledAsync(store, enabled: true);

        var jobStore = new ProcessingJobStore(store.Database, store.Clock);
        var task = new ProcessingWatchedFolderScanDispatchScheduleTask(store.Database, store.Options, jobStore, store.Clock, NullLogger<ProcessingWatchedFolderScanDispatchScheduleTask>.Instance);
        await task.RunOnceAsync(CancellationToken.None);

        var count = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.watched_folder.remux_scan_dispatch.v1'");
        Assert.Equal(0, count);
    }

    [Fact]
    public async Task Manual_enqueue_works_even_while_the_scope_schedule_switch_is_off()
    {
        using var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "schedule-task-tests-secret-4"));
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        var libraryId = await CreateLibraryAsync(store, watched, output);
        await SetMovieScheduleEnabledAsync(store, enabled: false);

        var jobStore = new ProcessingJobStore(store.Database, store.Clock);
        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var job = await ProcessingWatchedFolderScanDispatchEnqueue.EnqueueScanDispatchJobAsync(uow, jobStore, enqueueRemuxJobs: true, "manual", "movie", libraryId);
        await uow.CommitAsync();

        Assert.Equal(ProcessingWatchedFolderScanDispatchJobKinds.ScanDispatch, job.JobKind);
        var count = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.watched_folder.remux_scan_dispatch.v1'");
        Assert.Equal(1, count);
    }
}
