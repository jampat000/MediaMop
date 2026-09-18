using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Json;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Tests.MediaManagers;

namespace Weir.Infrastructure.Tests.Processing;

/// <summary>
/// Ported from <c>apps/backend/tests/test_processing_failure_cleanup.py</c>: <see cref="ProcessingFailureCleanupSweep"/>
/// against a real database and real temporary folders, with each media manager's queue behind
/// <see cref="FakeManagerHttp"/>.
/// </summary>
public sealed class ProcessingFailureCleanupSweepTests : IDisposable
{
    private readonly MediaManagerFixture _fixture = new();
    private readonly TempDirectory _root = new();

    public void Dispose()
    {
        _root.Dispose();
        _fixture.Dispose();
    }

    private ProcessingFailureCleanupSweep Sweep() =>
        new(_fixture.Store.Database, _fixture.Store.Options, _fixture.Connections, TimeProvider.System, NullLogger<ProcessingFailureCleanupSweep>.Instance);

    private string P(string relative) => Directory.CreateDirectory(_root.Join(relative)).FullName;

    /// <summary>Seeds both the Movies and TV libraries with their own watched/output/work folders, mirroring
    /// Python's <c>seed_libraries</c>.</summary>
    private async Task SeedLibrariesAsync(string movieWatched, string movieOutput, string movieWork, string tvWatched, string tvOutput, string tvWork)
    {
        await _fixture.Store.Execute("DELETE FROM libraries");
        await _fixture.Db(uow => uow.ExecuteAsync(
            "INSERT INTO libraries (name, media_type, watched_folder, output_folder, work_folder, display_order) VALUES ('Movies', 'movie', $w, $o, $k, 1)",
            ("$w", movieWatched), ("$o", movieOutput), ("$k", movieWork)));
        await _fixture.Db(uow => uow.ExecuteAsync(
            "INSERT INTO libraries (name, media_type, watched_folder, output_folder, work_folder, display_order) VALUES ('TV', 'tv', $w, $o, $k, 2)",
            ("$w", tvWatched), ("$o", tvOutput), ("$k", tvWork)));
    }

    private Task<int> AddFailedJobAsync(string rel, string scope, bool dryRun = false, TimeSpan? age = null) =>
        _fixture.Db(uow => uow.ExecuteAsync(
            "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status, updated_at) VALUES ($dedupe, 'processing.file.remux_pass.v1', $payload, 'failed', $updated)",
            ("$dedupe", $"x:{scope}:{rel}:{Guid.NewGuid():N}"),
            ("$payload", PyJsonWriter.Dumps(new PyDict().Set("relative_media_path", rel).Set("media_scope", scope).Set("dry_run", dryRun), PyJsonFormat.Compact)),
            ("$updated", Weir.Infrastructure.Jobs.PythonTimestamps.Orm(DateTimeOffset.UtcNow - (age ?? TimeSpan.FromHours(1))))));

    private Task<int> AddPendingJobAsync(string rel, string scope) =>
        _fixture.Db(uow => uow.ExecuteAsync(
            "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status) VALUES ($dedupe, 'processing.file.remux_pass.v1', $payload, 'pending')",
            ("$dedupe", $"p:{scope}:{rel}:{Guid.NewGuid():N}"),
            ("$payload", PyJsonWriter.Dumps(new PyDict().Set("relative_media_path", rel).Set("media_scope", scope), PyJsonFormat.Compact))));

