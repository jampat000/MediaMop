using System.Net;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using Weir.Api.Tests.MediaManagers;
using Weir.Api.Tests.Platform;
using Weir.Infrastructure.MediaManagers;
using static Weir.Api.Tests.Platform.ApiTestClient;

namespace Weir.Api.Tests.Processing;

/// <summary>
/// <c>GET /api/v1/processing/manager-setup</c> over real HTTP, against a Sonarr and a Deluno scripted with the JSON their
/// real APIs return: the remote path mapping Sonarr needs and whether it has it, the folders Deluno reports, and that Weir
/// only ever reads — every request it makes is a GET.
/// </summary>
public sealed class ManagerSetupApiTests
{
    private const string Path = "/api/v1/processing/manager-setup";

    private const string SonarrClients = """
        [{"enable":true,"protocol":"torrent","priority":1,"removeCompletedDownloads":true,"removeFailedDownloads":true,"name":"qBittorrent",
          "fields":[{"order":0,"name":"host","label":"Host","value":"qbittorrent","type":"textbox","advanced":false,"privacy":"normal","isFloat":false},
                    {"order":1,"name":"port","label":"Port","value":8080,"type":"textbox","advanced":false,"privacy":"normal","isFloat":false},
                    {"order":6,"name":"tvCategory","label":"Category","value":"tv-sonarr","type":"textbox","advanced":false,"privacy":"normal","isFloat":false}],
          "implementationName":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings","tags":[],"id":1}]
        """;

    private const string DelunoManifest = """
        {"product":"Deluno","version":"v1","instanceName":"Deluno","capabilities":["movies","tv","pre-import-processing"],
         "libraries":[{"id":"lib-tv","name":"TV","mediaType":"tv","rootPath":"/media/tv","downloadsPath":"/media/downloads/complete/tv",
                       "importWorkflow":"refine-before-import","processorOutputPath":"/media/downloads/weir/tv","processorTimeoutMinutes":0,
                       "processorFailureMode":"import-original","missingSearchEnabled":true,"upgradeSearchEnabled":true,"maxItemsPerRun":10,
                       "automationStatus":"idle","cleanupMode":"keep-source","removeEmptySourceFolders":false}],
         "indexers":[],"downloadClients":[],"connections":[]}
        """;

    private static async Task<(WeirTestServer Server, ApiTestClient Client, ScriptedManager Manager)> StartAsync()
    {
        var manager = new ScriptedManager();
        var server = await WeirTestServer.StartAsync(
            [("WEIR_SESSION_SECRET", Secret), ("WEIR_PROCESSING_WORKER_COUNT", "0")],
            configureServices: services => services.AddSingleton<IManagerHttpHandlerFactory>(manager));
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        return (server, client, manager);
    }

    private static async Task ConnectAsync(ApiTestClient client, string kind, string name, string baseUrl)
    {
        using var response = await client.PostAsync("/api/v1/media-managers/connections", new Dictionary<string, object?>
        {
            ["csrf_token"] = await client.CsrfAsync(),
            ["kind"] = kind,
            ["name"] = name,
            ["base_url"] = baseUrl,
            ["api_key"] = "key",
        });
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
    }

