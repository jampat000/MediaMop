using System.Net;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Tests.MediaManagers;

/// <summary>
/// The orchestrator behind issue #507: after a library-mode swap, tell every manager that owns the changed
/// file, retrying transient failures before recording a warning, and coalescing a batch into one rescan.
/// </summary>
public sealed class LibraryFileChangeNotifierTests
{
    private static LibraryFileChangeNotifier Notifier(MediaManagerFixture fixture, Func<int, CancellationToken, Task>? delay = null) =>
        new(fixture.Connections, fixture.Store.Database, new SqliteActivityWriter(fixture.Store.Database), fixture.Store.Clock, delay: delay ?? ((_, _) => Task.CompletedTask));

    [Fact]
    public async Task A_batch_of_ten_episodes_produces_one_rescan_series_call()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("sonarr", "Main");
        var episodePaths = Enumerable.Range(1, 10).Select(i => $"/tv/Show/S01/e{i:00}.mkv").ToArray();
        fixture.Http
            .Json(HttpMethod.Get, "/api/v3/rootfolder", "[]")
            .Json(HttpMethod.Get, "/api/v3/series", """[{"id":12,"title":"Show"}]""")
            .Json(HttpMethod.Get, "/api/v3/episodefile", $$"""[{{string.Join(",", episodePaths.Select(p => $$"""{"path":"{{p}}"}"""))}}]""")
            .Json(HttpMethod.Post, "/api/v3/command", """{"id":1}""", HttpStatusCode.Created);

        var notifier = Notifier(fixture);
        foreach (var path in episodePaths)
        {
            await notifier.NotifyAsync(new LibraryFileChange("tv", path, Reason: "removed 2 audio tracks"));
        }

