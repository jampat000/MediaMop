using System.Globalization;
using System.Net;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Api.Endpoints;
using Weir.Core.Activity;
using static Weir.Api.Tests.Platform.ApiTestClient;

namespace Weir.Api.Tests.Platform;

/// <summary>Ports of <c>test_activity_history.py</c> (the API half) and <c>test_activity_stream.py</c>, on a real temp SQLite database.</summary>
public sealed class ActivityApiTests
{
    private static readonly (string Title, string Detail)[] HistoryRows =
    [
        ("Heat was handed back", "{\"trigger\": \"scheduled\", \"library_id\": 1, \"relative_media_path\": \"Heat/heat.mkv\"}"),
        ("Heat failed", "{\"trigger\": \"retry\", \"ok\": false, \"library_id\": 1, \"relative_media_path\": \"Heat/heat.mkv\"}"),
        ("Alien processed", "{\"trigger\": \"manual\", \"library_id\": 1, \"relative_media_path\": \"Alien/alien.mkv\"}"),
        ("Show processed", "{\"trigger\": \"webhook\", \"library_id\": 2, \"relative_media_path\": \"Show/S01E01.mkv\"}"),
    ];

    [Fact]
    public async Task History_filters_on_why_how_where_and_which_file()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        Assert.Equal(["Show processed"], await TitlesAsync(client, "trigger=webhook"));
        Assert.Equal(["Heat failed"], await TitlesAsync(client, "result=failed"));
        Assert.Equal(["Show processed"], await TitlesAsync(client, "library_id=2"));
        Assert.Equal(["Heat failed", "Heat was handed back"], await TitlesAsync(client, "file=heat.mkv"));
        Assert.Equal(["Heat failed", "Heat was handed back"], await TitlesAsync(client, "file=HEAT.MKV"));
        Assert.Equal(["Alien processed"], await TitlesAsync(client, "search=alien"));
    }

    [Fact]
    public async Task The_page_is_told_how_far_back_history_goes()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var response = await client.GetAsync("/api/v1/activity/recent?module=refiner");
        var body = await Json(response);
        Assert.Equal(90, body["retention_days"]!.GetValue<int>());
        Assert.NotNull(body["oldest_event_at"]);
        Assert.NotEmpty(body["items"]![0]!["relative_path"]!.GetValue<string>());
        Assert.Equal(4, body["total"]!.GetValue<int>());
        Assert.Equal(1, body["system_events"]!.GetValue<int>());
        Assert.False(body["has_more"]!.GetValue<bool>());
        var item = body["items"]![0]!.AsObject();
        Assert.Equal(
            ["id", "created_at", "event_type", "module", "title", "detail", "trigger", "result", "library_id", "relative_path", "run_key"],
            item.Select(pair => pair.Key));
        Assert.Matches("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}$", item["created_at"]!.GetValue<string>());
    }

    [Fact]
    public async Task Paging_is_newest_first_and_before_id_continues()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var first = await client.GetAsync("/api/v1/activity/recent?module=refiner&limit=2");
        var page = await Json(first);
        Assert.True(page["has_more"]!.GetValue<bool>());
        Assert.Equal(4, page["total"]!.GetValue<int>());
        var ids = page["items"]!.AsArray().Select(item => item!["id"]!.GetValue<long>()).ToList();
        Assert.Equal(2, ids.Count);

        using var next = await client.GetAsync($"/api/v1/activity/recent?module=refiner&limit=2&before_id={ids.Min()}");
        var rest = (await Json(next))["items"]!.AsArray().Select(item => item!["id"]!.GetValue<long>()).ToList();
        Assert.All(rest, id => Assert.True(id < ids.Min()));
    }

    [Fact]
    public async Task Without_a_filter_the_total_is_pythons_fromless_count()
    {
        // Python's count replaces the selected columns with count(*), which drops FROM when nothing filters:
        // "SELECT count(*)" is 1, so the total is the page size and has_more is false. Ported as-is.
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var response = await client.GetAsync("/api/v1/activity/recent?limit=2");
        var body = await Json(response);
        Assert.Equal(2, body["total"]!.GetValue<int>());
        Assert.False(body["has_more"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Query_validation_and_dates_answer_as_fastapi_does()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var limit = await client.GetAsync("/api/v1/activity/recent?limit=0&module=");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, limit.StatusCode);
        Assert.Equal(
            "{\"detail\":[{\"type\":\"greater_than_equal\",\"loc\":[\"query\",\"limit\"],\"msg\":\"Input should be greater than or equal to 1\",\"input\":\"0\",\"ctx\":{\"ge\":1}}," +
            "{\"type\":\"string_too_short\",\"loc\":[\"query\",\"module\"],\"msg\":\"String should have at least 1 character\",\"input\":\"\",\"ctx\":{\"min_length\":1}}]}",
            await limit.Content.ReadAsStringAsync());

        using var format = await client.GetAsync("/api/v1/activity/export?format=xml");
        Assert.Equal(
            "{\"detail\":[{\"type\":\"string_pattern_mismatch\",\"loc\":[\"query\",\"format\"],\"msg\":\"String should match pattern '^(csv|json)$'\",\"input\":\"xml\",\"ctx\":{\"pattern\":\"^(csv|json)$\"}}]}",
            await format.Content.ReadAsStringAsync());

        using var badDate = await client.GetAsync("/api/v1/activity/recent?date_from=yesterday");
        Assert.Equal(HttpStatusCode.BadRequest, badDate.StatusCode);
        Assert.Equal("Invalid date_from.", await Detail(badDate));

        using var future = await client.GetAsync("/api/v1/activity/recent?module=refiner&date_from=2999-01-01T00:00:00Z");
        Assert.Empty((await Json(future))["items"]!.AsArray());

        using var missing = await client.GetAsync("/api/v1/activity/file-history");
        Assert.Equal(
            "{\"detail\":[{\"type\":\"missing\",\"loc\":[\"query\",\"relative_path\"],\"msg\":\"Field required\",\"input\":null}]}",
            await missing.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task A_filtered_range_exports_as_csv_and_json()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var csv = await client.GetAsync("/api/v1/activity/export?format=csv&file=heat.mkv");
        Assert.Equal(HttpStatusCode.OK, csv.StatusCode);
        Assert.Matches("^attachment; filename=\"weir-activity-\\d{8}-\\d{6}\\.csv\"$", Header(csv, "Content-Disposition"));
        Assert.Equal("text/csv; charset=utf-8", Header(csv, "Content-Type"));
        Assert.Equal("50000", Header(csv, "X-Weir-Export-Limit"));
        Assert.Equal("2", Header(csv, "X-Weir-Export-Rows"));
        var lines = (await csv.Content.ReadAsStringAsync()).Split("\r\n");
        Assert.Equal("id,created_at,module,event_type,trigger,result,library_id,relative_path,title,detail", lines[0]);
        Assert.Contains(",refiner,refiner.file_remux_pass_completed,scheduled,success,1,Heat/heat.mkv,Heat was handed back,\"{\"\"trigger\"\": \"\"scheduled\"\"", lines[1], StringComparison.Ordinal);
        Assert.Contains(",retry,failed,1,Heat/heat.mkv,Heat failed,", lines[2], StringComparison.Ordinal);
        Assert.Equal(string.Empty, lines[3]);

        using var json = await client.GetAsync("/api/v1/activity/export?format=json&trigger=manual&module=refiner");
        Assert.Equal("application/json", Header(json, "Content-Type"));
        var text = await json.Content.ReadAsStringAsync();
        Assert.StartsWith("[\n  {\n    \"id\": ", text, StringComparison.Ordinal);
        var records = JsonNode.Parse(text)!.AsArray();
        Assert.Equal(["Alien processed"], records.Select(record => record!["title"]!.GetValue<string>()));
        Assert.Equal(
            ["id", "created_at", "module", "event_type", "trigger", "result", "library_id", "relative_path", "title", "detail"],
            records[0]!.AsObject().Select(pair => pair.Key));

        using var none = await client.GetAsync("/api/v1/activity/export?format=json&trigger=startup");
        Assert.Equal("[]", await none.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Removing_one_files_history_says_what_goes_then_removes_only_that()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        var media = Path.Join(server.Home, "heat.mkv");
        await File.WriteAllTextAsync(media, "not touched");

        using var preview = await client.GetAsync("/api/v1/activity/file-history?relative_path=Heat/heat.mkv&library_id=1");
        Assert.Equal(HttpStatusCode.OK, preview.StatusCode);
        Assert.Equal(
            "{\"relative_path\":\"Heat/heat.mkv\",\"activity_events\":2,\"processing_records\":1,\"message\":\"This removes 2 Activity event(s) and 1 processing record(s) about Heat/heat.mkv. " +
            "It does not touch the file itself, its current status on the Files screen, or anything else's history.\"}",
            await preview.Content.ReadAsStringAsync());

        using var removed = await client.PostAsync(
            "/api/v1/activity/file-history/remove",
            new { csrf_token = await client.CsrfAsync(), relative_path = " Heat/heat.mkv ", library_id = 1 });
        Assert.Equal(HttpStatusCode.OK, removed.StatusCode);
        Assert.Equal("{\"relative_path\":\"Heat/heat.mkv\",\"activity_events_deleted\":2,\"processing_records_deleted\":1}", await removed.Content.ReadAsStringAsync());

        Assert.Equal(["Alien processed", "Show processed"], await TitlesAsync(client, string.Empty));
        Assert.Equal(1, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM refiner_file_logs WHERE relative_path = 'Alien/alien.mkv'"));
        Assert.Equal(1, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM refiner_file_logs"));
        Assert.Equal("not touched", await File.ReadAllTextAsync(media));
    }

    [Fact]
    public async Task Removing_history_needs_an_operator_and_a_fresh_token()
    {
        await using var server = await SeededServerAsync();
        await TestDatabase.SeedViewerAsync(server);
        var viewer = new ApiTestClient(server);
        await viewer.SignInAsync("bob", ViewerPassword);
        using var forbidden = await viewer.PostAsync("/api/v1/activity/file-history/remove", new { csrf_token = await viewer.CsrfAsync(), relative_path = "Heat/heat.mkv" });
        Assert.Equal(HttpStatusCode.Forbidden, forbidden.StatusCode);
        Assert.Equal("Forbidden.", await Detail(forbidden));

        var admin = await AdminAsync(server);
        using var stale = await admin.PostAsync("/api/v1/activity/file-history/remove", new { csrf_token = "stale", relative_path = "Heat/heat.mkv" });
        Assert.Equal(HttpStatusCode.BadRequest, stale.StatusCode);
        Assert.Equal("Your confirmation token expired. Refresh the page and try again.", await Detail(stale));
        Assert.Equal(6, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM activity_events"));
    }

    [Fact]
    public async Task Clearing_all_history_is_previewed_without_removing_anything()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var preview = await client.GetAsync("/api/v1/suite/operational-history/preview");
        var body = await Json(preview);
        Assert.Equal("preview", body["status"]!.GetValue<string>());
        using var recent = await client.GetAsync("/api/v1/activity/recent");
        Assert.Equal((await Json(recent))["total"]!.GetValue<long>(), body["activity_events_deleted"]!.GetValue<long>());
        Assert.Equal(4, (await TitlesAsync(client, string.Empty)).Count);
    }

    [Fact]
    public async Task Activity_routes_require_authentication()
    {
        await using var server = await SeededServerAsync();
        var anonymous = new ApiTestClient(server);
        foreach (var path in new[] { "/api/v1/activity/recent", "/api/v1/activity/stream", "/api/v1/activity/export", "/api/v1/activity/file-history?relative_path=a" })
        {
            using var response = await anonymous.GetAsync(path);
            Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
            Assert.Equal("Not authenticated.", await Detail(response));
        }
    }

    [Fact]
    public async Task The_stream_emits_the_latest_id_and_a_newer_revision_after_a_new_event()
    {
        await using var server = await SeededServerAsync();
        var client = await AdminAsync(server);
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/activity/stream");
        request.Headers.Add("Cookie", string.Join("; ", client.Cookies.Select(pair => $"{pair.Key}={pair.Value}")));
        using var response = await server.Client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("text/event-stream; charset=utf-8", Header(response, "Content-Type"));
        Assert.Equal("no-store, no-cache", Header(response, "Cache-Control"));
        Assert.Equal("no", Header(response, "X-Accel-Buffering"));

        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync());
        Assert.Equal(["retry: 5000"], await NextBlockAsync(reader));
        var first = await NextBlockAsync(reader);
        Assert.Equal("event: activity.latest", first[0]);
        var latest = await TestDatabase.ScalarAsync(server, "SELECT max(id) FROM activity_events");
        Assert.Equal($"data: {{\"latest_event_id\":{latest},\"activity_revision\":{Revision(first)}}}", first[1]);

        var other = new ApiTestClient(server);
        await other.SignInAsync();
        var newest = await TestDatabase.ScalarAsync(server, "SELECT max(id) FROM activity_events");
        Assert.True(newest > latest);
        string[] block;
        do
        {
            block = await NextBlockAsync(reader);
        }
        while (!block[1].Contains($"\"latest_event_id\":{newest}", StringComparison.Ordinal));

        Assert.True(Revision(block) > Revision(first));
    }

    [Fact]
    public async Task The_stream_generator_emits_newer_ids_and_the_same_id_when_the_revision_changes()
    {
        var notifier = new ActivityLatestNotifier();
        using var cancel = new CancellationTokenSource();
        long?[] values = [10, 10, 11, 11];
        var reads = 0;
        var frames = new List<string>();
        await foreach (var frame in ActivityEndpoints.LatestFramesAsync(
            _ => Task.FromResult(reads < values.Length ? values[reads++] : 11),
            notifier,
            TimeProvider.System,
            TimeSpan.Zero,
            100,
            NullLogger.Instance,
            cancel.Token))
        {
            frames.Add(frame);
            if (frames.Count == 3)
            {
                notifier.Notify(11);
            }

            if (frames.Count == 4)
            {
                notifier.Notify(11);
            }

            if (frames.Count == 5)
            {
                break;
            }
        }

        Assert.Equal(
            [
                "retry: 5000\n\n",
                "event: activity.latest\ndata: {\"latest_event_id\":10,\"activity_revision\":0}\n\n",
                "event: activity.latest\ndata: {\"latest_event_id\":11,\"activity_revision\":0}\n\n",
                "event: activity.latest\ndata: {\"latest_event_id\":11,\"activity_revision\":1}\n\n",
                "event: activity.latest\ndata: {\"latest_event_id\":11,\"activity_revision\":2}\n\n",
            ],
            frames);
    }

    [Fact]
    public async Task The_stream_sends_keepalives_when_nothing_changes()
    {
        var notifier = new ActivityLatestNotifier();
        var frames = new List<string>();
        await foreach (var frame in ActivityEndpoints.LatestFramesAsync(_ => Task.FromResult<long?>(null), notifier, TimeProvider.System, TimeSpan.Zero, 2, NullLogger.Instance, CancellationToken.None))
        {
            frames.Add(frame);
            if (frames.Count == 3)
            {
                break;
            }
        }

        Assert.Equal(["retry: 5000\n\n", ": keepalive\n\n", ": keepalive\n\n"], frames);
    }

    [Fact]
    public async Task Record_activity_event_does_not_prune_history_using_log_retention()
    {
        await using var server = await SeededServerAsync();
        await TestDatabase.ExecuteAsync(server, "UPDATE suite_settings SET log_retention_days = 1");
        await TestDatabase.ExecuteAsync(
            server,
            "INSERT INTO activity_events (created_at, event_type, module, title, detail, result) VALUES ($at, 'refiner.file_remux_pass_completed', 'refiner', 'Old Refiner result', '{}', 'success')",
            ("$at", DateTime.UtcNow.AddDays(-10).ToString("yyyy-MM-dd HH:mm:ss.ffffff", CultureInfo.InvariantCulture)));
        var client = await AdminAsync(server);
        using var response = await client.GetAsync("/api/v1/activity/recent?limit=100&module=refiner");
        Assert.Contains("Old Refiner result", (await Json(response))["items"]!.AsArray().Select(item => item!["title"]!.GetValue<string>()));
    }

    private static long Revision(string[] block)
    {
        var data = JsonNode.Parse(block[1]["data: ".Length..])!;
        return data["activity_revision"]!.GetValue<long>();
    }

    private static async Task<string[]> NextBlockAsync(StreamReader reader)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var block = new List<string>();
        while (true)
        {
            var line = await reader.ReadLineAsync(timeout.Token) ?? throw new InvalidOperationException("The stream ended.");
            if (line.Length == 0)
            {
                if (block.Count > 0)
                {
                    return [.. block];
                }

                continue;
            }

            if (!line.StartsWith(':'))
            {
                block.Add(line);
            }
        }
    }

    /// <summary>The four Refiner results written through the server's own Activity writer, and two processing records.</summary>
    private static async Task<WeirTestServer> SeededServerAsync()
    {
        var server = await StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var writer = server.Services.GetRequiredService<IActivityWriter>();
        foreach (var (title, detail) in HistoryRows)
        {
            await writer.RecordAsync(new ActivityEventDraft(ActivityEventTypes.RefinerFileRemuxPassCompleted, "refiner", title, detail));
        }

        foreach (var path in new[] { "Heat/heat.mkv", "Alien/alien.mkv" })
        {
            await TestDatabase.ExecuteAsync(server, "INSERT INTO refiner_file_logs (library_id, relative_path, title, recorded_at) VALUES (1, $p, 'pass', CURRENT_TIMESTAMP)", ("$p", path));
        }

        return server;
    }

    private static async Task<ApiTestClient> AdminAsync(WeirTestServer server)
    {
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        return client;
    }

    private static async Task<List<string>> TitlesAsync(ApiTestClient client, string query)
    {
        using var response = await client.GetAsync("/api/v1/activity/recent?module=refiner" + (query.Length > 0 ? "&" + query : string.Empty));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return [.. (await Json(response))["items"]!.AsArray().Select(item => item!["title"]!.GetValue<string>()).Order(StringComparer.Ordinal)];
    }
}
