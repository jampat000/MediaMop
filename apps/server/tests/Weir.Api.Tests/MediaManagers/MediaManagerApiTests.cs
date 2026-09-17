using System.Net;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using Weir.Infrastructure.MediaManagers;
using Weir.Api.Tests.Platform;
using static Weir.Api.Tests.Platform.ApiTestClient;

namespace Weir.Api.Tests.MediaManagers;

/// <summary>A scripted manager for the test server's outbound HTTP.</summary>
internal sealed class ScriptedManager : IManagerHttpHandlerFactory
{
    private readonly Dictionary<(string Method, string Path), Func<HttpRequestMessage, Task<HttpResponseMessage>>> _routes = new();

    public List<HttpRequestMessage> Requests { get; } = [];

    public ScriptedManager Route(HttpMethod method, string path, Func<HttpRequestMessage, Task<HttpResponseMessage>> respond)
    {
        _routes[(method.Method, path)] = respond;
        return this;
    }

    public ScriptedManager Json(HttpMethod method, string path, string json, HttpStatusCode status = HttpStatusCode.OK) =>
        Route(method, path, _ => Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(json) }));

    public HttpMessageHandler Handler(bool followRedirects) => new Recording(this);

    private sealed class Recording(ScriptedManager owner) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            lock (owner.Requests)
            {
                owner.Requests.Add(request);
            }

            return owner._routes.TryGetValue((request.Method.Method, request.RequestUri!.AbsolutePath), out var respond)
                ? respond(request)
                : throw new HttpRequestException("No connection could be made because the target machine actively refused it.");
        }
    }
}

/// <summary>
/// Ports of <c>test_media_manager_connections_api.py</c>, <c>test_media_manager_capabilities_api.py</c>,
/// <c>test_media_manager_intake_api.py</c>, <c>test_media_manager_handoff_status_api.py</c> and
/// <c>test_reconciliation_service.py</c> over the real HTTP pipeline, plus the #527 fix.
/// </summary>
public sealed class MediaManagerApiTests
{
    private const string Connections = "/api/v1/media-managers/connections";

    private static async Task<(WeirTestServer Server, ApiTestClient Client, ScriptedManager Manager)> StartAsync(params (string Name, string Value)[] variables)
    {
        var manager = new ScriptedManager();
        var server = await WeirTestServer.StartAsync(
            [("WEIR_SESSION_SECRET", Secret), ("WEIR_REFINER_WORKER_COUNT", "0"), ("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", ""), .. variables],
            configureServices: services => services.AddSingleton<IManagerHttpHandlerFactory>(manager));
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        var trusted = variables.FirstOrDefault(v => v.Name == "WEIR_TRUSTED_BROWSER_ORIGINS").Value;
        using var login = await client.PostAsync(
            "/api/v1/auth/login",
            new { username = "alice", password = AdminPassword, csrf_token = await client.CsrfAsync() },
            trusted is null ? null : new Dictionary<string, string> { ["Origin"] = trusted, ["X-Requested-With"] = "XMLHttpRequest" });
        Assert.Equal(HttpStatusCode.OK, login.StatusCode);
        return (server, client, manager);
    }

    private static async Task<JsonNode> CreateAsync(ApiTestClient client, string kind = "deluno", string name = "Deluno", string baseUrl = "http://10.1.1.142:5099", string apiKey = "deluno_secret_key")
    {
        using var response = await client.PostAsync(Connections, new { csrf_token = await client.CsrfAsync(), kind, name, base_url = baseUrl, api_key = apiKey });
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return await Json(response);
    }

