using System.Net;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Tests.MediaManagers;

/// <summary>
/// <see cref="ArrManagerRedownload"/> (#509): request shapes verified against Sonarr/Radarr source (see the
/// class's remarks for citations), the destructive-step flag, the delete-then-search ordering, and the
/// unsupported paths (Deluno, no manager).
/// </summary>
public sealed class ArrManagerRedownloadTests
{
    private static ManagerConnection Connection(string kind) => new(kind, "Main", "http://manager.local", "k", 1);

    [Fact]
    public void Only_sonarr_and_radarr_report_support()
    {
        var redownload = new ArrManagerRedownload(new FakeManagerHttp());
        Assert.True(redownload.SupportsRedownload("radarr"));
        Assert.True(redownload.SupportsRedownload("sonarr"));
        Assert.False(redownload.SupportsRedownload("deluno"));
        Assert.False(redownload.SupportsRedownload("native"));
        Assert.False(redownload.SupportsRedownload(null));
        Assert.False(redownload.SupportsRedownload("made-up"));
    }

    [Fact]
    public async Task A_movie_with_an_existing_file_is_deleted_then_searched_for_and_the_destructive_step_is_flagged()
    {
        var http = new FakeManagerHttp()
            .Json(HttpMethod.Get, "/api/v3/movie/7", """{"id":7,"movieFile":{"id":42,"size":1500000000,"path":"/movies/Film/film.mkv"}}""")
            .Route(HttpMethod.Delete, "/api/v3/moviefile/42", _ => FakeManagerHttp.Response(HttpStatusCode.OK))
            .Route(HttpMethod.Post, "/api/v3/command", _ => FakeManagerHttp.Response(HttpStatusCode.Created, """{"id":1}"""));
        var redownload = new ArrManagerRedownload(http);

        var result = await redownload.RequestRedownloadAsync(Connection("radarr"), MediaManagerKinds.Movie, "7", "/movies/Film/film.mkv");

        Assert.Equal(RedownloadOutcome.Requested, result.Outcome);
        Assert.True(result.DeletedExistingFile);
        Assert.Equal(1500000000, result.ExistingFileSizeBytes);

        Assert.Equal(["/api/v3/movie/7", "/api/v3/moviefile/42", "/api/v3/command"], http.Requests.Select(r => r.PathAndQuery));
        var deleteRequest = http.RequestsTo(HttpMethod.Delete, "/api/v3/moviefile").Single();
        Assert.Empty(deleteRequest.Body);
        var searchRequest = http.RequestsTo(HttpMethod.Post, "/api/v3/command").Single();
        Assert.Equal("""{"name":"MoviesSearch","movieIds":[7]}""", PyJsonWriter.Dumps(searchRequest.Json!, PyJsonFormat.Compact));
    }

    [Fact]
    public async Task A_movie_with_no_existing_file_is_only_searched_for_never_deleted()
    {
        var http = new FakeManagerHttp()
            .Json(HttpMethod.Get, "/api/v3/movie/9", """{"id":9}""")
            .Route(HttpMethod.Post, "/api/v3/command", _ => FakeManagerHttp.Response(HttpStatusCode.Created, """{"id":2}"""));
        var redownload = new ArrManagerRedownload(http);

        var result = await redownload.RequestRedownloadAsync(Connection("radarr"), MediaManagerKinds.Movie, "9", "/movies/NoFile/film.mkv");

        Assert.Equal(RedownloadOutcome.Requested, result.Outcome);
        Assert.False(result.DeletedExistingFile);
        Assert.Null(result.ExistingFileSizeBytes);
        Assert.Empty(http.RequestsTo(HttpMethod.Delete, "/api/v3/moviefile"));
    }

