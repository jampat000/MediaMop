using System.Net;
using System.Text;
using Microsoft.Extensions.DependencyInjection;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;

namespace Weir.Api.Tests.Platform;

/// <summary>Fixed ffprobe/ffmpeg paths that need not exist on disk — these tests fake the process, not the tool lookup.</summary>
internal sealed class FixedMediaToolResolver : IMediaToolResolver
{
    public (string Ffprobe, string Ffmpeg) Resolve() => ("ffprobe", "ffmpeg");

    public string? ResolveMkvmerge() => null;
}

/// <summary>Answers every ffprobe call with a fixed two-audio-track probe. These tests never run the worker
/// (<c>WEIR_PROCESSING_WORKER_COUNT=0</c>), so an ffmpeg call is not expected, but is answered harmlessly if made.</summary>
internal sealed class FixedProbeRunner : IProcessRunner
{
    public string Probe { get; set; } =
        """
        {"format":{"duration":"100.0"},"streams":[
          {"index":0,"codec_type":"video","codec_name":"h264","width":1920,"height":1080},
          {"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1}},
          {"index":2,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"jpn"}}
        ]}
        """;

    public Task<ProcessResult> RunAsync(ProcessRequest request, CancellationToken cancellationToken = default)
    {
        var argv = request.Argv;
        if (argv.Count > 0 && argv[0] == "ffprobe")
        {
            return Task.FromResult(new ProcessResult { ExitCode = 0, Stdout = Encoding.UTF8.GetBytes(Probe), Stderr = [] });
        }

        return Task.FromResult(new ProcessResult { ExitCode = 0, Stdout = [], Stderr = [] });
    }
}

/// <summary>
/// End-to-end HTTP proof of issue #501: <c>GET /processing/files/{id}/tracks</c> lists a fresh probe with the rules'
/// verdict per stream, and <c>POST /processing/files/{id}/manual-plan</c> validates and queues an operator's choice.
/// </summary>
public sealed class ProcessingManualTrackApiTests
{
    private static async Task<(WeirTestServer Server, ApiTestClient Client, long FileId, string RelativePath)> StartWithHeldFileAsync()
    {
        var server = await WeirTestServer.StartAsync(
            [("WEIR_SESSION_SECRET", ApiTestClient.Secret), ("WEIR_PROCESSING_WORKER_COUNT", "0")],
            configureServices: services =>
            {
                services.AddSingleton<IProcessRunner>(new FixedProbeRunner());
                services.AddSingleton<IMediaToolResolver>(new FixedMediaToolResolver());
            });
        await TestDatabase.SeedAdminAsync(server);

        var watched = Directory.CreateDirectory(Path.Join(server.Home, "watched")).FullName;
        var output = Directory.CreateDirectory(Path.Join(server.Home, "output")).FullName;
        const string relative = "Show (2020)/episode.mkv";
        Directory.CreateDirectory(Path.Join(watched, "Show (2020)"));
        await File.WriteAllBytesAsync(Path.Join(watched, "Show (2020)", "episode.mkv"), new byte[2048]);

        var libraryId = await TestDatabase.ScalarAsync(
            server,
            "INSERT INTO libraries (name, media_type, watched_folder, output_folder) VALUES ($name, 'movie', $watched, $output) RETURNING id",
            ("$name", "Movies #501"), ("$watched", watched), ("$output", output));
        var fileId = await TestDatabase.ScalarAsync(
            server,
            "INSERT INTO files (library_id, relative_path, status, last_seen_at) VALUES ($lib, $path, 'on_hold', CURRENT_TIMESTAMP) RETURNING id",
            ("$lib", libraryId), ("$path", relative));

        var client = new ApiTestClient(server);
        await client.SignInAsync();
        return (server, client, fileId, relative);
    }