    [Fact]
    public async Task A_failed_movie_older_than_grace_cleans_source_output_and_temp()
    {
        var mw = P("mw");
        var mo = P("mo");
        var mwork = P("mwork");
        await SeedLibrariesAsync(mw, mo, mwork, P("tw"), P("to"), P("twork"));
        const string rel = "Title/Film.mkv";
        Directory.CreateDirectory(Path.Combine(mw, "Title"));
        Directory.CreateDirectory(Path.Combine(mo, "Title"));
        File.WriteAllBytes(Path.Combine(mw, "Title", "Film.mkv"), "a"u8.ToArray());
        File.WriteAllBytes(Path.Combine(mo, "Title", "Film.mkv"), "b"u8.ToArray());
        var temp = Path.Combine(mwork, "Film.processing.tmp.mkv");
        File.WriteAllBytes(temp, "c"u8.ToArray());
        await AddFailedJobAsync(rel, "movie");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", """{"records":[]}""");
        await LinkAllLibrariesAsync(connection);

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.True(((PyBool)job["movie_failure_cleanup_ran"]).Value);
        Assert.Equal("passed_not_in_queue", PyConvert.Str(job["movie_failure_cleanup_queue_check"]));
        Assert.True(((PyBool)job["movie_failure_cleanup_source_folder_deleted"]).Value);
        Assert.True(((PyBool)job["movie_failure_cleanup_output_folder_deleted"]).Value);
        Assert.Contains(temp, ((PyList)job["movie_failure_cleanup_temp_files_deleted"]).Items.Select(PyConvert.Str));
        Assert.False(Directory.Exists(Path.Combine(mw, "Title")));
        Assert.False(Directory.Exists(Path.Combine(mo, "Title")));
        Assert.False(File.Exists(temp));
    }

    [Fact]
    public async Task A_failed_movie_still_held_by_a_manager_skips()
    {
        var mw = P("mw");
        await SeedLibrariesAsync(mw, P("mo"), P("mwork"), P("tw"), P("to"), P("twork"));
        const string rel = "Title/Film.mkv";
        Directory.CreateDirectory(Path.Combine(mw, "Title"));
        var source = Path.Combine(mw, "Title", "Film.mkv");
        File.WriteAllBytes(source, "a"u8.ToArray());
        await AddFailedJobAsync(rel, "movie");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", $$"""{"records":[{"id":1,"outputPath":"{{Path.GetFullPath(source).Replace('\\', '/')}}"}]}""");
        await LinkAllLibrariesAsync(connection);

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.False(((PyBool)job["movie_failure_cleanup_ran"]).Value);
        Assert.Equal("blocked_in_queue", PyConvert.Str(job["movie_failure_cleanup_queue_check"]));
        Assert.True(Directory.Exists(Path.Combine(mw, "Title")));
    }

    [Fact]
    public async Task A_dry_run_failed_job_is_skipped_entirely()
    {
        await SeedLibrariesAsync(P("mw"), P("mo"), P("mwork"), P("tw"), P("to"), P("twork"));
        await AddFailedJobAsync("Title/Film.mkv", "movie", dryRun: true);

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.True(((PyBool)job["movie_failure_cleanup_dry_run"]).Value);
        Assert.Contains("compatibility", PyConvert.Str(job["movie_failure_cleanup_skip_reason"]), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Tv_cleanup_skips_when_a_sibling_episode_is_still_in_the_queue()
    {
        var tw = P("tw");
        await SeedLibrariesAsync(P("mw"), P("mo"), P("mwork"), tw, P("to"), P("twork"));
        Directory.CreateDirectory(Path.Combine(tw, "Show", "Season 1"));
        var ep1 = Path.Combine(tw, "Show", "Season 1", "S01E01.mkv");
        var ep2 = Path.Combine(tw, "Show", "Season 1", "S01E02.mkv");
        File.WriteAllBytes(ep1, "1"u8.ToArray());
        File.WriteAllBytes(ep2, "2"u8.ToArray());
        await AddFailedJobAsync("Show/Season 1/S01E01.mkv", "tv");
        var connection = await _fixture.AddConnectionAsync("sonarr", "Sonarr", "http://10.0.0.5:8989", "k");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/episodefile", "[]");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", $$"""{"records":[{"id":1,"outputPath":"{{Path.GetFullPath(ep2).Replace('\\', '/')}}"}]}""");
        await LinkAllLibrariesAsync(connection);

        var result = await Sweep().RunForScopeAsync("tv", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.False(((PyBool)job["tv_failure_cleanup_ran"]).Value);
        Assert.Equal("blocked_in_queue_or_active_job", PyConvert.Str(job["tv_failure_cleanup_queue_check"]));
        Assert.True(Directory.Exists(Path.Combine(tw, "Show", "Season 1")));
    }

    [Fact]
    public async Task Tv_season_delete_is_blocked_by_a_pending_sibling_job()
    {
        var tw = P("tw");
        await SeedLibrariesAsync(P("mw"), P("mo"), P("mwork"), tw, P("to"), P("twork"));
        Directory.CreateDirectory(Path.Combine(tw, "Show", "Season 1"));
        File.WriteAllBytes(Path.Combine(tw, "Show", "Season 1", "S01E01.mkv"), "1"u8.ToArray());
        File.WriteAllBytes(Path.Combine(tw, "Show", "Season 1", "S01E02.mkv"), "2"u8.ToArray());
        await AddFailedJobAsync("Show/Season 1/S01E01.mkv", "tv");
        await AddFailedJobAsync("Show/Season 1/S01E02.mkv", "tv");
        await AddPendingJobAsync("Show/Season 1/S01E02.mkv", "tv");
        var connection = await _fixture.AddConnectionAsync("sonarr", "Sonarr", "http://10.0.0.5:8989", "k");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/episodefile", "[]");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", """{"records":[]}""");
        await LinkAllLibrariesAsync(connection);

        var result = await Sweep().RunForScopeAsync("tv", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.False(((PyBool)job["tv_failure_cleanup_ran"]).Value);
        Assert.Equal("blocked_in_queue_or_active_job", PyConvert.Str(job["tv_failure_cleanup_queue_check"]));
    }

    [Fact]
    public async Task Missing_path_settings_skip_cleanly()
    {
        await _fixture.Store.Execute("DELETE FROM libraries");
        await _fixture.Db(uow => uow.ExecuteAsync(
            "INSERT INTO libraries (name, media_type, display_order) VALUES ('Movies', 'movie', 1)"));

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        Assert.Equal("skipped", PyConvert.Str(result["cleanup_run_status"]));
        Assert.Contains("not configured", PyConvert.Str(result["skip_reason"]), StringComparison.Ordinal);
    }

    [Fact]
    public async Task No_eligible_failed_jobs_reports_no_eligible_status()
    {
        await SeedLibrariesAsync(P("mw"), P("mo"), P("mwork"), P("tw"), P("to"), P("twork"));

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        Assert.Equal("no_eligible_files", PyConvert.Str(result["cleanup_run_status"]));
        Assert.Equal(0L, (long)((PyInt)result["eligible_failed_jobs"]).Value);
        Assert.Contains("No eligible failed jobs", PyConvert.Str(result["skip_reason"]), StringComparison.Ordinal);
    }

    [Fact]
    public async Task No_manager_configured_for_the_scope_skips_with_a_named_reason()
    {
        await SeedLibrariesAsync(P("mw"), P("mo"), P("mwork"), P("tw"), P("to"), P("twork"));
        await AddFailedJobAsync("Title/Film.mkv", "movie");

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.False(((PyBool)job["movie_failure_cleanup_ran"]).Value);
        Assert.Contains("could not check whether anything is still importing", PyConvert.Str(job["movie_failure_cleanup_skip_reason"]), StringComparison.Ordinal);
        Assert.Contains("No media manager is connected for Movies.", PyConvert.Str(job["movie_failure_cleanup_skip_reason"]), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Root_bounds_prevent_deleting_the_watched_root_itself()
    {
        var mw = P("mw");
        var mo = P("mo");
        await SeedLibrariesAsync(mw, mo, P("mwork"), P("tw"), P("to"), P("twork"));
        File.WriteAllBytes(Path.Combine(mw, "Film.mkv"), "x"u8.ToArray());
        File.WriteAllBytes(Path.Combine(mo, "Film.mkv"), "y"u8.ToArray());
        await AddFailedJobAsync("Film.mkv", "movie");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", """{"records":[]}""");
        await LinkAllLibrariesAsync(connection);

        var result = await Sweep().RunForScopeAsync("movie", CancellationToken.None);

        var job = (PyDict)((PyList)result["jobs"]).Items[0];
        Assert.False(((PyBool)job["movie_failure_cleanup_source_folder_deleted"]).Value);
        Assert.Equal(Path.GetFullPath(mw), Path.GetFullPath(PyConvert.Str(job["movie_failure_cleanup_source_folder_path"])));
        Assert.True(File.Exists(Path.Combine(mw, "Film.mkv")));
    }

    private async Task LinkAllLibrariesAsync(long connectionId)
    {
        var libraryIds = await _fixture.Db(uow => uow.QueryAsync("SELECT id FROM libraries", reader => reader.GetInt64(0)));
        foreach (var libraryId in libraryIds)
        {
            await _fixture.Store.Execute($"INSERT INTO library_manager_links (library_id, connection_id) VALUES ({libraryId}, {connectionId})");
        }
    }
}
