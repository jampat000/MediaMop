using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Json;
using Weir.Core.Security;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Processing.RemuxPass;
using Weir.Infrastructure.Tests.MediaManagers;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Processing.RemuxPass;

/// <summary>
/// Ported from <c>apps/backend/tests/test_processing_tv_season_folder_cleanup.py</c>: the manager-signal, active-job,
/// output-completeness and minimum-age gates a whole-season deletion must pass, driven through
/// <see cref="TvSeasonFolderCleanup"/> with a fake Sonarr behind <see cref="FakeManagerHttp"/> — reuses
/// <see cref="PassFolders"/> from <c>RemuxPassRunnerTests</c> for the folder tree.
/// </summary>
public sealed class TvSeasonFolderCleanupTests : IDisposable
{
    private readonly PassFolders _folders = new();

    public void Dispose() => _folders.Dispose();

    private static string Str(PyDict output, string key) => PyConvert.Str(output[key]);

    private static bool Bool(PyDict output, string key) => ((PyBool)output[key]!).Value;

    private static async Task<(StoreFixture Store, TvSeasonFolderCleanup Cleanup, FakeManagerHttp Http, MediaManagerConnectionService Connections, ProcessingJobStore Jobs)> BuildAsync()
    {
        var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "tv-season-cleanup-tests-credentials-secret"));
        store.Clock.Set(DateTimeOffset.UtcNow);
        var cipher = new CredentialCipher(store.Options.CredentialsSecret, store.Options.SessionSecret, store.Options.PreviousCredentialsSecrets, store.Clock);
        var http = new FakeManagerHttp();
        var ports = new HttpMediaManagerPorts(http);
        var connections = new MediaManagerConnectionService(store.Options, cipher, ports);
        var cleanup = new TvSeasonFolderCleanup(store.Database, connections, store.Clock, NullLogger<TvSeasonFolderCleanup>.Instance);
        var jobs = new ProcessingJobStore(store.Database, store.Clock);
        return (store, cleanup, http, connections, jobs);
    }

    private static void RouteSonarrQueue(FakeManagerHttp http, string recordsJson) =>
        http.Json(HttpMethod.Get, "/api/v3/queue", "{\"records\":" + recordsJson + "}");

    private static PyDict LiveOkContext(string relativeMediaPath) => new PyDict()
        .Set("ok", true)
        .Set("dry_run", false)
        .Set("outcome", "live_skipped_not_required")
        .Set("relative_media_path", relativeMediaPath);

    private Task<PyDict> RunAsync(
        TvSeasonFolderCleanup cleanup, string source, long minFileAgeSeconds = 0, long? currentJobId = null, PyDict? remuxContext = null, string? finalOutputFile = null)
    {
        var output = new PyDict();
        var context = new TvSeasonCleanupContext(
            output, _folders.Runtime(), source, _folders.Watched, minFileAgeSeconds, currentJobId, remuxContext ?? new PyDict(), finalOutputFile);
        return cleanup.RunAsync(context, CancellationToken.None).ContinueWith(_ => output, TaskScheduler.Default);
    }

    [Fact]
    public void Episode_set_direct_children_only()
    {
        var season = Path.Join(_folders.Watched, "S01");
        Directory.CreateDirectory(season);
        File.WriteAllBytes(Path.Join(season, "a.mkv"), [1]);
        File.WriteAllBytes(Path.Join(season, "b.mkv"), [1]);
        var subs = Path.Join(season, "Subs");
        Directory.CreateDirectory(subs);
        File.WriteAllBytes(Path.Join(subs, "hidden.mkv"), [1]);

        var got = TvSeasonFolderCleanup.GetTvEpisodeSetMediaFiles(season);
        Assert.Equal(["a.mkv", "b.mkv"], got.Select(Path.GetFileName));
    }

    [Fact]
    public async Task Skips_when_no_manager_is_connected()
    {
        var (store, cleanup, _, _, _) = await BuildAsync();
        using var _1 = store;
        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var output = await RunAsync(cleanup, ep, currentJobId: 99, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.True(Bool(output, "tv_manager_queue_unavailable"));
        Assert.False(Bool(output, "tv_season_folder_deleted"));
        Assert.Contains("No media manager is connected for TV", Str(output, "tv_season_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(Directory.Exists(Path.GetDirectoryName(ep)));
    }

    [Fact]
    public async Task Skips_when_a_manager_is_unreachable()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        http.Throw(HttpMethod.Get, "/api/v3/queue", new HttpRequestException("Connection refused."));

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var output = await RunAsync(cleanup, ep, currentJobId: 99, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.True(Bool(output, "tv_manager_queue_unavailable"));
        Assert.False(Bool(output, "tv_season_folder_deleted"));
        Assert.Contains("Sonarr (Main)", Str(output, "tv_season_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(Directory.Exists(Path.GetDirectoryName(ep)));
    }

    [Fact]
    public async Task Blocked_when_a_manager_still_holds_a_sibling_episode()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        var queued = _folders.Source("Serie/S01/queued.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());
        File.WriteAllBytes(_folders.Out("Serie/S01/queued.mkv"), Enumerable.Repeat((byte)'z', 100).ToArray());

        var queuedJson = queued.Replace("\\", "\\\\", StringComparison.Ordinal);
        RouteSonarrQueue(http, "[{\"status\":\"importpending\",\"outputPath\":\"" + queuedJson + "\"}]");

        var output = await RunAsync(cleanup, ep, currentJobId: 1, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.False(Bool(output, "tv_season_folder_deleted"));
        Assert.Contains("Sonarr", Str(output, "tv_season_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(Directory.Exists(Path.GetDirectoryName(ep)));
    }

    [Fact]
    public async Task Blocked_by_active_other_tv_job_for_the_same_path()
    {
        var (store, cleanup, http, connections, jobs) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var payload = new PyDict().Set("relative_media_path", "Serie/S01/e.mkv").Set("dry_run", false).Set("media_scope", "tv");
        await jobs.EnqueueOrGetAsync("k1", "processing.file.remux_pass.v1", PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));

        var output = await RunAsync(cleanup, ep, currentJobId: 999, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.Contains("queued or running", Str(output, "tv_season_folder_skip_reason"), StringComparison.Ordinal);
        Assert.False(Bool(output, "tv_season_folder_deleted"));
    }

    [Fact]
    public async Task Not_blocked_by_a_movie_scope_job_at_the_same_path_and_deletes_the_season()
    {
        var (store, cleanup, http, connections, jobs) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var payload = new PyDict().Set("relative_media_path", "Serie/S01/e.mkv").Set("dry_run", false).Set("media_scope", "movie");
        await jobs.EnqueueOrGetAsync("km", "processing.file.remux_pass.v1", PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));

        var seasonFolder = Path.GetDirectoryName(ep)!;
        var output = await RunAsync(cleanup, ep, currentJobId: 1, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.True(Bool(output, "tv_season_folder_deleted"));
        Assert.False(Directory.Exists(seasonFolder));
    }

    [Fact]
    public async Task Season_equals_watched_root_is_skipped()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("e.mkv", 400);
        var output = await RunAsync(cleanup, ep, currentJobId: 1, remuxContext: LiveOkContext("e.mkv"), finalOutputFile: _folders.Out("e.mkv"));

        Assert.False(Bool(output, "tv_season_folder_deleted"));
        Assert.Contains("watched folder root", Str(output, "tv_season_folder_skip_reason"), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Check4_blocked_when_a_never_processed_sibling_is_not_old_enough()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        _folders.Source("Serie/S01/new.mkv", 400);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var output = await RunAsync(cleanup, ep, minFileAgeSeconds: 86_400, currentJobId: 1, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.False(Bool(output, "tv_season_folder_deleted"));
        var skip = Str(output, "tv_season_folder_skip_reason").ToLowerInvariant();
        Assert.True(skip.Contains("minimum", StringComparison.Ordinal) || skip.Contains("age", StringComparison.Ordinal));
        Assert.True(Directory.Exists(Path.GetDirectoryName(ep)));
    }

    [Fact]
    public async Task Check4_passes_when_the_never_processed_sibling_is_old_enough()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        var old = _folders.Source("Serie/S01/old.mkv", 400);
        File.SetLastWriteTimeUtc(old, store.Clock.GetUtcNow().AddSeconds(-500_000).UtcDateTime);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var seasonFolder = Path.GetDirectoryName(ep)!;
        var output = await RunAsync(cleanup, ep, minFileAgeSeconds: 60, currentJobId: 1, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.True(Bool(output, "tv_season_folder_deleted"));
        Assert.False(Directory.Exists(seasonFolder));
    }

    [Fact]
    public async Task A_prior_recorded_activity_success_clears_a_never_finished_episode()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var detail = PyJsonWriter.Dumps(
            new PyDict().Set("ok", true).Set("dry_run", false).Set("media_scope", "tv")
                .Set("relative_media_path", "Serie/S01/e.mkv").Set("outcome", "live_skipped_not_required"),
            PyJsonFormat.Compact);
        await store.Execute(
            "INSERT INTO activity_events (event_type, module, title, detail) VALUES ('processing.file_remux_pass_completed', 'processing', 't', '" +
            detail.Replace("'", "''", StringComparison.Ordinal) + "')");

        // No remux_context match for this run (a different file just finished), so the cleanup falls back to
        // the recorded activity success instead of treating the episode as never processed.
        var seasonFolder = Path.GetDirectoryName(ep)!;
        var output = await RunAsync(cleanup, ep, minFileAgeSeconds: 86_400, currentJobId: 1, remuxContext: LiveOkContext("Serie/S01/other.mkv"), finalOutputFile: null);

        Assert.True(Bool(output, "tv_season_folder_deleted"));
        Assert.False(Directory.Exists(seasonFolder));
    }

    [Fact]
    public async Task Cascade_removes_the_empty_show_folder()
    {
        var (store, cleanup, http, connections, _) = await BuildAsync();
        using var _1 = store;
        await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "sonarr", "Main", "http://sonarr.local", "key"));
        RouteSonarrQueue(http, "[]");

        var ep = _folders.Source("Serie/S01/e.mkv", 500);
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("Serie/S01/e.mkv"))!);
        File.WriteAllBytes(_folders.Out("Serie/S01/e.mkv"), Enumerable.Repeat((byte)'y', 100).ToArray());

        var seasonFolder = Path.GetDirectoryName(ep)!;
        var showFolder = Path.GetDirectoryName(seasonFolder)!;
        var output = await RunAsync(cleanup, ep, currentJobId: 1, remuxContext: LiveOkContext("Serie/S01/e.mkv"), finalOutputFile: _folders.Out("Serie/S01/e.mkv"));

        Assert.True(Bool(output, "tv_season_folder_deleted"));
        Assert.False(Directory.Exists(seasonFolder));
        Assert.False(Directory.Exists(showFolder));
        Assert.True(Directory.Exists(_folders.Watched));
        var cascade = ((PyList)output["tv_cascade_folders_deleted"]!).Items;
        Assert.Contains(cascade, p => ((PyStr)p).Value.Contains("Serie", StringComparison.Ordinal));
    }
}