    private static async Task<JsonArray> ManagersAsync(ApiTestClient client, string mediaType, string watched, string output, bool? removeOriginal = null)
    {
        var remove = removeOriginal is { } flag ? $"&remove_original_after_success={(flag ? "true" : "false")}" : string.Empty;
        using var response = await client.GetAsync(
            $"{Path}?media_type={mediaType}&watched_folder={Uri.EscapeDataString(watched)}&output_folder={Uri.EscapeDataString(output)}{remove}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = (await Json(response))!;
        Assert.Equal(mediaType, body["media_type"]!.GetValue<string>());
        return body["managers"]!.AsArray();
    }

    private static List<(string State, string Text)> Lines(JsonNode manager) =>
        [.. manager["lines"]!.AsArray().Select(line => (line!["state"]!.GetValue<string>(), line["text"]!.GetValue<string>()))];

    [Fact]
    public async Task Sonarr_gets_the_mapping_it_needs_and_a_plain_answer_about_whether_it_has_it()
    {
        var (server, client, manager) = await StartAsync();
        await using var _server = server;
        await ConnectAsync(client, "sonarr", "Sonarr", "http://192.0.2.60:8989");
        manager.Json(HttpMethod.Get, "/api/v3/remotepathmapping", "[]")
            .Json(HttpMethod.Get, "/api/v3/downloadclient", SonarrClients)
            .Json(HttpMethod.Get, "/api/v3/config/downloadclient", """{"downloadClientWorkingFolders":"_UNPACK_|_FAILED_","enableCompletedDownloadHandling":true,"autoRedownloadFailed":true,"id":1}""")
            .Json(HttpMethod.Get, "/api/v3/queue", """{"page":1,"pageSize":1000,"totalRecords":0,"records":[]}""");

        var missing = Assert.Single(await ManagersAsync(client, "tv", "/media/downloads/complete", "/media/downloads/weir"))!;

        Assert.Equal("sonarr", missing["kind"]!.GetValue<string>());
        Assert.Equal("remote_path_mapping", missing["flow"]!.GetValue<string>());
        Assert.False(missing["ready"]!.GetValue<bool>());
        Assert.Equal(["qbittorrent"], missing["mapping"]!["hosts"]!.AsArray().Select(host => host!.GetValue<string>()));
        Assert.Equal("/media/downloads/complete", missing["mapping"]!["remote_path"]!.GetValue<string>());
        Assert.Equal("/media/downloads/weir", missing["mapping"]!["local_path"]!.GetValue<string>());
        Assert.Contains(("problem", "Sonarr has no remote path mapping for /media/downloads/complete yet — add the one above."), Lines(missing));

        manager.Json(HttpMethod.Get, "/api/v3/remotepathmapping", """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""");
        var removing = Assert.Single(await ManagersAsync(client, "tv", "/media/downloads/complete", "/media/downloads/weir"))!;
        var keeping = Assert.Single(await ManagersAsync(client, "tv", "/media/downloads/complete", "/media/downloads/weir", removeOriginal: false))!;

        // qBittorrent seeds, so a library that removes originals would stop the import; one that keeps them is ready.
        Assert.False(removing["ready"]!.GetValue<bool>());
        Assert.Contains(
            ("problem", "Your download client seeds torrents. Turn off \"After cleaning, remove the original download\" so seeding keeps working and Sonarr can import."),
            Lines(removing));
        Assert.True(keeping["ready"]!.GetValue<bool>());
        Assert.All(manager.Requests, request => Assert.Equal(HttpMethod.Get, request.Method));
        Assert.All(manager.Requests, request => Assert.Equal("key", request.Headers.GetValues("X-Api-Key").Single()));
    }

    [Fact]
    public async Task A_sonarr_that_cannot_be_reached_says_so_and_a_movie_library_does_not_ask_sonarr_at_all()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;
        await ConnectAsync(client, "sonarr", "Sonarr", "http://192.0.2.60:8989");

        var tv = Assert.Single(await ManagersAsync(client, "tv", "/media/downloads/complete", "/media/downloads/weir"))!;
        var movies = await ManagersAsync(client, "movie", "/media/downloads/complete", "/media/downloads/weir");

        Assert.False(tv["ready"]!.GetValue<bool>());
        Assert.Contains("Sonarr", Assert.Single(Lines(tv)).Text, StringComparison.Ordinal);
        Assert.Empty(movies);
    }

    [Fact]
    public async Task Deluno_reports_the_folders_a_library_needs_and_nothing_to_map()
    {
        var (server, client, manager) = await StartAsync();
        await using var _server = server;
        await ConnectAsync(client, "deluno", "Deluno", "http://192.0.2.10:5099");
        manager.Json(HttpMethod.Get, "/api/integrations/external/manifest", DelunoManifest);

        var deluno = Assert.Single(await ManagersAsync(client, "tv", "/media/downloads/complete", "/media/downloads/weir/tv"))!;

        Assert.Equal("handoff", deluno["flow"]!.GetValue<string>());
        Assert.Null(deluno["mapping"]);
        Assert.Equal("/media/downloads/complete/tv", deluno["suggested_watched_folder"]!.GetValue<string>());
        Assert.Equal("/media/downloads/weir/tv", deluno["suggested_output_folder"]!.GetValue<string>());
        Assert.True(deluno["ready"]!.GetValue<bool>());
        Assert.All(manager.Requests, request => Assert.Equal(HttpMethod.Get, request.Method));
    }

    [Fact]
    public async Task A_library_removes_originals_unless_told_to_keep_them_and_says_which()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;

        async Task<JsonNode> CreateAsync(string name, bool? remove)
        {
            var body = new Dictionary<string, object?> { ["csrf_token"] = await client.CsrfAsync(), ["name"] = name, ["media_type"] = "tv" };
            if (remove is { } flag)
            {
                body["remove_original_after_success"] = flag;
            }

            using var response = await client.PostAsync("/api/v1/processing/libraries", body);
            Assert.Equal(HttpStatusCode.Created, response.StatusCode);
            return (await Json(response))!;
        }

        var byDefault = await CreateAsync("Shows default", null);
        var keeping = await CreateAsync("Shows seeding", false);
        using var read = await client.GetAsync($"/api/v1/processing/libraries/{keeping["id"]!.GetValue<long>()}");

        Assert.True(byDefault["remove_original_after_success"]!.GetValue<bool>());
        Assert.False(keeping["remove_original_after_success"]!.GetValue<bool>());
        Assert.False((await Json(read))!["remove_original_after_success"]!.GetValue<bool>());
    }

    [Fact]
    public async Task The_media_type_is_required_and_must_be_one_weir_knows()
    {
        var (server, client, _) = await StartAsync();
        await using var _server = server;

        using var missing = await client.GetAsync(Path);
        using var unknown = await client.GetAsync($"{Path}?media_type=music");

        Assert.Equal(HttpStatusCode.UnprocessableEntity, missing.StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, unknown.StatusCode);
    }
}