    [Fact]
    public async Task A_connection_is_added_listed_updated_and_deleted_without_ever_returning_its_key()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;
        var row = await CreateAsync(client);
        Assert.Equal(
            """{"id":1,"kind":"deluno","name":"Deluno","enabled":true,"base_url":"http://10.1.1.142:5099","api_key_is_saved":true,"webhook_secret_is_set":false,"webhook_url_path":"/api/v1/intake/webhook/deluno","last_test_ok":null,"last_test_at":null,"last_test_detail":null,"lanes":[{"lane":"missing","enabled":false,"max_items_per_run":50,"retry_delay_minutes":1440,"schedule_enabled":false,"schedule_days":"","schedule_start":"00:00","schedule_end":"23:59","schedule_interval_seconds":3600},{"lane":"upgrade","enabled":false,"max_items_per_run":50,"retry_delay_minutes":1440,"schedule_enabled":false,"schedule_days":"","schedule_start":"00:00","schedule_end":"23:59","schedule_interval_seconds":3600}]}""",
            row.ToJsonString());
        await CreateAsync(client, "radarr", "Radarr", "http://10.1.1.5:7878");

        using (var unknown = await client.PostAsync(Connections, new { csrf_token = await client.CsrfAsync(), kind = "plex", name = "P" }))
        {
            Assert.Equal(HttpStatusCode.UnprocessableEntity, unknown.StatusCode);
            Assert.Equal("literal_error", (await Json(unknown))["detail"]![0]!["type"]!.GetValue<string>());
        }

        using (var duplicate = await client.PostAsync(Connections, new { csrf_token = await client.CsrfAsync(), kind = "radarr", name = "Deluno" }))
        {
            Assert.Equal((HttpStatusCode.BadRequest, "A connection named 'Deluno' already exists."), (duplicate.StatusCode, await Detail(duplicate)));
        }

        using (var badUrl = await client.PostAsync(Connections, new { csrf_token = await client.CsrfAsync(), kind = "radarr", name = "X", base_url = "not-a-url" }))
        {
            Assert.Contains("will not work", await Detail(badUrl), StringComparison.Ordinal);
        }

        using (var noToken = await client.PostAsync(Connections, new { csrf_token = "bad", kind = "radarr", name = "Y" }))
        {
            Assert.Equal((HttpStatusCode.BadRequest, "Invalid or expired CSRF token."), (noToken.StatusCode, await Detail(noToken)));
        }

        using (var extra = await client.PostAsync(Connections, new { csrf_token = await client.CsrfAsync(), kind = "radarr", name = "Z", surprise = 1 }))
        {
            Assert.Equal("extra_forbidden", (await Json(extra))["detail"]![0]!["type"]!.GetValue<string>());
        }

        using var listed = await client.GetAsync(Connections);
        Assert.Equal(["deluno", "radarr"], (await Json(listed)).AsArray().Select(r => r!["kind"]!.GetValue<string>()));

        using (var renamed = await client.PutAsync($"{Connections}/1", new { csrf_token = await client.CsrfAsync(), name = "Deluno renamed" }))
        {
            var body = await Json(renamed);
            Assert.Equal(("Deluno renamed", true), (body["name"]!.GetValue<string>(), body["api_key_is_saved"]!.GetValue<bool>()));
        }

        using (var cleared = await client.PutAsync($"{Connections}/1", new { csrf_token = await client.CsrfAsync(), api_key = "" }))
        {
            Assert.False((await Json(cleared))["api_key_is_saved"]!.GetValue<bool>());
        }

        using (var missing = await client.GetAsync($"{Connections}/99"))
        {
            Assert.Equal((HttpStatusCode.NotFound, "That media manager connection does not exist."), (missing.StatusCode, await Detail(missing)));
        }

        using (var zero = await client.GetAsync($"{Connections}/0"))
        {
            Assert.Equal("greater_than_equal", (await Json(zero))["detail"]![0]!["type"]!.GetValue<string>());
        }

        using var deleted = await client.SendAsync(HttpMethod.Delete, $"{Connections}/2", new { csrf_token = await client.CsrfAsync() });
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        Assert.Equal(0, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM media_manager_search_lanes WHERE connection_id = 2"));
    }

