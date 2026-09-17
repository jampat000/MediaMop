using System.Globalization;
using System.Net;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Refiner.RemuxPass;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Tests.Media;
using Weir.Infrastructure.Tests.MediaManagers;

namespace Weir.Infrastructure.Tests.Refiner.RemuxPass;

/// <summary>
/// Ported from <c>apps/backend/tests/test_refiner_file_remux_pass_activity_handler.py</c>, plus the policy and hand-off paths the
/// handler drives: a real database at head, real folders, and ffprobe/ffmpeg behind a fake process runner.
/// </summary>
public sealed class RemuxPassHandlerTests : IDisposable
{
    private const string EventsPath = "/api/integrations/processors/events";

    private readonly MediaManagerFixture _fixture = new();
    private readonly PassFolders _folders = new();
    private readonly FakeMediaRunner _media = new();

    public RemuxPassHandlerTests()
    {
        _fixture.Store.Execute(
            "UPDATE refiner_operator_settings SET min_file_age_seconds = 0, refiner_min_input_file_size_mb = 0, minimum_free_disk_space_mb = 0")
            .GetAwaiter().GetResult();
        _fixture.Http.Json(HttpMethod.Post, EventsPath, "{}", HttpStatusCode.Accepted);
    }

    public void Dispose()
    {
        _folders.Dispose();
        _fixture.Dispose();
    }

    private RemuxPassHandler Handler(IFailurePolicy? policy = null)
    {
        var data = new SqliteRemuxPassData(_fixture.Store.Database, _fixture.Connections, NullLogger<SqliteRemuxPassData>.Instance);
        var runner = new RemuxPassRunner(
            new MediaTools(_media, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System),
            new FixedResolver(),
            data,
            data,
            new SkippedTvSeasonFolderCleanup(),
            new FakeOriginalLanguage(),
            new RemuxPassSettings { WatchedFolderMinFileAgeSeconds = 0 },
            TimeProvider.System,
            NullLogger<RemuxPassRunner>.Instance);
        return new RemuxPassHandler(
            _fixture.Store.Database,
            _fixture.Store.Options,
            runner,
            policy ?? new QueueingFailurePolicy(_fixture.Jobs),
            TimeProvider.System,
            NullLogger<RemuxPassHandler>.Instance,
            _fixture.Reporter);
    }