    [Fact]
    public async Task Getting_tracks_requires_sign_in()
    {
        var (server, _, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;
        var anonymous = new ApiTestClient(server);

        using var response = await anonymous.GetAsync($"/api/v1/processing/files/{fileId}/tracks");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task Getting_tracks_returns_every_stream_with_the_rules_verdict()
    {
        var (server, client, fileId, relative) = await StartWithHeldFileAsync();
        await using var disposable = server;

        using var response = await client.GetAsync($"/api/v1/processing/files/{fileId}/tracks");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.Equal(relative, body!["relative_path"]!.GetValue<string>());
        var streams = body["streams"]!.AsArray();
        Assert.Equal(3, streams.Count);

        var english = streams.Single(s => s!["index"]!.GetValue<int>() == 1);
        Assert.Equal("audio", english!["type"]!.GetValue<string>());
        Assert.True(english["rule_would_keep"]!.GetValue<bool>());

        var japanese = streams.Single(s => s!["index"]!.GetValue<int>() == 2);
        Assert.False(japanese!["rule_would_keep"]!.GetValue<bool>());
        Assert.Contains("not selected", japanese["rule_reason"]!.GetValue<string>(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Manual_plan_needs_an_operator_role()
    {
        var (server, _, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;
        await TestDatabase.SeedViewerAsync(server);
        var viewer = new ApiTestClient(server);
        await viewer.SignInAsync("bob", ApiTestClient.ViewerPassword);

        using var response = await viewer.PostAsync(
            $"/api/v1/processing/files/{fileId}/manual-plan",
            new { csrf_token = await viewer.CsrfAsync(), keep = new object[] { new { index = 0 }, new { index = 1, @default = true } }, order = new[] { 0, 1 } });

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Manual_plan_needs_a_valid_csrf_token()
    {
        var (server, client, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;

        using var response = await client.PostAsync(
            $"/api/v1/processing/files/{fileId}/manual-plan",
            new { csrf_token = "not-a-real-token", keep = new object[] { new { index = 0 }, new { index = 1, @default = true } }, order = new[] { 0, 1 } });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Manual_plan_with_no_video_kept_is_rejected_with_400()
    {
        var (server, client, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;

        using var response = await client.PostAsync(
            $"/api/v1/processing/files/{fileId}/manual-plan",
            new { csrf_token = await client.CsrfAsync(), keep = new object[] { new { index = 1, @default = true } }, order = new[] { 1 } });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("video", await ApiTestClient.Detail(response), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Manual_plan_with_no_audio_kept_is_rejected_with_400()
    {
        var (server, client, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;

        using var response = await client.PostAsync(
            $"/api/v1/processing/files/{fileId}/manual-plan",
            new { csrf_token = await client.CsrfAsync(), keep = new object[] { new { index = 0 } }, order = new[] { 0 } });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("audio", await ApiTestClient.Detail(response), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Manual_plan_referencing_an_unknown_index_is_rejected_with_400()
    {
        var (server, client, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;

        using var response = await client.PostAsync(
            $"/api/v1/processing/files/{fileId}/manual-plan",
            new { csrf_token = await client.CsrfAsync(), keep = new object[] { new { index = 0 }, new { index = 99, @default = true } }, order = new[] { 0, 99 } });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task A_valid_manual_plan_is_queued_and_recorded_as_activity()
    {
        var (server, client, fileId, _) = await StartWithHeldFileAsync();
        await using var disposable = server;

        using var response = await client.PostAsync(
            $"/api/v1/processing/files/{fileId}/manual-plan",
            new { csrf_token = await client.CsrfAsync(), keep = new object[] { new { index = 0 }, new { index = 2, @default = true } }, order = new[] { 0, 2 } });

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.True(body!["ok"]!.GetValue<bool>());
        Assert.True(body["job_id"]!.GetValue<long>() > 0);

        var jobCount = await TestDatabase.ScalarAsync(server, "SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.file.remux_pass.v1'");
        Assert.Equal(1, jobCount);
        var activityCount = await TestDatabase.ScalarAsync(
            server, "SELECT COUNT(*) FROM activity_events WHERE event_type = 'processing.file_manual_plan_queued'");
        Assert.Equal(1, activityCount);
        var countedInEnglish = await TestDatabase.ScalarAsync(
            server,
            "SELECT COUNT(*) FROM activity_events WHERE event_type = 'processing.file_manual_plan_queued' AND instr(detail, ' chose 2 tracks to keep for ') > 0");
        Assert.Equal(1, countedInEnglish);
    }
}