    [Fact]
    public async Task Routes_need_an_operator_session()
    {
        var (server, _, _) = await StartAsync();
        await using var _server = server;
        Assert.Equal(HttpStatusCode.Unauthorized, (await new ApiTestClient(server).GetAsync(Connections)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await new ApiTestClient(server).GetAsync("/api/v1/media-managers/capabilities")).StatusCode);
        await TestDatabase.SeedViewerAsync(server);
        var viewer = new ApiTestClient(server);
        await viewer.SignInAsync("bob", ViewerPassword);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.GetAsync(Connections)).StatusCode);
    }

    [Fact]
    public async Task A_lane_is_saved_per_manager_with_its_schedule_normalised()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;
        await CreateAsync(client);
        object Lane(string days, string start) => new { csrf_token = client.CsrfAsync().Result, enabled = true, max_items_per_run = 25, retry_delay_minutes = 60, schedule_enabled = true, schedule_days = days, schedule_start = start, schedule_end = "5:00", schedule_interval_seconds = 900 };
        using (var saved = await client.PutAsync($"{Connections}/1/lanes/missing", Lane("Mon,Tue", "1:00")))
        {
            var body = await Json(saved);
            Assert.Equal(("missing", true, "Mon,Tue", "01:00", "05:00"), (body["lane"]!.GetValue<string>(), body["enabled"]!.GetValue<bool>(), body["schedule_days"]!.GetValue<string>(), body["schedule_start"]!.GetValue<string>(), body["schedule_end"]!.GetValue<string>()));
        }

        using (var badDays = await client.PutAsync($"{Connections}/1/lanes/missing", Lane("monday", "01:00")))
        {
            Assert.Equal((HttpStatusCode.BadRequest, "Days must be written like Mon, Tue, Wed with commas between them."), (badDays.StatusCode, await Detail(badDays)));
        }

        using var badLane = await client.PutAsync($"{Connections}/1/lanes/sideways", Lane("Mon", "01:00"));
        Assert.Equal(("literal_error", "path"), ((await Json(badLane))["detail"]![0]!["type"]!.GetValue<string>(), (await Json(badLane))["detail"]![0]!["loc"]![0]!.GetValue<string>()));
    }

    /// <summary>
    /// #544 item 2: an invalid lane time (an hour past 23, or a value that is not even <c>HH:MM</c>) answered 500
    /// from an uncaught <c>PyValueErrorException</c>; it is now a 400 naming the field that could not be read.
    /// </summary>
    [Fact]
    public async Task An_invalid_lane_time_is_a_400_naming_the_field()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;
        await CreateAsync(client);
        object Lane(string start, string end) => new { csrf_token = client.CsrfAsync().Result, enabled = true, max_items_per_run = 25, retry_delay_minutes = 60, schedule_enabled = true, schedule_days = "Mon", schedule_start = start, schedule_end = end, schedule_interval_seconds = 900 };

        using (var badHour = await client.PutAsync($"{Connections}/1/lanes/missing", Lane("25:00", "23:59")))
        {
            Assert.Equal(HttpStatusCode.BadRequest, badHour.StatusCode);
            var detail = await Detail(badHour);
            Assert.StartsWith("schedule_start:", detail, StringComparison.Ordinal);
            Assert.Contains("0", detail, StringComparison.Ordinal);
        }

        using var notATime = await client.PutAsync($"{Connections}/1/lanes/missing", Lane("00:00", "9"));
        Assert.Equal(HttpStatusCode.BadRequest, notATime.StatusCode);
        Assert.StartsWith("schedule_end:", await Detail(notATime), StringComparison.Ordinal);

        // The lane was not left half-saved by the refused write: it still holds its untouched default.
        using var unchanged = await client.GetAsync($"{Connections}/1");
        var lane = (await Json(unchanged))["lanes"]!.AsArray().Single(l => l!["lane"]!.GetValue<string>() == "missing")!;
        Assert.Equal(("", "00:00", "23:59"), (lane["schedule_days"]!.GetValue<string>(), lane["schedule_start"]!.GetValue<string>(), lane["schedule_end"]!.GetValue<string>()));
    }

    [Fact]
    public async Task A_generated_secret_is_shown_once_and_the_webhook_then_enforces_it_for_that_manager_only()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;
        await CreateAsync(client);
        await CreateAsync(client, "radarr", "Radarr", "http://10.1.1.5:7878");
        using var generated = await client.PostAsync($"{Connections}/1/webhook-secret", new { csrf_token = await client.CsrfAsync() });
        var body = await Json(generated);
        var secret = body["webhook_secret"]!.GetValue<string>();
        Assert.Equal(("/api/v1/intake/webhook/deluno", "X-Webhook-Secret"), (body["webhook_url_path"]!.GetValue<string>(), body["header_name"]!.GetValue<string>()));
        using (var fetched = await client.GetAsync($"{Connections}/1"))
        {
            var text = await fetched.Content.ReadAsStringAsync();
            Assert.Contains("\"webhook_secret_is_set\":true", text, StringComparison.Ordinal);
            Assert.DoesNotContain(secret, text, StringComparison.Ordinal);
        }

        var anonymous = new ApiTestClient(server);
        var handoff = new { eventType = "deluno.processor-handoff", mediaType = "movies", sourcePath = "/x/y.mkv" };
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.PostAsync("/api/v1/intake/webhook/deluno", handoff)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.PostAsync("/api/v1/intake/webhook/deluno", handoff, new Dictionary<string, string> { ["X-Webhook-Secret"] = "wrong" })).StatusCode);
        using var accepted = await anonymous.PostAsync("/api/v1/intake/webhook/deluno", handoff, new Dictionary<string, string> { ["X-Webhook-Secret"] = secret });
        Assert.Equal(HttpStatusCode.BadRequest, accepted.StatusCode);
        Assert.Contains("watched folder", await Detail(accepted), StringComparison.Ordinal);
        Assert.Equal(HttpStatusCode.OK, (await anonymous.PostAsync("/api/v1/intake/webhook/radarr", new { eventType = "Grab" })).StatusCode);
    }

    [Fact]
    public async Task A_connection_test_reports_unreachable_refused_and_removed_meanwhile()
    {
        var (server, client, manager) = await StartAsync();
        await using var _server = server;
        await CreateAsync(client, baseUrl: "http://127.0.0.1:1");
        using (var unreachable = await client.PostAsync($"{Connections}/1/test", new { csrf_token = await client.CsrfAsync() }))
        {
            var body = await Json(unreachable);
            Assert.False(body["ok"]!.GetValue<bool>());
            Assert.Equal("Weir could not reach Deluno at http://127.0.0.1:1. Check the address is right, and that the app is running and reachable from this machine.", body["detail"]!.GetValue<string>());
            Assert.EndsWith("Z", body["checked_at"]!.GetValue<string>(), StringComparison.Ordinal);
        }

        using (var saved = await client.GetAsync($"{Connections}/1"))
        {
            var body = await Json(saved);
            Assert.False(body["last_test_ok"]!.GetValue<bool>());
            Assert.DoesNotContain("Z", body["last_test_at"]!.GetValue<string>(), StringComparison.Ordinal);
        }

        manager.Json(HttpMethod.Get, "/api/integrations/external/health", "{}", HttpStatusCode.Forbidden);
        using (var refused = await client.PostAsync($"{Connections}/1/test", new { csrf_token = await client.CsrfAsync() }))
        {
            Assert.Equal("Weir reached Deluno, but the API key was refused. Check the key and save it again.", (await Json(refused))["detail"]!.GetValue<string>());
        }

        manager.Route(HttpMethod.Get, "/api/integrations/external/health", async _ =>
        {
            await TestDatabase.ExecuteAsync(server, "DELETE FROM media_manager_search_lanes; DELETE FROM media_manager_connections;");
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("""{"status":"ok"}""") };
        });
        using var removed = await client.PostAsync($"{Connections}/1/test", new { csrf_token = await client.CsrfAsync() });
        Assert.Equal((HttpStatusCode.NotFound, "That media manager connection was removed while its connection test was running."), (removed.StatusCode, await Detail(removed)));
    }

    /// <summary>
    /// #544 item 1: a manager answering 2xx with a body that is not JSON (a reverse proxy's HTML login page,
    /// most often) made the connection test 500 from an uncaught JSON-decode exception; it is now reported as a
    /// plain, unsuccessful test result.
    /// </summary>
    [Fact]
    public async Task A_connection_test_classifies_a_2xx_non_json_answer_instead_of_crashing()
    {
        var (server, client, manager) = await StartAsync();
        await using var _server = server;
        await CreateAsync(client, "radarr", "Radarr", "http://10.1.1.5:7878");
        manager.Json(HttpMethod.Get, "/api/v3/system/status", "<html>this is a login page, not Radarr</html>");
        using var tested = await client.PostAsync($"{Connections}/1/test", new { csrf_token = await client.CsrfAsync() });
        Assert.Equal(HttpStatusCode.OK, tested.StatusCode);
        var body = await Json(tested);
        Assert.False(body["ok"]!.GetValue<bool>());
        Assert.Equal(
            "Weir reached Radarr but did not get the answer it expected. Check the address points at the app itself, not a page inside it.",
            body["detail"]!.GetValue<string>());
    }

    [Fact]
    public async Task Capabilities_report_what_each_credentialed_manager_manages()
    {
        var (server, client, manager) = await StartAsync();
        await using var _server = server;
        manager.Json(HttpMethod.Get, "/api/integrations/external/manifest", """{"libraries":[{"id":"lib-movies","name":"Movies","mediaType":"movies","path":"/media/movies"},{"id":"lib-tv","name":"TV","mediaType":"tv","path":"/media/tv"}]}""");
        await CreateAsync(client, name: "Main");
        await CreateAsync(client, name: "No key", apiKey: "");
        using var response = await client.GetAsync("/api/v1/media-managers/capabilities");
        Assert.Equal(
            """[{"connection_id":1,"kind":"deluno","name":"Main","label":"Deluno (Main)","media_scopes":["movie","tv"],"reports_import_queue":true,"reports_library_truth":false,"reachable":true,"library_roots":["/media/movies","/media/tv"],"summary":"Looks after Movies and TV episodes. Weir can ask it what is mid-import, but not which files it still keeps, so folder cleanup stays off unless another manager can answer that.","detail":null}]""",
            await response.Content.ReadAsStringAsync());
        Assert.Equal("deluno_secret_key", Assert.Single(manager.Requests).Headers.GetValues("X-Api-Key").Single());
    }

    [Fact]
    public async Task The_intake_webhook_ignores_what_is_not_its_business_and_names_unknown_sources()
    {
        var (server, _, _) = await StartAsync();
        await using var _server = server;
        var client = new ApiTestClient(server);
        using (var grab = await client.PostAsync("/api/v1/intake/webhook/sonarr", new { eventType = "Grab", episodes = new[] { new { id = 1 } } }))
        {
            Assert.Equal("""{"status":"ignored","source":"sonarr"}""", await grab.Content.ReadAsStringAsync());
        }

        using (var imported = await client.PostAsync("/api/v1/intake/webhook/RADARR", new { eventType = "Download", movie = new { id = 3, title = "Film", year = 2010 }, movieFile = new { path = "/media/m/f.mkv" } }))
        {
            Assert.Equal("""{"status":"ignored","source":"radarr","event":"imported"}""", await imported.Content.ReadAsStringAsync());
        }

        using (var unknown = await client.PostAsync("/api/v1/intake/webhook/plex", new { }))
        {
            Assert.Equal((HttpStatusCode.NotFound, "Unknown media manager source 'plex'. Known sources: deluno, native, radarr, sonarr. Use 'native' for a manager without a dialect of its own."), (unknown.StatusCode, await Detail(unknown)));
        }

        using var notADict = await client.SendAsync(HttpMethod.Post, "/api/v1/intake/webhook/native", content: TestDatabase.RawJson("[1]"));
        Assert.Equal("""{"detail":[{"type":"dict_type","loc":["body"],"msg":"Input should be a valid dictionary","input":[1]}]}""", await notADict.Content.ReadAsStringAsync());
        Assert.Equal(0, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM refiner_jobs WHERE job_kind = 'refiner.file.remux_pass.v1'"));
    }

    [Fact]
    public async Task A_configured_instance_secret_is_required_including_under_its_old_name()
    {
        foreach (var name in new[] { "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", "WEIR_SUBBER_WEBHOOK_SECRET" })
        {
            await using var server = await WeirTestServer.StartAsync([("WEIR_SESSION_SECRET", Secret), ("WEIR_REFINER_WORKER_COUNT", "0"), (name, "s3cret")]);
            var client = new ApiTestClient(server);
            Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsync("/api/v1/intake/webhook/radarr", new { eventType = "Grab" })).StatusCode);
            Assert.Equal(HttpStatusCode.OK, (await client.PostAsync("/api/v1/intake/webhook/radarr", new { eventType = "Grab" }, new Dictionary<string, string> { ["X-Webhook-Secret"] = "s3cret" })).StatusCode);
        }
    }

    [Fact]
    public async Task A_hand_off_is_queued_answered_for_and_cancelled_over_http()
    {
        var watched = Path.Join(Path.GetTempPath(), "weir-handoff-" + Guid.NewGuid().ToString("N"));
        var (server, _, _) = await StartAsync(("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", "s3cret"));
        await using var _server = server;
        await TestDatabase.ExecuteAsync(server, "UPDATE refiner_libraries SET watched_folder = $w WHERE media_type = 'movie'", ("$w", watched));
        var manager = new ApiTestClient(server);
        var secret = new Dictionary<string, string> { ["X-Webhook-Secret"] = "s3cret" };

        using (var noSecret = await manager.GetAsync("/api/v1/intake/capabilities"))
        {
            Assert.Equal((HttpStatusCode.Unauthorized, "Invalid or missing X-Webhook-Secret header."), (noSecret.StatusCode, await Detail(noSecret)));
        }

        Assert.Equal("""{"capabilities":["handoff-status","handoff-cancel"]}""", await (await manager.GetAsync("/api/v1/intake/capabilities", secret)).Content.ReadAsStringAsync());
        Assert.Equal(HttpStatusCode.NotFound, (await manager.GetAsync("/api/v1/intake/handoffs/deluno/h1", secret)).StatusCode);
        Assert.Equal("Unknown media manager source 'plex'.", await Detail(await manager.GetAsync("/api/v1/intake/handoffs/plex/h1", secret)));

        var handoff = new { eventType = "deluno.processor-handoff", handoffId = "h1", libraryId = "lib-1", mediaType = "movies", sourcePath = Path.Join(watched, "Film", "film.mkv"), callbackPath = "/api/integrations/processors/events" };
        using (var queued = await manager.PostAsync("/api/v1/intake/webhook/deluno", handoff, secret))
        {
            Assert.Equal("""{"status":"ok","source":"deluno","event":"handoff","media_scope":"movie","enqueued":"refiner.file.remux_pass.v1"}""", await queued.Content.ReadAsStringAsync());
        }

        using (var status = await manager.GetAsync("/api/v1/intake/handoffs/deluno/h1", secret))
        {
            var body = await Json(status);
            Assert.Equal(("queued", 1), (body["state"]!.GetValue<string>(), body["queuePosition"]!.GetValue<int>()));
            Assert.EndsWith("Z", body["lastChangedUtc"]!.GetValue<string>(), StringComparison.Ordinal);
        }

        using (var cancelled = await manager.SendAsync(HttpMethod.Delete, "/api/v1/intake/handoffs/deluno/h1", headers: secret))
        {
            Assert.Equal(HttpStatusCode.NoContent, cancelled.StatusCode);
            Assert.Null(cancelled.Content.Headers.ContentType);
        }

        Assert.Equal(1, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM activity_events WHERE event_type = 'refiner.handoff_cancelled' AND title = 'Deluno cancelled its hand-off of film.mkv'"));
        Assert.Equal("cancelled", (await Json(await manager.GetAsync("/api/v1/intake/handoffs/deluno/h1", secret)))["state"]!.GetValue<string>());
        using var again = await manager.SendAsync(HttpMethod.Delete, "/api/v1/intake/handoffs/deluno/h1", headers: secret);
        Assert.Equal((HttpStatusCode.Conflict, "This hand-off is cancelled, so Weir did not cancel it."), (again.StatusCode, await Detail(again)));
    }

    [Fact]
    public async Task Hand_off_routes_without_any_secret_say_what_to_set()
    {
        var (server, _, _) = await StartAsync();
        await using var _server = server;
        using var response = await new ApiTestClient(server).SendAsync(HttpMethod.Delete, "/api/v1/intake/handoffs/deluno/h1");
        Assert.Equal((HttpStatusCode.Forbidden, "Set a webhook secret in Weir so a media manager can ask about hand-offs."), (response.StatusCode, await Detail(response)));
    }

    [Fact]
    public async Task Issue_527_a_reconciliation_repair_needs_the_origin_check_and_a_csrf_token()
    {
        var (server, client, _) = await StartAsync(("WEIR_TRUSTED_BROWSER_ORIGINS", "http://weir.local"));
        await using var _server = server;
        var work = Path.Join(server.Home, "work");
        Directory.CreateDirectory(work);
        var artifact = Path.Join(work, ".movie.mkv.partial");
        await File.WriteAllTextAsync(artifact, "partial");
        await TestDatabase.ExecuteAsync(server, "UPDATE refiner_libraries SET work_folder = $w WHERE media_type = 'movie'", ("$w", work));
        var origin = new Dictionary<string, string> { ["Origin"] = "http://weir.local", ["X-Requested-With"] = "XMLHttpRequest" };

        using (var report = await client.GetAsync("/api/v1/system/reconciliation"))
        {
            var issue = (await Json(report))["issues"]!.AsArray().Single(i => i!["kind"]!.GetValue<string>() == "partial_temp_artifact")!;
            Assert.Equal((artifact, true), (issue["path"]!.GetValue<string>(), issue["requires_confirmation"]!.GetValue<bool>()));
        }

        using (var noToken = await client.PostAsync("/api/v1/system/reconciliation/repair", new { action = "remove_refiner_temp_artifact", path = artifact, confirm = true }, origin))
        {
            Assert.Equal((HttpStatusCode.BadRequest, "Invalid or expired CSRF token."), (noToken.StatusCode, await Detail(noToken)));
        }

        using (var badOrigin = await client.PostAsync("/api/v1/system/reconciliation/repair", new { action = "remove_refiner_temp_artifact", path = artifact, confirm = true, csrf_token = await client.CsrfAsync() }, new Dictionary<string, string> { ["Origin"] = "http://evil.example", ["X-Requested-With"] = "XMLHttpRequest" }))
        {
            Assert.Equal((HttpStatusCode.Forbidden, "Origin not allowed."), (badOrigin.StatusCode, await Detail(badOrigin)));
        }

        Assert.True(File.Exists(artifact));
        using (var unconfirmed = await client.PostAsync("/api/v1/system/reconciliation/repair", new { action = "remove_refiner_temp_artifact", path = artifact, confirm = false, csrf_token = await client.CsrfAsync() }, origin))
        {
            Assert.Equal(HttpStatusCode.BadRequest, unconfirmed.StatusCode);
            Assert.Contains("confirm=true", await Detail(unconfirmed), StringComparison.Ordinal);
        }

        using var applied = await client.PostAsync("/api/v1/system/reconciliation/repair", new { action = "remove_refiner_temp_artifact", path = artifact, confirm = true, csrf_token = await client.CsrfAsync() }, origin);
        Assert.Equal("""{"applied":true,"message":"Removed the temp artifact."}""", await applied.Content.ReadAsStringAsync());
        Assert.False(File.Exists(artifact));
        Assert.Equal(1, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM activity_events WHERE event_type = 'system.reconciliation.repair' AND detail = 'remove_refiner_temp_artifact: Removed the temp artifact.'"));
    }

    [Fact]
    public async Task Head_on_the_post_only_webhook_is_method_not_allowed()
    {
        await using var server = await WeirTestServer.StartAsync([("WEIR_SESSION_SECRET", Secret), ("WEIR_REFINER_WORKER_COUNT", "0"), ("WEIR_WEB_DIST", "")]);
        using var request = new HttpRequestMessage(HttpMethod.Head, "/api/v1/intake/webhook/deluno");
        Assert.Equal(HttpStatusCode.MethodNotAllowed, (await server.Client.SendAsync(request)).StatusCode);
    }
}
