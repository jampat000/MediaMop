using System.Globalization;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Processing.RemuxPass;
using Weir.Infrastructure.Tests.MediaManagers;

namespace Weir.Infrastructure.Tests.Processing.RemuxPass;

/// <summary>
/// Ported from <c>apps/backend/tests/test_processing_pass_through.py</c>: <see cref="ProcessingPassThroughHandler"/> against a
/// real database and real temporary folders, with the manager side behind <see cref="FakeManagerHttp"/>.
/// </summary>
public sealed class ProcessingPassThroughHandlerTests : IDisposable
{
    private const string EventsPath = "/api/integrations/processors/events";

    private readonly MediaManagerFixture _fixture = new();
    private readonly PassFolders _folders = new();

    public void Dispose()
    {
        _folders.Dispose();
        _fixture.Dispose();
    }

    private ProcessingPassThroughHandler Handler() =>
        new(_fixture.Store.Database, TimeProvider.System, NullLogger<ProcessingPassThroughHandler>.Instance, _fixture.Reporter);

    private async Task<long> LibraryAsync(string collision = "replace")
    {
        await _fixture.Store.Execute("DELETE FROM libraries");
        return Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO libraries (name, media_type, watched_folder, output_folder, work_folder, output_collision_policy, display_order) " +
            "VALUES ('Movies', 'movie', $w, $o, $k, $collision, 1) RETURNING id",
            ("$w", _folders.Watched),
            ("$o", _folders.Output),
            ("$k", _folders.Work),
            ("$collision", collision))), CultureInfo.InvariantCulture);
    }

    private Task FileRowAsync(long libraryId, string relativePath, string status = "processing_failed") =>
        _fixture.Store.Execute(
            $"INSERT INTO files (library_id, relative_path, status, status_reason) VALUES ({libraryId}, '{relativePath}', '{status}', 'failed')");

    private static JobWorkContext Context(long id, string payload) => new(id, IntakeRules.PassThroughJobKind, payload, "test");

    private async Task<string> ScalarText(string sql)
    {
        using var connection = _fixture.Store.Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(await command.ExecuteScalarAsync(), CultureInfo.InvariantCulture) ?? string.Empty;
    }

    [Fact]
    public async Task The_original_is_delivered_byte_for_byte_and_the_source_survives()
    {
        var library = await LibraryAsync();
        var source = _folders.Source(Path.Join("Movie", "file.mkv"), bytes: 5000);
        await FileRowAsync(library, "Movie/file.mkv");
        var payload = $$"""{"relative_media_path":"Movie/file.mkv","library_id":{{library}},"trigger":"worker"}""";

        await Handler().HandleAsync(Context(1, payload), CancellationToken.None);

        var destination = _folders.Out(Path.Join("Movie", "file.mkv"));
        Assert.True(File.Exists(destination));
        Assert.Equal(File.ReadAllBytes(source), File.ReadAllBytes(destination));
        Assert.True(File.Exists(source), "the source must never be deleted by a pass-through");
        Assert.Equal("passed_through", await ScalarText("SELECT status FROM files"));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'processing.file_passed_through'"));
        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events WHERE event_type = 'processing.file_passed_through'"));
        Assert.True(((PyBool)detail["delivered"]).Value);
        Assert.True(((PyBool)detail["source_kept"]).Value);
    }

    [Fact]
    public async Task Nothing_half_written_is_left_when_the_source_vanishes_mid_flight()
    {
        var library = await LibraryAsync();
        await FileRowAsync(library, "gone.mkv");
        var payload = $$"""{"relative_media_path":"gone.mkv","library_id":{{library}},"trigger":"worker"}""";

        var exception = await Assert.ThrowsAsync<AlreadyRecordedFailureException>(
            () => Handler().HandleAsync(Context(2, payload), CancellationToken.None));

        Assert.Contains("no longer in the watched folder", exception.Message, StringComparison.Ordinal);
        Assert.False(File.Exists(_folders.Out("gone.mkv")));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'processing.file_pass_through_failed'"));
        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events WHERE event_type = 'processing.file_pass_through_failed'"));
        Assert.True(((PyBool)detail["source_kept"]).Value);
        Assert.Equal("failed", PyConvert.Str(detail["result"]));
    }

    [Fact]
    public async Task Output_folder_same_as_watched_folder_is_refused_without_deleting_anything()
    {
        await _fixture.Store.Execute("DELETE FROM libraries");
        var library = Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO libraries (name, media_type, watched_folder, output_folder, work_folder, display_order) " +
            "VALUES ('Movies', 'movie', $w, $w, $k, 1) RETURNING id",
            ("$w", _folders.Watched),
            ("$k", _folders.Work))), CultureInfo.InvariantCulture);
        _folders.Source("file.mkv");
        await FileRowAsync(library, "file.mkv");
        var payload = $$"""{"relative_media_path":"file.mkv","library_id":{{library}},"trigger":"worker"}""";

        await Assert.ThrowsAsync<AlreadyRecordedFailureException>(() => Handler().HandleAsync(Context(3, payload), CancellationToken.None));
        Assert.True(File.Exists(_folders.Source("file.mkv")));
    }

    [Fact]
    public async Task An_existing_output_under_skip_is_respected_and_delivered_false_means_no_report()
    {
        var library = await LibraryAsync(collision: "skip");
        _folders.Source("file.mkv");
        Directory.CreateDirectory(Path.GetDirectoryName(_folders.Out("file.mkv"))!);
        File.WriteAllText(_folders.Out("file.mkv"), "already there");
        await FileRowAsync(library, "file.mkv");
        await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "hskip", library, "file.mkv"); return 0; });
        var payload = $$$"""{"relative_media_path":"file.mkv","library_id":{{{library}}},"trigger":"worker","origin":{"source_key":"deluno","handoff_id":"hskip","callback_path":"{{{EventsPath}}}"}}""";

        await Handler().HandleAsync(Context(4, payload), CancellationToken.None);

        Assert.Equal("already there", File.ReadAllText(_folders.Out("file.mkv")));
        Assert.Empty(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events WHERE event_type = 'processing.file_passed_through'"));
        Assert.False(((PyBool)detail["delivered"]).Value);
        Assert.Equal("skip", PyConvert.Str(detail["collision_action"]));
    }

    [Fact]
    public async Task A_delivered_hand_off_is_reported_to_the_waiting_manager_with_its_output_path()
    {
        var library = await LibraryAsync();
        _folders.Source(Path.Join("Film", "film.mkv"));
        await FileRowAsync(library, "Film/film.mkv");
        await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h1", library, "Film/film.mkv"); return 0; });
        var payload = $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"trigger":"worker","origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"{{{EventsPath}}}"}}""";

        await Handler().HandleAsync(Context(5, payload), CancellationToken.None);

        var post = Assert.Single(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
        var body = (PyDict)post.Json!;
        Assert.Equal(("h1", "completed"), (PyConvert.Str(body["handoffId"]), PyConvert.Str(body["status"])));
        Assert.Equal(Path.GetFullPath(_folders.Out(Path.Join("Film", "film.mkv"))), PyConvert.Str(body["outputPath"]));
        Assert.Equal(
            "Weir could not process this file, so it handed the original back unchanged; it is ready to import.",
            PyConvert.Str(body["message"]));
        Assert.Equal("passed-through", await ScalarText("SELECT state FROM media_manager_handoffs WHERE handoff_id = 'h1'"));
    }

    [Fact]
    public async Task A_delivery_that_did_not_come_from_a_manager_reports_nothing()
    {
        var library = await LibraryAsync();
        _folders.Source("solo.mkv");
        await FileRowAsync(library, "solo.mkv");
        var payload = $$"""{"relative_media_path":"solo.mkv","library_id":{{library}},"trigger":"worker"}""";

        await Handler().HandleAsync(Context(6, payload), CancellationToken.None);

        Assert.Empty(_fixture.Http.Requests);
        Assert.Equal("passed_through", await ScalarText("SELECT status FROM files"));
    }

    [Fact]
    public async Task Repeated_pass_through_jobs_for_the_same_file_share_one_dedupe_key()
    {
        var library = await LibraryAsync();
        var jobs = _fixture.Jobs;
        var body = $$"""{"relative_media_path":"x.mkv","library_id":{{library}},"trigger":"worker"}""";
        var first = await jobs.EnqueueOrGetAsync($"processing.file.pass_through.v1:{library}:x.mkv", IntakeRules.PassThroughJobKind, body);
        var second = await jobs.EnqueueOrGetAsync($"processing.file.pass_through.v1:{library}:x.mkv", IntakeRules.PassThroughJobKind, body);
        Assert.Equal(first.Id, second.Id);
    }
}