    [Fact]
    public async Task A_series_episode_file_matched_by_path_is_deleted_then_the_whole_series_is_searched()
    {
        var http = new FakeManagerHttp()
            .Json(
                HttpMethod.Get,
                "/api/v3/episodefile",
                """[{"id":55,"size":900000000,"path":"/tv/Show/S01E01.mkv"},{"id":56,"size":123,"path":"/tv/Show/S01E02.mkv"}]""")
            .Route(HttpMethod.Delete, "/api/v3/episodefile/55", _ => FakeManagerHttp.Response(HttpStatusCode.OK))
            .Route(HttpMethod.Post, "/api/v3/command", _ => FakeManagerHttp.Response(HttpStatusCode.Created, """{"id":3}"""));
        var redownload = new ArrManagerRedownload(http);

        var result = await redownload.RequestRedownloadAsync(Connection("sonarr"), MediaManagerKinds.Tv, "3", "/tv/Show/S01E01.mkv");

        Assert.Equal(RedownloadOutcome.Requested, result.Outcome);
        Assert.True(result.DeletedExistingFile);
        Assert.Equal(900000000, result.ExistingFileSizeBytes);
        Assert.Empty(http.RequestsTo(HttpMethod.Delete, "/api/v3/episodefile/56"));

        var searchRequest = http.RequestsTo(HttpMethod.Post, "/api/v3/command").Single();
        Assert.Equal("""{"name":"SeriesSearch","seriesId":3}""", PyJsonWriter.Dumps(searchRequest.Json!, PyJsonFormat.Compact));
    }

    [Fact]
    public async Task A_search_failure_after_the_file_is_already_deleted_is_reported_not_thrown()
    {
        var http = new FakeManagerHttp()
            .Json(HttpMethod.Get, "/api/v3/movie/7", """{"id":7,"movieFile":{"id":42,"size":100,"path":"/movies/Film/film.mkv"}}""")
            .Route(HttpMethod.Delete, "/api/v3/moviefile/42", _ => FakeManagerHttp.Response(HttpStatusCode.OK))
            .Route(HttpMethod.Post, "/api/v3/command", _ => FakeManagerHttp.Response(HttpStatusCode.InternalServerError, "boom"));
        var redownload = new ArrManagerRedownload(http);

        var result = await redownload.RequestRedownloadAsync(Connection("radarr"), MediaManagerKinds.Movie, "7", "/movies/Film/film.mkv");

        Assert.Equal(RedownloadOutcome.DeletedButSearchFailed, result.Outcome);
        // The file is already gone: the destructive step must still be flagged even though the
        // request overall did not succeed, so a caller never loses track of a file that no longer exists.
        Assert.True(result.DeletedExistingFile);
        Assert.Contains("no file", result.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_search_failure_with_nothing_deleted_yet_throws_instead_of_being_swallowed()
    {
        var http = new FakeManagerHttp()
            .Json(HttpMethod.Get, "/api/v3/movie/9", """{"id":9}""")
            .Route(HttpMethod.Post, "/api/v3/command", _ => FakeManagerHttp.Response(HttpStatusCode.InternalServerError, "boom"));
        var redownload = new ArrManagerRedownload(http);

        await Assert.ThrowsAsync<MediaManagerHttpException>(
            () => redownload.RequestRedownloadAsync(Connection("radarr"), MediaManagerKinds.Movie, "9", "/movies/NoFile/film.mkv"));
    }

    [Fact]
    public async Task Deluno_and_a_scope_mismatch_are_unsupported_without_any_network_call()
    {
        var http = new FakeManagerHttp();
        var redownload = new ArrManagerRedownload(http);

        var delunoResult = await redownload.RequestRedownloadAsync(Connection("deluno"), MediaManagerKinds.Movie, "7", "/movies/Film/film.mkv");
        Assert.Equal(RedownloadOutcome.Unsupported, delunoResult.Outcome);
        Assert.False(delunoResult.DeletedExistingFile);

        var wrongScopeResult = await redownload.RequestRedownloadAsync(Connection("radarr"), MediaManagerKinds.Tv, "7", "/tv/Show/S01E01.mkv");
        Assert.Equal(RedownloadOutcome.Unsupported, wrongScopeResult.Outcome);

        Assert.Empty(http.Requests);
    }

    [Fact]
    public void No_manager_at_all_is_told_to_download_it_again_themselves()
    {
        Assert.False(ManagerRedownloadRules.KindSupportsRedownload(null));
        Assert.Contains("download it again yourself", ManagerRedownloadRules.NoManagerMessage, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void The_confirmation_states_the_file_is_replaced_before_a_replacement_exists_and_is_not_guaranteed()
    {
        var text = ManagerRedownloadRules.DestructiveConfirmation("Film (2020)", 1_500_000_000);
        Assert.Contains("deleted", text, StringComparison.Ordinal);
        Assert.Contains("no guarantee", text, StringComparison.Ordinal);
        Assert.Contains("GB", text, StringComparison.Ordinal);
    }
}
