using System.Globalization;
using System.Net;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Tests.MediaManagers;

namespace Weir.Infrastructure.Tests.Refiner.RemuxPass;

/// <summary>
/// Ported from <c>apps/backend/tests/test_refiner_reject.py</c>: <see cref="RefinerRejectHandler"/> against a real
/// database and real temporary folders, with each manager behind <see cref="FakeManagerHttp"/>.
/// </summary>
public sealed class RefinerRejectHandlerTests : IDisposable
{
    private const string EventsPath = "/api/integrations/processors/events";
    private const string ManifestPath = "/api/integrations/external/manifest";

    private readonly MediaManagerFixture _fixture = new();
    private readonly PassFolders _folders = new();

    public void Dispose()
    {
        _folders.Dispose();
        _fixture.Dispose();
    }

    private RefinerRejectHandler Handler() =>
        new(
            _fixture.Store.Database,
            _fixture.Ports,
            _fixture.Connections,
            _fixture.Reporter,
            _fixture.Ledger,
            _fixture.Jobs,
            new RejectPacing(TimeProvider.System),
            TimeProvider.System,
            NullLogger<RefinerRejectHandler>.Instance);

    private async Task<long> LibraryAsync(string rejectedFileAction = "leave")
    {
        await _fixture.Store.Execute("DELETE FROM refiner_libraries");
        return Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO refiner_libraries (name, media_type, watched_folder, output_folder, work_folder, failure_policy, rejected_file_action, display_order) " +
            "VALUES ('Movies', 'movie', $w, $o, $k, 'reject', $action, 1) RETURNING id",
            ("$w", _folders.Watched),
            ("$o", _folders.Output),
            ("$k", _folders.Work),
            ("$action", rejectedFileAction))), CultureInfo.InvariantCulture);
    }

    private Task LinkAsync(long libraryId, long connectionId) =>
        _fixture.Store.Execute($"INSERT INTO refiner_library_manager_links (library_id, connection_id) VALUES ({libraryId}, {connectionId})");

    private Task FileRowAsync(long libraryId, string relativePath, string status = "processing_failed") =>
        _fixture.Store.Execute(
            $"INSERT INTO refiner_files (library_id, relative_path, status, status_reason) VALUES ({libraryId}, '{relativePath}', '{status}', 'ffmpeg could not read the audio track.')");

    private static JobWorkContext Context(long id, string payload) => new(id, IntakeRules.RejectJobKind, payload, "test");

    private async Task<string> ScalarText(string sql)
    {
        using var connection = _fixture.Store.Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(await command.ExecuteScalarAsync(), CultureInfo.InvariantCulture) ?? string.Empty;
    }

    // --- through a hand-off (Deluno) --------------------------------------------------------------

    [Fact]
    public async Task An_accepted_handoff_rejection_removes_the_source_and_reports_disposition_rejected()
    {
        var library = await LibraryAsync(rejectedFileAction: "delete_file");
        var source = _folders.Source("Film/film.mkv");
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await LinkAsync(library, connection);
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h1", library, "Film/film.mkv"); return 0; });
        _fixture.Http.Json(HttpMethod.Get, ManifestPath, """{"capabilities":["processor-reject-regrab"],"libraries":[]}""");
        _fixture.Http.Json(HttpMethod.Post, EventsPath, "{}", HttpStatusCode.Accepted);
        var payload = $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"reason":"ffmpeg could not read the audio track.","failure_class":"execution","origin":{"source_key":"deluno","handoff_id":"h1","library_id":"lib-movies","callback_path":"{{{EventsPath}}}"}}""";

        await Handler().HandleAsync(Context(41, payload), CancellationToken.None);

        var post = Assert.Single(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
        var body = (PyDict)post.Json!;
        Assert.Equal("failed", PyConvert.Str(body["status"]));
        Assert.Equal("rejected", PyConvert.Str(body["disposition"]));
        Assert.True(((PyBool)body["sourceRemoved"]).Value);
        Assert.Equal("lib-movies", PyConvert.Str(body["libraryId"]));
        Assert.Equal("execution", PyConvert.Str(body["failureClass"]));
        Assert.False(File.Exists(source));
        Assert.Equal("rejected", await ScalarText("SELECT status FROM refiner_files"));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'refiner.file_rejected'"));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'refiner.handoff_reported'"));
        Assert.Equal(0, await _fixture.Store.Scalar($"SELECT count(*) FROM refiner_jobs WHERE job_kind = '{IntakeRules.PassThroughJobKind}'"));
        Assert.Equal("rejected", await ScalarText("SELECT state FROM media_manager_handoffs WHERE handoff_id = 'h1'"));
    }

    [Fact]
    public async Task A_refused_rejection_keeps_the_download_and_hands_it_back()
    {
        var library = await LibraryAsync();
        var source = _folders.Source("Film/film.mkv");
        var bytesBefore = File.ReadAllBytes(source);
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await LinkAsync(library, connection);
        _fixture.Http.Json(HttpMethod.Get, ManifestPath, """{"capabilities":["processor-reject-regrab"],"libraries":[]}""");
        _fixture.Http.Json(HttpMethod.Post, EventsPath, "{}", HttpStatusCode.Conflict);
        var payload = $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"reason":"ffmpeg could not read the audio track.","origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"{{{EventsPath}}}"}}""";

        await Handler().HandleAsync(Context(42, payload), CancellationToken.None);

        Assert.Equal(bytesBefore, File.ReadAllBytes(source));
        var reason = await ScalarText("SELECT status_reason FROM refiner_files");
        Assert.NotEqual("rejected", await ScalarText("SELECT status FROM refiner_files"));
        Assert.Contains("did not accept the rejection", reason, StringComparison.Ordinal);
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM refiner_jobs WHERE job_kind = '{IntakeRules.PassThroughJobKind}'"));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'refiner.file_reject_fell_back'"));
    }

    [Fact]
    public async Task An_unreachable_manager_is_not_an_acceptance()
    {
        var library = await LibraryAsync();
        var source = _folders.Source("Film/film.mkv");
        var bytesBefore = File.ReadAllBytes(source);
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await LinkAsync(library, connection);
        _fixture.Http.Json(HttpMethod.Get, ManifestPath, """{"capabilities":["processor-reject-regrab"],"libraries":[]}""");
        _fixture.Http.Throw(HttpMethod.Post, EventsPath, new HttpRequestException("no route to host"));
        var payload = $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"{{{EventsPath}}}"}}""";

        await Handler().HandleAsync(Context(43, payload), CancellationToken.None);

        Assert.Equal(bytesBefore, File.ReadAllBytes(source));
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM refiner_jobs WHERE job_kind = '{IntakeRules.PassThroughJobKind}'"));
    }

    [Fact]
    public async Task A_manager_that_cannot_replace_the_release_is_never_told_to_reject()
    {
        var library = await LibraryAsync();
        _folders.Source("Film/film.mkv");
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await LinkAsync(library, connection);
        _fixture.Http.Json(HttpMethod.Get, ManifestPath, """{"capabilities":[],"libraries":[]}""");
        _fixture.Http.Json(HttpMethod.Post, EventsPath, "{}", HttpStatusCode.Accepted);
        var payload = $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"{{{EventsPath}}}"}}""";

        await Handler().HandleAsync(Context(44, payload), CancellationToken.None);

        Assert.Empty(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
        Assert.Contains("does not yet say it can replace a rejected release", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM refiner_jobs WHERE job_kind = '{IntakeRules.PassThroughJobKind}'"));
    }

    // --- through Sonarr / Radarr's queue -----------------------------------------------------------

    [Fact]
    public async Task A_single_file_download_is_removed_and_blocklisted_through_the_queue()
    {
        var library = await LibraryAsync();
        var source = _folders.Source("Film/film.mkv");
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        await LinkAsync(library, connection);
        var outputPath = Path.GetFullPath(source).Replace('\\', '/');
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", $$"""{"records":[{"id":55,"outputPath":"{{outputPath}}","downloadId":"dl1"}]}""");
        _fixture.Http.Route(HttpMethod.Delete, "/api/v3/queue/55", _ => FakeManagerHttp.Response(HttpStatusCode.OK));
        var payload = $$"""{"relative_media_path":"Film/film.mkv","library_id":{{library}}}""";

        await Handler().HandleAsync(Context(45, payload), CancellationToken.None);

        Assert.Single(_fixture.Http.RequestsTo(HttpMethod.Delete, "/api/v3/queue/55"));
        Assert.Equal("rejected", await ScalarText("SELECT status FROM refiner_files"));
        Assert.Contains("removed the download and blocklisted the release", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
    }

    [Fact]
    public async Task No_matching_queue_item_hands_the_original_back()
    {
        var library = await LibraryAsync();
        _folders.Source("Film/film.mkv");
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        await LinkAsync(library, connection);
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", """{"records":[]}""");
        var payload = $$"""{"relative_media_path":"Film/film.mkv","library_id":{{library}}}""";

        await Handler().HandleAsync(Context(46, payload), CancellationToken.None);

        Assert.Contains("No download in the linked media manager's queue", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM refiner_jobs WHERE job_kind = '{IntakeRules.PassThroughJobKind}'"));
    }

    [Fact]
    public async Task Two_matching_queue_items_are_never_guessed_between()
    {
        var library = await LibraryAsync();
        var source = _folders.Source("Film/film.mkv");
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        await LinkAsync(library, connection);
        var outputPath = Path.GetFullPath(source).Replace('\\', '/');
        _fixture.Http.Json(HttpMethod.Get, "/api/v3/queue", $$"""{"records":[{"id":55,"outputPath":"{{outputPath}}"},{"id":56,"outputPath":"{{outputPath}}"}]}""");
        var payload = $$"""{"relative_media_path":"Film/film.mkv","library_id":{{library}}}""";

        await Handler().HandleAsync(Context(47, payload), CancellationToken.None);

        Assert.Contains("Weir could not tell which one to reject", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Empty(_fixture.Http.RequestsTo(HttpMethod.Delete, "/api/v3/queue/55"));
    }

    [Fact]
    public async Task A_season_pack_tracked_as_several_items_is_never_rejected()
    {
        var library = await LibraryAsync();
        var source = _folders.Source("Film/film.mkv");
        await FileRowAsync(library, "Film/film.mkv");
        var connection = await _fixture.AddConnectionAsync("radarr", "Radarr", "http://10.0.0.5:7878", "k");
        await LinkAsync(library, connection);
        var outputPath = Path.GetFullPath(source).Replace('\\', '/');
        _fixture.Http.Json(
            HttpMethod.Get, "/api/v3/queue",
            $$"""{"records":[{"id":55,"outputPath":"{{outputPath}}","downloadId":"dl1"},{"id":56,"outputPath":"other","downloadId":"dl1"}]}""");
        var payload = $$"""{"relative_media_path":"Film/film.mkv","library_id":{{library}}}""";

        await Handler().HandleAsync(Context(48, payload), CancellationToken.None);

        Assert.Contains("a season pack or", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Empty(_fixture.Http.RequestsTo(HttpMethod.Delete, "/api/v3/queue/55"));
    }

    [Fact]
    public async Task No_linked_manager_that_can_reject_hands_the_original_back()
    {
        var library = await LibraryAsync();
        _folders.Source("solo.mkv");
        await FileRowAsync(library, "solo.mkv");
        var payload = $$"""{"relative_media_path":"solo.mkv","library_id":{{library}}}""";

        await Handler().HandleAsync(Context(49, payload), CancellationToken.None);

        Assert.Contains("No linked media manager can take a rejection", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM refiner_jobs WHERE job_kind = '{IntakeRules.PassThroughJobKind}'"));
    }

    // --- fix #532: a rejection always upserts a Files row ----------------------------------------

    [Fact]
    public async Task Fix_532_a_rejection_upserts_a_files_row_even_with_no_prior_scan()
    {
        var library = await LibraryAsync(rejectedFileAction: "delete_file");
        _folders.Source("Film/film.mkv");
        // Deliberately no refiner_files row: this hand-off was never seen by a watched-folder scan.
        var connection = await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await LinkAsync(library, connection);
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h9", library, "Film/film.mkv"); return 0; });
        _fixture.Http.Json(HttpMethod.Get, ManifestPath, """{"capabilities":["processor-reject-regrab"],"libraries":[]}""");
        _fixture.Http.Json(HttpMethod.Post, EventsPath, "{}", HttpStatusCode.Accepted);
        var payload = $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"reason":"Weir could not read this file's contents.","failure_class":"preflight","origin":{"source_key":"deluno","handoff_id":"h9","callback_path":"{{{EventsPath}}}"}}""";

        Assert.Equal(0, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_files"));

        await Handler().HandleAsync(Context(50, payload), CancellationToken.None);

        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_files"));
        Assert.Equal(
            "rejected|preflight",
            await ScalarText("SELECT status || '|' || failure_class FROM refiner_files WHERE relative_path = 'Film/film.mkv'"));
    }
}
