using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Processing;
using Weir.Core.Security;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.MediaManagers;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Closes #522's per-file manager queue attribution gap: a linked manager's live queue must block/hold a
/// watched-folder file it still reports downloading or importing, exactly like Python's
/// <c>evaluate_watched_media_file_for_dispatch</c> (port of the manager-signal parts of
/// <c>test_processing_watched_folder_remux_scan_dispatch_evaluate.py</c> and
/// <c>test_processing_watched_folder_remux_scan_dispatch_lane.py</c>), driven through
/// <see cref="ProcessingWatchedFolderScanDispatchJobHandler"/> with a fake Radarr behind
/// <see cref="FakeManagerHttp"/> rather than a hand-built signal.
/// </summary>
public sealed class ProcessingWatchedFolderScanDispatchManagerQueueSignalTests
{
    private static async Task<(StoreFixture Store, ProcessingJobStore Jobs, ProcessingWatchedFolderScanDispatchJobHandler Handler, FakeManagerHttp Http, MediaManagerConnectionService Connections)> BuildAsync()
    {
        var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "queue-signal-tests-credentials-secret"));
        var cipher = new CredentialCipher(store.Options.CredentialsSecret, store.Options.SessionSecret, store.Options.PreviousCredentialsSecrets, store.Clock);
        var http = new FakeManagerHttp();
        var ports = new HttpMediaManagerPorts(http);
        var connections = new MediaManagerConnectionService(store.Options, cipher, ports);
        var jobs = new ProcessingJobStore(store.Database, store.Clock);
        var handler = new ProcessingWatchedFolderScanDispatchJobHandler(store.Database, store.Clock, store.Options, jobs, connections);
        await store.Execute(
            "INSERT INTO operator_settings (id, min_file_age_seconds, min_input_file_size_mb, minimum_free_disk_space_mb) " +
            "VALUES (1, 0, 0, 0) ON CONFLICT(id) DO UPDATE SET min_file_age_seconds = 0, min_input_file_size_mb = 0, minimum_free_disk_space_mb = 0");
        return (store, jobs, handler, http, connections);
    }

    private static async Task<long> CreateLibraryAsync(StoreFixture store, string watched, string output, IReadOnlyList<long> managerConnectionIds)
    {
        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var created = await LibraryStore.CreateAsync(uow, new ProcessingLibraryInput
        {
            Name = "Movies " + Guid.NewGuid().ToString("N")[..8],
            MediaType = ProcessingMediaScopes.Movie,
            WatchedFolder = watched,
            OutputFolder = output,
            MinFileAgeSeconds = 0,
            FileDetectionIntervalSeconds = 0,
            ManagerConnectionIds = managerConnectionIds,
        });
        await uow.CommitAsync();
        return created.Id;
    }

    private static async Task RunScanAsync(ProcessingWatchedFolderScanDispatchJobHandler handler, ProcessingJobStore jobs, long libraryId)
    {
        var payload = new PyDict().Set("enqueue_remux_jobs", true).Set("scan_trigger", "manual").Set("media_scope", "movie").Set("library_id", libraryId);
        var job = await jobs.EnqueueOrGetAsync(
            $"scan-test-{Guid.NewGuid():N}",
            ProcessingWatchedFolderScanDispatchJobKinds.ScanDispatch,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));
        await handler.HandleAsync(new JobWorkContext(job.Id, job.JobKind, job.PayloadJson, "test-owner"), CancellationToken.None);
    }

    private static void RouteQueue(FakeManagerHttp http, string recordsJson) =>
        http.Json(HttpMethod.Get, "/api/v3/queue", $$"""{"records":{{recordsJson}}}""");

    [Fact]
    public async Task A_file_a_linked_manager_still_reports_downloading_is_not_enqueued()
    {
        var (store, jobs, handler, http, connections) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        var mkv = Path.Combine(watched, "Held By Radarr 2001.mkv");
        File.WriteAllBytes(mkv, [1]);

        var connectionId = await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "radarr", "Main", "http://radarr.local", "key"));
        var outputPathJson = mkv.Replace("\\", "\\\\", StringComparison.Ordinal);
        RouteQueue(http, "[{\"status\":\"downloading\",\"outputPath\":\"" + outputPathJson + "\",\"movie\":{\"title\":\"Held By Radarr\",\"year\":2001}}]");

        var libraryId = await CreateLibraryAsync(store, watched, output, [connectionId]);
        await RunScanAsync(handler, jobs, libraryId);

        var remuxCount = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.file.remux_pass.v1'");
        Assert.Equal(0, remuxCount);

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.FindAsync(uow, libraryId, "Held By Radarr 2001.mkv");
        Assert.NotNull(file);
        Assert.Equal(ProcessingFileStatuses.BlockedUpstream, file!.Status);
        Assert.Equal("Radarr (Main)", file.BlockedByConnection);
        Assert.Contains("Radarr (Main) is still importing this file", file.StatusReason, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_file_the_linked_manager_does_not_list_is_still_processed()
    {
        var (store, jobs, handler, http, connections) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        File.WriteAllBytes(Path.Combine(watched, "Clear 2002.mkv"), [1]);

        var connectionId = await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "radarr", "Main", "http://radarr.local", "key"));
        RouteQueue(http, "[]");

        var libraryId = await CreateLibraryAsync(store, watched, output, [connectionId]);
        await RunScanAsync(handler, jobs, libraryId);

        var remuxCount = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.file.remux_pass.v1'");
        Assert.Equal(1, remuxCount);
    }

    [Fact]
    public async Task A_manager_holding_an_unrelated_file_does_not_block_this_one()
    {
        var (store, jobs, handler, http, connections) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        File.WriteAllBytes(Path.Combine(watched, "Unrelated 2003.mkv"), [1]);

        var connectionId = await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "radarr", "Main", "http://radarr.local", "key"));
        RouteQueue(http, """[{"status":"downloading","outputPath":"D:\\Other\\Somewhere Else 1999.mkv","movie":{"title":"Somewhere Else","year":1999}}]""");

        var libraryId = await CreateLibraryAsync(store, watched, output, [connectionId]);
        await RunScanAsync(handler, jobs, libraryId);

        var remuxCount = await store.Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.file.remux_pass.v1'");
        Assert.Equal(1, remuxCount);
    }
}
