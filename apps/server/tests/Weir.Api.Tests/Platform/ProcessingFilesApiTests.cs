using System.Net;

namespace Weir.Api.Tests.Platform;

/// <summary>
/// End-to-end proof of the fix for #530 at the HTTP layer: <c>GET /processing/files</c> must answer 200 for a
/// row at <c>passed_through</c> or <c>rejected</c>, and the <c>file_status</c> query filter must accept
/// either value rather than 422. Also covers the everyday Processing Files list shape.
/// </summary>
public sealed class ProcessingFilesApiTests
{
    private static async Task<long> SeedLibraryAsync(WeirTestServer server, string name = "Movies bug530") =>
        await TestDatabase.ScalarAsync(
            server,
            "INSERT INTO libraries (name, media_type) VALUES ($name, 'movie') RETURNING id",
            ("$name", name));

    private static Task SeedFileAsync(WeirTestServer server, long libraryId, string relativePath, string status) =>
        TestDatabase.ExecuteAsync(
            server,
            "INSERT INTO files (library_id, relative_path, status, last_seen_at) VALUES ($lib, $path, $status, CURRENT_TIMESTAMP)",
            ("$lib", libraryId), ("$path", relativePath), ("$status", status));

    [Theory]
    [InlineData("passed_through")]
    [InlineData("rejected")]
    public async Task Filtering_by_either_bug_530_status_answers_200_not_422(string status)
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var libraryId = await SeedLibraryAsync(server);
        await SeedFileAsync(server, libraryId, "Movie (2020)/movie.mkv", status);

        using var response = await client.GetAsync($"/api/v1/processing/files?file_status={status}");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        var files = body!["files"]!.AsArray();
        var file = Assert.Single(files);
        Assert.Equal(status, file!["status"]!.GetValue<string>());
        Assert.Equal(1, body["status_counts"]![status]!.GetValue<int>());
    }

    [Fact]
    public async Task A_page_with_a_passed_through_file_alongside_others_answers_200_not_500()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var libraryId = await SeedLibraryAsync(server);
        await SeedFileAsync(server, libraryId, "a.mkv", "passed_through");
        await SeedFileAsync(server, libraryId, "b.mkv", "unprocessed");

        using var response = await client.GetAsync("/api/v1/processing/files");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.Equal(2, body!["returned"]!.GetValue<int>());
    }

    [Fact]
    public async Task An_invalid_file_status_is_still_rejected_with_422()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.GetAsync("/api/v1/processing/files?file_status=not_a_real_status");

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    [Fact]
    public async Task Creating_a_library_then_listing_it_round_trips_over_http()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var created = await client.PostAsync(
            "/api/v1/processing/libraries",
            new { csrf_token = await client.CsrfAsync(), name = "Anime", media_type = "movie", watched_folder = @"c:\anime-in", output_folder = @"c:\anime-out" });
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var createdBody = await ApiTestClient.Json(created);
        Assert.Equal("Anime", createdBody!["name"]!.GetValue<string>());
        Assert.Equal("no_upstream_signal", createdBody["manager_coverage"]!.GetValue<string>());

        using var list = await client.GetAsync("/api/v1/processing/libraries");
        Assert.Equal(HttpStatusCode.OK, list.StatusCode);
        var libraries = (await ApiTestClient.Json(list))!.AsArray();
        Assert.Contains(libraries, lib => lib!["name"]!.GetValue<string>() == "Anime");
    }

    [Fact]
    public async Task Two_libraries_with_overlapping_folders_are_refused_with_400()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var csrf = await client.CsrfAsync();
        await client.PostAsync("/api/v1/processing/libraries", new { csrf_token = csrf, name = "Anime", media_type = "movie", watched_folder = @"c:\anime-in", output_folder = @"c:\anime-out" });

        using var response = await client.PostAsync(
            "/api/v1/processing/libraries",
            new { csrf_token = await client.CsrfAsync(), name = "Anime 4K", media_type = "movie", watched_folder = @"c:\anime-out", output_folder = @"c:\anime4k-out" });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("overlap", await ApiTestClient.Detail(response), StringComparison.Ordinal);
    }
}