        Assert.Single(fixture.Http.RequestsTo(HttpMethod.Post, "/api/v3/command"));
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'library.file_change_notified'"));
    }

    [Fact]
    public async Task A_second_batch_after_the_coalesce_window_rescans_again()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("sonarr", "Main");
        fixture.Http
            .Json(HttpMethod.Get, "/api/v3/rootfolder", "[]")
            .Json(HttpMethod.Get, "/api/v3/series", """[{"id":12,"title":"Show"}]""")
            .Json(HttpMethod.Get, "/api/v3/episodefile", """[{"path":"/tv/Show/S01/e01.mkv"},{"path":"/tv/Show/S01/e02.mkv"}]""")
            .Json(HttpMethod.Post, "/api/v3/command", """{"id":1}""", HttpStatusCode.Created);

        var notifier = Notifier(fixture);
        await notifier.NotifyAsync(new LibraryFileChange("tv", "/tv/Show/S01/e01.mkv"));
        fixture.Store.Clock.Set(fixture.Store.Clock.GetUtcNow() + LibraryFileChangeRules.CoalesceWindow + TimeSpan.FromSeconds(1));
        await notifier.NotifyAsync(new LibraryFileChange("tv", "/tv/Show/S01/e02.mkv"));

        Assert.Equal(2, fixture.Http.RequestsTo(HttpMethod.Post, "/api/v3/command").Count);
    }

    [Fact]
    public async Task A_notify_failure_is_retried_then_recorded_as_a_warning_and_the_call_still_completes()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("radarr", "4K");
        fixture.Http
            .Json(HttpMethod.Get, "/api/v3/rootfolder", "[]")
            .Json(HttpMethod.Get, "/api/v3/movie", """[{"id":7,"title":"Solaris","movieFile":{"path":"/media/Solaris/f.mkv"}}]""")
            .Json(HttpMethod.Post, "/api/v3/command", "server error", HttpStatusCode.InternalServerError);

        var delays = 0;
        var notifier = Notifier(fixture, delay: (_, _) => { delays++; return Task.CompletedTask; });
        await notifier.NotifyAsync(new LibraryFileChange("movie", "/media/Solaris/f.mkv"));

        Assert.Equal(3, fixture.Http.RequestsTo(HttpMethod.Post, "/api/v3/command").Count);
        Assert.Equal(2, delays);
        Assert.Equal(
            1,
            await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'library.file_change_notify_warning' AND title = 'Weir could not tell Radarr (4K) that f.mkv changed'"));
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE result = 'warning'"));
    }

    [Fact]
    public async Task Deluno_without_the_capability_is_skipped_with_a_note_and_makes_no_call()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("deluno", "Main");
        fixture.Http.Json(HttpMethod.Get, "/api/integrations/external/manifest", """{"libraries":[],"capabilities":["movies","tv"]}""");

        var notifier = Notifier(fixture);
        await notifier.NotifyAsync(new LibraryFileChange("movie", "/media/f.mkv"));

        Assert.Empty(fixture.Http.RequestsTo(HttpMethod.Post, "/api/integrations/external/file-changed"));
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'library.file_change_notify_skipped' AND result = 'skipped'"));
    }

    [Fact]
    public async Task Deluno_with_the_capability_is_told_directly_by_path()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("deluno", "Main");
        fixture.Http
            .Json(HttpMethod.Get, "/api/integrations/external/manifest", """{"libraries":[],"capabilities":["movies","tv","external-file-changed"]}""")
            .Json(HttpMethod.Post, "/api/integrations/external/file-changed", """{"path":"/media/f.mkv","coalesced":false,"titles":[]}""", HttpStatusCode.Accepted);

        var notifier = Notifier(fixture);
        await notifier.NotifyAsync(new LibraryFileChange("movie", "/media/f.mkv", Reason: "removed 2 audio tracks"));

        var request = Assert.Single(fixture.Http.RequestsTo(HttpMethod.Post, "/api/integrations/external/file-changed"));
        Assert.Equal("""{"path":"/media/f.mkv","tool":"Weir","reason":"removed 2 audio tracks"}""", PyJsonWriter.Dumps(request.Json!, PyJsonFormat.Compact));
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'library.file_change_notified'"));
    }

    [Fact]
    public async Task A_manager_that_does_not_hold_the_file_is_left_alone()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("radarr", "4K");
        fixture.Http
            .Json(HttpMethod.Get, "/api/v3/rootfolder", "[]")
            .Json(HttpMethod.Get, "/api/v3/movie", """[{"id":7,"title":"Solaris","movieFile":{"path":"/media/Solaris/f.mkv"}}]""");

        var notifier = Notifier(fixture);
        await notifier.NotifyAsync(new LibraryFileChange("movie", "/media/Someone/Else.mkv"));

        Assert.Empty(fixture.Http.RequestsTo(HttpMethod.Post, "/api/v3/command"));
        Assert.Equal(0, await fixture.Store.Scalar("SELECT count(*) FROM activity_events"));
    }

    [Fact]
    public async Task A_local_library_root_is_translated_to_the_managers_own_root_before_matching()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("radarr", "4K");
        fixture.Http
            .Json(HttpMethod.Get, "/api/v3/rootfolder", """[{"id":1,"path":"/mnt/movies"}]""")
            .Json(HttpMethod.Get, "/api/v3/movie", """[{"id":7,"title":"Solaris","movieFile":{"path":"/mnt/movies/Solaris/f.mkv"}}]""")
            .Json(HttpMethod.Post, "/api/v3/command", """{"id":1}""", HttpStatusCode.Created);

        var notifier = Notifier(fixture);
        await notifier.NotifyAsync(new LibraryFileChange("movie", @"D:\Data\Movies\Solaris\f.mkv", LocalLibraryRoot: @"D:\Data\Movies"));

        var command = Assert.Single(fixture.Http.RequestsTo(HttpMethod.Post, "/api/v3/command"));
        Assert.Equal("""{"name":"RescanMovie","movieId":7}""", PyJsonWriter.Dumps(command.Json!, PyJsonFormat.Compact));
    }
}
