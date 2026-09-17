using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Security;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.MediaManagers;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Real-temp-dir, real-SQLite port of the key assertions in
/// <c>test_refiner_watched_folder_remux_scan_dispatch_lane.py</c>: the handler enqueues
/// <c>refiner.file.remux_pass.v1</c> with Python's exact payload shape, honours
/// <c>enqueue_remux_jobs</c>, skips a relative path already covered by an active pass, and applies a
/// library's rejected-file cleanup policy.
/// </summary>
public sealed class RefinerWatchedFolderScanDispatchJobHandlerTests
{
    private static async Task<(StoreFixture Store, RefinerJobStore Jobs, RefinerWatchedFolderScanDispatchJobHandler Handler)> BuildAsync()
    {
        var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "handler-tests-credentials-secret"));
        var cipher = new CredentialCipher(store.Options.CredentialsSecret, store.Options.SessionSecret, store.Options.PreviousCredentialsSecrets, store.Clock);
        var ports = new HttpMediaManagerPorts(new FakeManagerHttp());
        var connections = new MediaManagerConnectionService(store.Options, cipher, ports);
        var jobs = new RefinerJobStore(store.Database, store.Clock);
        var handler = new RefinerWatchedFolderScanDispatchJobHandler(store.Database, store.Clock, store.Options, jobs, connections);
        // Match the Python fixture: zero out the operator-wide minimum age/size so these tests assert scan
        // dispatch itself, not the settling/hold-timer gates a freshly written test file would otherwise trip.
        await store.Execute(
            "INSERT INTO refiner_operator_settings (id, min_file_age_seconds, refiner_min_input_file_size_mb, minimum_free_disk_space_mb) " +
            "VALUES (1, 0, 0, 0) ON CONFLICT(id) DO UPDATE SET min_file_age_seconds = 0, refiner_min_input_file_size_mb = 0, minimum_free_disk_space_mb = 0");
        return (store, jobs, handler);
    }

    private static async Task<long> CreateLibraryAsync(
        StoreFixture store, string watched, string output, bool enqueuePeriodicRemux = true, long minFileAgeSeconds = 0, long fileDetectionIntervalSeconds = 0,
        string rejectedFileAction = "leave", string excludePatternsCsv = "")
    {
        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var created = await LibraryStore.CreateAsync(uow, new RefinerLibraryInput
        {
            Name = "Movies " + Guid.NewGuid().ToString("N")[..8],
            MediaType = RefinerMediaScopes.Movie,
            WatchedFolder = watched,
            OutputFolder = output,
            MinFileAgeSeconds = minFileAgeSeconds,
            FileDetectionIntervalSeconds = fileDetectionIntervalSeconds,
            RejectedFileAction = rejectedFileAction,
            ExcludePatternsCsv = excludePatternsCsv,
        });
        await uow.CommitAsync();
        return created.Id;
    }

    private static async Task RunScanAsync(RefinerWatchedFolderScanDispatchJobHandler handler, RefinerJobStore jobs, long libraryId, bool enqueueRemuxJobs)
    {
        var payload = new PyDict().Set("enqueue_remux_jobs", enqueueRemuxJobs).Set("scan_trigger", "manual").Set("media_scope", "movie").Set("library_id", libraryId);
        var job = await jobs.EnqueueOrGetAsync(
            $"scan-test-{Guid.NewGuid():N}",
            RefinerWatchedFolderScanDispatchJobKinds.ScanDispatch,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));
        await handler.HandleAsync(new JobWorkContext(job.Id, job.JobKind, job.PayloadJson, "test-owner"), CancellationToken.None);
    }

    [Fact]
    public async Task The_handler_enqueues_a_remux_pass_job_with_pythons_exact_payload_shape()
    {
        var (store, jobs, handler) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        var mkv = Path.Combine(watched, "Gate Test 2001.mkv");
        File.WriteAllBytes(mkv, [1]);

        var libraryId = await CreateLibraryAsync(store, watched, output);
        await RunScanAsync(handler, jobs, libraryId, enqueueRemuxJobs: true);

        var remuxJobs = store.Database.Open();
        using var command = remuxJobs.CreateCommand();
        command.CommandText = "SELECT dedupe_key, status, payload_json FROM refiner_jobs WHERE job_kind = 'refiner.file.remux_pass.v1'";
        using var reader = command.ExecuteReader();
        Assert.True(reader.Read());
        var dedupeKey = reader.GetString(0);
        var status = reader.GetString(1);
        var payloadJson = reader.GetString(2);
        Assert.False(reader.Read());

        Assert.StartsWith("refiner.file.remux_pass.v1:scan:", dedupeKey, StringComparison.Ordinal);
        Assert.Equal("pending", status);
        var body = (PyDict)PyJsonParser.Parse(payloadJson);
        Assert.Equal("Gate Test 2001.mkv", ((PyStr)body.Get("relative_media_path")!).Value);
        Assert.Equal("movie", ((PyStr)body.Get("media_scope")!).Value);
        Assert.Equal("manual", ((PyStr)body.Get("trigger")!).Value);
        Assert.Equal(libraryId, (long)((PyInt)body.Get("library_id")!).Value);
        Assert.Null(body.Get("dry_run"));
    }

    [Fact]
    public async Task Enqueue_remux_jobs_false_records_file_state_but_queues_nothing()
    {
        var (store, jobs, handler) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        File.WriteAllBytes(Path.Combine(watched, "Check Only 2001.mkv"), [1]);

        var libraryId = await CreateLibraryAsync(store, watched, output);
        await RunScanAsync(handler, jobs, libraryId, enqueueRemuxJobs: false);

        var remuxCount = await store.Scalar("SELECT COUNT(*) FROM refiner_jobs WHERE job_kind = 'refiner.file.remux_pass.v1'");
        Assert.Equal(0, remuxCount);

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.FindAsync(uow, libraryId, "Check Only 2001.mkv");
        Assert.NotNull(file);
        Assert.Equal(RefinerFileStatuses.Unprocessed, file!.Status);
    }

    [Fact]
    public async Task A_relative_path_already_covered_by_an_active_pass_is_not_enqueued_twice()
    {
        var (store, jobs, handler) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        File.WriteAllBytes(Path.Combine(watched, "Already Queued 2001.mkv"), [1]);
        var libraryId = await CreateLibraryAsync(store, watched, output);

        var existingPayload = new PyDict().Set("relative_media_path", "Already Queued 2001.mkv").Set("media_scope", "movie").Set("library_id", libraryId);
        await jobs.EnqueueOrGetAsync("existing-remux", "refiner.file.remux_pass.v1", PyJsonWriter.Dumps(existingPayload, PyJsonFormat.Compact));

        await RunScanAsync(handler, jobs, libraryId, enqueueRemuxJobs: true);

        var remuxCount = await store.Scalar("SELECT COUNT(*) FROM refiner_jobs WHERE job_kind = 'refiner.file.remux_pass.v1'");
        Assert.Equal(1, remuxCount);
    }

    [Fact]
    public async Task A_file_matching_the_library_exclude_pattern_under_delete_file_is_removed_and_recorded_skipped()
    {
        var (store, jobs, handler) = await BuildAsync();
        using var _ = store;
        var watched = store.Home.Join("watch");
        var output = store.Home.Join("out");
        Directory.CreateDirectory(watched);
        Directory.CreateDirectory(output);
        var sampleFolder = Path.Combine(watched, "Bad Release");
        Directory.CreateDirectory(sampleFolder);
        var sample = Path.Combine(sampleFolder, "sample.mkv");
        File.WriteAllBytes(sample, [1]);

        var libraryId = await CreateLibraryAsync(store, watched, output, rejectedFileAction: "delete_file", excludePatternsCsv: "*sample*");
        await RunScanAsync(handler, jobs, libraryId, enqueueRemuxJobs: true);

        Assert.False(File.Exists(sample));
        var remuxCount = await store.Scalar("SELECT COUNT(*) FROM refiner_jobs WHERE job_kind = 'refiner.file.remux_pass.v1'");
        Assert.Equal(0, remuxCount);

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.FindAsync(uow, libraryId, "Bad Release/sample.mkv");
        Assert.NotNull(file);
        Assert.Equal(RefinerFileStatuses.Skipped, file!.Status);
    }
}