    private async Task<long> LibraryAsync(string failurePolicy = "pass_through", long maxAttempts = 3, string rejectedFileAction = "leave", string mediaType = "movie")
    {
        await _fixture.Store.Execute("DELETE FROM refiner_libraries");
        return Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO refiner_libraries (name, media_type, watched_folder, output_folder, work_folder, failure_policy, max_attempts, " +
            "rejected_file_action, retry_backoff_seconds, min_file_age_seconds, display_order) " +
            "VALUES ('Movies', $type, $w, $o, $k, $policy, $max, $action, 60, 0, 1) RETURNING id",
            ("$type", mediaType),
            ("$w", _folders.Watched),
            ("$o", _folders.Output),
            ("$k", _folders.Work),
            ("$policy", failurePolicy),
            ("$max", maxAttempts),
            ("$action", rejectedFileAction))), CultureInfo.InvariantCulture);
    }

    private Task FileRowAsync(long libraryId, string relativePath, string status = "processing") =>
        _fixture.Store.Execute(
            $"INSERT INTO refiner_files (library_id, relative_path, status, status_reason) VALUES ({libraryId}, '{relativePath}', '{status}', 'Processing')");

    private async Task<long> EnqueueAsync(string payload, string dedupe)
    {
        var job = await _fixture.Jobs.EnqueueOrGetAsync(dedupe, RemuxPassOutcomes.JobKind, payload);
        return job.Id;
    }

    private static JobWorkContext Context(long id, string payload) => new(id, RemuxPassOutcomes.JobKind, payload, "test");

    private async Task<string> ScalarText(string sql)
    {
        using var connection = _fixture.Store.Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(await command.ExecuteScalarAsync(), CultureInfo.InvariantCulture) ?? string.Empty;
    }

    [Fact]
    public async Task The_progress_row_becomes_the_completed_activity_row_and_the_file_is_processed()
    {
        var library = await LibraryAsync();
        _folders.Source(Path.Join("Movie", "file.mkv"));
        _media.Probes["file.mkv"] = FakeMediaRunner.EnglishAndJapanese;
        await FileRowAsync(library, "Movie/file.mkv", "unprocessed");
        var payload = $$$"""{"relative_media_path":"Movie/file.mkv","media_scope":"movie","library_id":{{{library}}}}""";

        await Handler().HandleAsync(Context(123, payload), CancellationToken.None);

        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM activity_events"));
        Assert.Equal("refiner.file_remux_pass_completed|refiner|file.mkv was processed successfully", await ScalarText("SELECT event_type || '|' || module || '|' || title FROM activity_events"));
        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events"));
        Assert.Equal(("live_output_written", "123"), (PyConvert.Str(detail["outcome"]), PyConvert.Str(detail["job_id"])));
        Assert.Equal("processed|Refiner finished processing this file.", await ScalarText("SELECT status || '|' || status_reason FROM refiner_files"));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_file_logs WHERE outcome = 'live_output_written' AND library_name = 'Movies' AND file_id IS NOT NULL"));
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_files WHERE video_codec = 'h264' AND audio_track_count = 2 AND output_collision_action = 'write'"));
    }

    [Fact]
    public async Task A_source_that_is_not_ready_puts_the_file_on_hold_without_counting_a_failure()
    {
        var library = await LibraryAsync();
        await _fixture.Store.Execute($"INSERT INTO refiner_files (library_id, relative_path, status, failure_class, failure_attempts) VALUES ({library}, 'Testament/file.mkv', 'processing', 'execution', 2)");
        var result = new PyDict().Set("ok", false).Set("outcome", "source_not_ready").Set("retryable_wait", true)
            .Set("relative_media_path", "Testament/file.mkv").Set("reason", "This file is still open for writing by another program.");

        await Handler().ApplyFileOutcomeStateAsync(result, library, "movie", null);

        Assert.Equal("on_hold|0||", await ScalarText("SELECT status || '|' || failure_attempts || '|' || coalesce(failure_class, '') || '|' || coalesce(next_retry_at, '') FROM refiner_files"));
        Assert.Equal((false, false), (((PyBool)result["quarantined"]).Value, ((PyBool)result["retry_scheduled"]).Value));
    }

    [Fact]
    public async Task A_rejected_no_video_file_is_deleted_only_after_the_rejection_was_recorded()
    {
        var library = await LibraryAsync(rejectedFileAction: "delete_file");
        var source = _folders.Source("audio-only.mpg");
        _media.DefaultProbe = """{"streams":[{"index":0,"codec_type":"audio","codec_name":"ac3","channels":2}]}""";
        await FileRowAsync(library, "audio-only.mpg");

        await Handler().HandleAsync(Context(5, $$$"""{"relative_media_path":"audio-only.mpg","library_id":{{{library}}}}"""), CancellationToken.None);

        Assert.False(File.Exists(source));
        Assert.StartsWith("skipped|0|", await ScalarText("SELECT status || '|' || failure_attempts || '|' || status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Contains("deleted the rejected file", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_file_logs WHERE title = 'Rejected file cleanup finished'"));
        Assert.Equal(0, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_jobs WHERE job_kind <> 'refiner.file.remux_pass.v1'"));
    }

    [Fact]
    public async Task An_execution_failure_is_retried_then_handed_back_under_pass_through_carrying_the_origin()
    {
        var library = await LibraryAsync(maxAttempts: 2);
        _folders.Source(Path.Join("Film", "film.mkv"));
        _media.DefaultProbe = FakeMediaRunner.EnglishAndJapanese;
        _media.RemuxError = "Conversion failed";
        await FileRowAsync(library, "Film/film.mkv");
        await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h1", library, "Film/film.mkv"); return 0; });
        var handoff = $$$"""{"relative_media_path":"Film/film.mkv","media_scope":"movie","trigger":"webhook","library_id":{{{library}}},"origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"{{{EventsPath}}}","release_name":"Film.2001"}}""";
        var first = await EnqueueAsync(handoff, "remux:h1");

        await Handler().HandleAsync(Context(first, handoff), CancellationToken.None);

        Assert.Equal("processing_failed|1|execution", await ScalarText("SELECT status || '|' || failure_attempts || '|' || failure_class FROM refiner_files"));
        Assert.NotEqual(string.Empty, await ScalarText("SELECT coalesce(next_retry_at, '') FROM refiner_files"));
        Assert.Empty(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
        var retrying = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events WHERE event_type = 'refiner.file_remux_pass_completed'"));
        Assert.Equal("retrying", PyConvert.Str(retrying["result"]));

        // #531 item 2: the retry a scan queues has no origin of its own; the pass carries the hand-off's forward.
        var retryPayload = $$"""{"relative_media_path":"Film/film.mkv","media_scope":"movie","library_id":{{library}},"trigger":"scheduled"}""";
        var second = await EnqueueAsync(retryPayload, "remux:retry");
        await Handler().HandleAsync(Context(second, retryPayload), CancellationToken.None);

        Assert.StartsWith("processing_failed|2|", await ScalarText("SELECT status || '|' || failure_attempts || '|' FROM refiner_files"), StringComparison.Ordinal);
        var passThrough = await ScalarText("SELECT payload_json FROM refiner_jobs WHERE job_kind = 'refiner.file.pass_through.v1'");
        Assert.Equal(
            $$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"trigger":"worker","origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"{{{EventsPath}}}","release_name":"Film.2001"}}""",
            passThrough);
        Assert.Equal($"refiner.file.pass_through.v1:{library}:Film/film.mkv", await ScalarText("SELECT dedupe_key FROM refiner_jobs WHERE job_kind = 'refiner.file.pass_through.v1'"));
        Assert.Contains("handing the original back to the output folder unchanged", await ScalarText("SELECT status_reason FROM refiner_files"), StringComparison.Ordinal);
        // The pass-through reports on its own once delivered, so nothing is sent yet.
        Assert.Empty(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
    }

    [Fact]
    public async Task A_retried_hand_off_that_succeeds_is_reported_with_its_output_path()
    {
        var library = await LibraryAsync();
        _folders.Source(Path.Join("Film", "film.mkv"));
        await FileRowAsync(library, "Film/film.mkv", "processing_failed");
        await _fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h2", library, "Film/film.mkv"); return 0; });
        await EnqueueAsync($$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"origin":{"source_key":"deluno","handoff_id":"h2","callback_path":"{{{EventsPath}}}"}}""", "remux:h2");
        var retryPayload = $$"""{"relative_media_path":"Film/film.mkv","media_scope":"movie","library_id":{{library}},"trigger":"scheduled"}""";
        var retry = await EnqueueAsync(retryPayload, "remux:retry2");

        await Handler().HandleAsync(Context(retry, retryPayload), CancellationToken.None);

        var post = Assert.Single(_fixture.Http.RequestsTo(HttpMethod.Post, EventsPath));
        var body = (PyDict)post.Json!;
        Assert.Equal(("h2", "completed"), (PyConvert.Str(body["handoffId"]), PyConvert.Str(body["status"])));
        Assert.Equal(Path.GetFullPath(_folders.Out(Path.Join("Film", "film.mkv"))), PyConvert.Str(body["outputPath"]));
        Assert.Equal("completed", await ScalarText("SELECT state FROM media_manager_handoffs WHERE handoff_id = 'h2'"));
        Assert.Equal(Path.GetFullPath(_folders.Out(Path.Join("Film", "film.mkv"))), await ScalarText("SELECT output_path FROM media_manager_handoffs WHERE handoff_id = 'h2'"));
    }

    [Fact]
    public async Task An_origin_is_never_carried_to_a_hand_off_that_was_already_answered()
    {
        var library = await LibraryAsync();
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h3", library, "Film/film.mkv"); return 0; });
        await EnqueueAsync($$$"""{"relative_media_path":"Film/film.mkv","library_id":{{{library}}},"origin":{"source_key":"deluno","handoff_id":"h3"}}""", "remux:h3");

        Assert.NotNull(await _fixture.Db(uow => HandoffOriginCarry.FindAsync(uow, library, "Film/film.mkv")));
        await _fixture.Db(async uow => { await _fixture.Ledger.RecordOutcomeAsync(uow, "deluno", "h3", "completed", "/out/film.mkv"); return 0; });
        Assert.Null(await _fixture.Db(uow => HandoffOriginCarry.FindAsync(uow, library, "Film/film.mkv")));
        Assert.Null(await _fixture.Db(uow => HandoffOriginCarry.FindAsync(uow, library, "Other/film.mkv")));
    }

    [Fact]
    public async Task Unreadable_content_under_reject_queues_a_reject_instead_of_a_hand_back()
    {
        var library = await LibraryAsync(failurePolicy: "reject");
        _folders.Source("bad.mkv");
        _media.ProbeError = "[matroska,webm @ 0x1] EBML header parsing failed\nbad.mkv: Invalid data found when processing input";
        await FileRowAsync(library, "bad.mkv");

        await Handler().HandleAsync(Context(9, $$$"""{"relative_media_path":"bad.mkv","library_id":{{{library}}}}"""), CancellationToken.None);

        Assert.Equal(1, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_jobs WHERE job_kind = 'refiner.file.reject.v1'"));
        Assert.Equal(0, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_jobs WHERE job_kind = 'refiner.file.pass_through.v1'"));
        var reject = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT payload_json FROM refiner_jobs WHERE job_kind = 'refiner.file.reject.v1'"));
        Assert.Equal("preflight", PyConvert.Str(reject["failure_class"]));
        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events"));
        Assert.Equal((true, "failed"), (((PyBool)detail["reject_queued"]).Value, PyConvert.Str(detail["result"])));
        Assert.False(detail.ContainsKey("next_action"));
    }

    [Fact]
    public async Task The_hold_policy_queues_no_follow_up_and_the_holding_seam_never_does()
    {
        var library = await LibraryAsync(failurePolicy: "hold", maxAttempts: 1);
        _folders.Source("one.mkv");
        _media.DefaultProbe = FakeMediaRunner.EnglishAndJapanese;
        _media.RemuxError = "boom";
        await FileRowAsync(library, "one.mkv");

        await Handler().HandleAsync(Context(11, $$$"""{"relative_media_path":"one.mkv","library_id":{{{library}}}}"""), CancellationToken.None);
        Assert.Equal(0, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_jobs"));

        await LibraryAsync(failurePolicy: "pass_through", maxAttempts: 1);
        await FileRowAsync(await _fixture.Store.Scalar("SELECT id FROM refiner_libraries"), "one.mkv");
        await Handler(new HoldingFailurePolicy()).HandleAsync(Context(12, """{"relative_media_path":"one.mkv"}"""), CancellationToken.None);
        Assert.Equal(0, await _fixture.Store.Scalar("SELECT count(*) FROM refiner_jobs"));
    }

    [Theory]
    [InlineData("", "missing payload_json")]
    [InlineData("{nope", "invalid json: ")]
    [InlineData("[1]", "payload must be a JSON object")]
    [InlineData("""{"media_scope":"movie"}""", "relative_media_path is required")]
    [InlineData("""{"relative_media_path":"a.mkv","dry_run":false}""", "legacy Refiner dry_run")]
    public async Task A_payload_that_cannot_run_is_recorded_as_a_failed_check(string payload, string reason)
    {
        await LibraryAsync();

        await Handler().HandleAsync(Context(7, payload), CancellationToken.None);

        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events"));
        Assert.Equal("failed_before_execution", PyConvert.Str(detail["outcome"]));
        Assert.Contains(reason, PyConvert.Str(detail["reason"]), StringComparison.Ordinal);
        Assert.Empty(_media.Calls);
    }

    [Fact]
    public async Task A_library_whose_folders_cannot_be_used_fails_before_execution_with_its_reason()
    {
        var library = await LibraryAsync();
        await _fixture.Store.Execute("UPDATE refiner_libraries SET output_folder = ''");
        await FileRowAsync(library, "a.mkv");

        await Handler().HandleAsync(Context(8, $$"""{"relative_media_path":"a.mkv","library_id":{{library}},"trigger":"manual"}"""), CancellationToken.None);

        var detail = (PyDict)PyJsonParser.Parse(await ScalarText("SELECT detail FROM activity_events"));
        Assert.Contains("has no output folder set", PyConvert.Str(detail["reason"]), StringComparison.Ordinal);
        Assert.Equal("manual", PyConvert.Str(detail["trigger"]));
        Assert.Equal("processing_failed|preflight", await ScalarText("SELECT status || '|' || failure_class FROM refiner_files"));
    }

    [Fact]
    public async Task A_handler_crash_is_recorded_against_the_file_with_the_policy_applied()
    {
        var library = await LibraryAsync(maxAttempts: 1);
        await FileRowAsync(library, "crash.mkv");
        var recorder = new RemuxPassFailureRecorder(_fixture.Store.Database, new QueueingFailurePolicy(_fixture.Jobs), TimeProvider.System, NullLogger<RemuxPassFailureRecorder>.Instance);
        var payload = $$$"""{"relative_media_path":"crash.mkv","library_id":{{{library}}},"origin":{"source_key":"deluno","handoff_id":"h9"}}""";

        var willRetry = await recorder.RecordAsync(new UnhandledJobFailure(Context(1, payload), library, "movie", "crash.mkv", "boom"), CancellationToken.None);

        Assert.False(willRetry);
        Assert.Equal("processing_failed|unknown", await ScalarText("SELECT status || '|' || failure_class FROM refiner_files"));
        Assert.Contains("\"handoff_id\":\"h9\"", await ScalarText("SELECT payload_json FROM refiner_jobs WHERE job_kind = 'refiner.file.pass_through.v1'"), StringComparison.Ordinal);
        Assert.Null(await recorder.RecordAsync(new UnhandledJobFailure(Context(1, "{}"), null, "tv", null, "boom"), CancellationToken.None));
    }

    [Fact]
    public async Task The_worker_claims_remux_pass_jobs_once_the_handler_is_registered()
    {
        var registry = new JobHandlerRegistry([Handler()]);
        Assert.Equal([RemuxPassOutcomes.JobKind], registry.JobKinds);
        Assert.Contains(RemuxPassOutcomes.JobKind, ClaimableKinds.For(registry).HandledKinds);
        await Task.CompletedTask;
    }
}
