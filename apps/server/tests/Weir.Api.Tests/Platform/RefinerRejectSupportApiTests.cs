using System.Net;

namespace Weir.Api.Tests.Platform;

/// <summary>
/// The opt-in Reject failure policy's support gate over real HTTP (port of the relevant assertions in
/// <c>test_refiner_api_surface.py</c>): <c>GET /refiner/reject-support</c>, and the same check refusing an
/// unsupported save at <c>POST</c>/<c>PUT /refiner/libraries</c>.
/// </summary>
public sealed class RefinerRejectSupportApiTests
{
    [Fact]
    public async Task No_connections_named_reports_unavailable_with_a_reason()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.GetAsync("/api/v1/refiner/reject-support");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.False(body!["available"]!.GetValue<bool>());
        Assert.Contains("Link a media manager", body["reason"]!.GetValue<string>(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_radarr_connection_always_reports_available()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var connectionId = await CreateRadarrConnectionAsync(client);

        using var response = await client.GetAsync($"/api/v1/refiner/reject-support?connection_ids={connectionId}");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.True(body!["available"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Saving_a_library_with_reject_and_no_supporting_manager_is_refused_with_400()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/refiner/libraries",
            new
            {
                csrf_token = await client.CsrfAsync(),
                name = "Anime",
                media_type = "movie",
                watched_folder = @"c:\anime-in",
                output_folder = @"c:\anime-out",
                failure_policy = "reject",
            });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("cannot use Reject yet", await ApiTestClient.Detail(response), StringComparison.Ordinal);

        using var list = await client.GetAsync("/api/v1/refiner/libraries");
        var libraries = (await ApiTestClient.Json(list))!.AsArray();
        Assert.DoesNotContain(libraries, lib => lib!["name"]!.GetValue<string>() == "Anime");
    }

    [Fact]
    public async Task Saving_a_library_with_reject_and_a_radarr_connection_is_accepted()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var connectionId = await CreateRadarrConnectionAsync(client);

        using var response = await client.PostAsync(
            "/api/v1/refiner/libraries",
            new
            {
                csrf_token = await client.CsrfAsync(),
                name = "Anime",
                media_type = "movie",
                watched_folder = @"c:\anime-in",
                output_folder = @"c:\anime-out",
                failure_policy = "reject",
                manager_connection_ids = new[] { connectionId },
            });

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.Equal("reject", body!["failure_policy"]!.GetValue<string>());
    }

    private static async Task<long> CreateRadarrConnectionAsync(ApiTestClient client)
    {
        using var response = await client.PostAsync(
            "/api/v1/media-managers/connections",
            new { csrf_token = await client.CsrfAsync(), kind = "radarr", name = "Radarr", base_url = "http://10.0.0.5:7878", api_key = "k" });
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        return body!["id"]!.GetValue<long>();
    }
}
