using System.Globalization;
using System.Net;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Rules;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Tests.MediaManagers;

/// <summary>
/// Ports of <c>test_media_manager_binding.py</c>, <c>test_credentials_secret_crypto.py</c>, the reporting half of
/// <c>test_media_manager_completion_callback.py</c>, the provider tests in <c>test_refiner_original_language.py</c>, and the
/// intake, ledger and reconciliation behaviour behind the HTTP routes.
/// </summary>
public sealed class MediaManagerServiceTests
{
    // --- binding -------------------------------------------------------------------------------

    [Fact]
    public async Task A_scope_resolves_to_every_enabled_credentialed_connection_that_serves_it()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("radarr", "1080p");
        await fixture.AddConnectionAsync("radarr", "4K");
        await fixture.AddConnectionAsync("deluno", "Main");
        await fixture.AddConnectionAsync("sonarr", "Main TV");
        await fixture.AddConnectionAsync("radarr", "Off", enabled: false);
        await fixture.AddConnectionAsync("radarr", "Half", apiKey: null);

        var movies = await fixture.Db(uow => fixture.Connections.ConnectionsForScopeAsync(uow, "movie"));
        Assert.Equal(["Radarr (1080p)", "Radarr (4K)", "Deluno (Main)"], movies.Select(c => c.Label));
        var tv = await fixture.Db(uow => fixture.Connections.ConnectionsForScopeAsync(uow, "tv"));
        Assert.Equal(["Deluno (Main)", "Sonarr (Main TV)"], tv.Select(c => c.Label));
        Assert.Equal("key", movies[0].ApiKey);
    }

    [Fact]
    public async Task The_environment_applies_only_when_nothing_claims_the_scope()
    {
        using var environment = new MediaManagerFixture(("WEIR_ARR_RADARR_BASE_URL", "http://radarr.local"), ("WEIR_ARR_RADARR_API_KEY", "env-key"));
        var resolved = await environment.Db(uow => environment.Connections.ConnectionsForScopeAsync(uow, "movie"));
        Assert.Equal(("radarr", (long?)null), (Assert.Single(resolved).Kind, resolved[0].ConnectionId));

        await environment.AddConnectionAsync("radarr", "Half", apiKey: null);
        Assert.Empty(await environment.Db(uow => environment.Connections.ConnectionsForScopeAsync(uow, "movie")));
        await environment.AddConnectionAsync("radarr", "4K");
        Assert.Equal(["Radarr (4K)"], (await environment.Db(uow => environment.Connections.ConnectionsForScopeAsync(uow, "movie"))).Select(c => c.Label));
    }

    [Fact]
    public async Task Fan_out_asks_every_covering_connection_and_narrows_rows_to_the_scope()
    {
        using var fixture = new MediaManagerFixture();
        fixture.Http
            .Json(HttpMethod.Get, "/api/v3/queue", """{"records":[]}""")
            .Json(HttpMethod.Get, "/api/integrations/external/queue", """{"jobs":[{"mediaType":"movie","title":"a film"},{"mediaType":"tv","title":"an episode"}]}""");
        await fixture.AddConnectionAsync("radarr", "1080p");
        await fixture.AddConnectionAsync("deluno", "Main");
        var signals = await fixture.Db(uow => fixture.Connections.CollectQueueSignalsAsync(uow, "movie"));
        Assert.Equal(["Radarr (1080p)", "Deluno (Main)"], signals.Select(s => s.Connection.Label));
        Assert.Equal(["a film"], signals[1].Rows.Select(r => ((PyStr)r.Payload["title"]).Value));
        var byId = await fixture.Db(uow => fixture.Connections.CollectLibraryTruthAsync(uow, "movie", [2]));
        Assert.Equal(SignalStatus.NoSignal, Assert.Single(byId).Status);
    }

    [Fact]
    public async Task Credentials_survive_session_secret_rotation_and_previous_credentials_secrets()
    {
        using var fixture = new MediaManagerFixture();
        var old = new Core.Security.CredentialCipher("old-credentials-secret", "session-a", [], TimeProvider.System);
        var envelope = old.Encrypt("arr-key");
        Assert.Equal("credentials:v1", ((PyStr)((PyDict)PyJsonParser.Parse(envelope))["key_id"]).Value);
        var rotated = new Core.Security.CredentialCipher("new-credentials-secret", "session-b", ["old-credentials-secret"], TimeProvider.System);
        Assert.Equal("arr-key", rotated.Decrypt(envelope));
        var rewrapped = rotated.Rewrap(envelope)!;
        Assert.Equal("arr-key", new Core.Security.CredentialCipher("new-credentials-secret", "session-c", [], TimeProvider.System).Decrypt(rewrapped));
    }

    /// <summary>
    /// #544 item 1: a manager answering 2xx with a body that is not JSON (an HTML login page from a reverse
    /// proxy, most often) is classified as an unreachable answer with a plain message, not a 500 from an
    /// uncaught JSON-decode exception. Exercised through <c>describe_connections</c>, the same path
    /// <c>GET /media-managers/capabilities</c> uses.
    /// </summary>
    [Fact]
    public async Task A_2xx_non_json_answer_is_classified_not_a_crash()
    {
        using var fixture = new MediaManagerFixture();
        fixture.Http.Json(HttpMethod.Get, "/api/v3/rootfolder", "<html>this is a login page, not Radarr</html>");
        await fixture.AddConnectionAsync("radarr", "Radarr");
        var described = Assert.Single(await fixture.Db(uow => fixture.Connections.DescribeConnectionsAsync(uow)));
        Assert.Equal(SignalStatus.Unreachable, described.Status);
        Assert.Contains("did not give Weir the answer it expected", described.Detail, StringComparison.Ordinal);
        Assert.DoesNotContain("Exception", described.Detail, StringComparison.Ordinal);
    }

    /// <summary>
    /// #544 item 3: <c>create_connection</c>/<c>update_connection</c> let a plain <c>PyValueErrorException</c> from
    /// encrypting the API key escape uncaught when no secret is configured; it now becomes the same
    /// <see cref="MediaManagerConnectionException"/> (a 400) any other operator mistake here does, still naming
    /// the env var to set.
    /// </summary>
    [Fact]
    public async Task Saving_an_api_key_without_a_configured_secret_names_the_env_var()
    {
        using var fixture = new MediaManagerFixture();
        var noSecretCipher = new Core.Security.CredentialCipher(null, null, [], TimeProvider.System);
        var service = new MediaManagerConnectionService(fixture.Store.Options, noSecretCipher, fixture.Ports);

        var created = await Assert.ThrowsAsync<MediaManagerConnectionException>(
            () => fixture.Db(uow => service.CreateAsync(uow, "radarr", "No Secret", "http://10.1.1.5:7878", "some-api-key")));
        Assert.Equal(Core.Security.CredentialCipher.MissingSecretMessage, created.Message);
        Assert.Contains("WEIR_CREDENTIALS_SECRET", created.Message, StringComparison.Ordinal);
        Assert.Contains("WEIR_SESSION_SECRET", created.Message, StringComparison.Ordinal);

        // A connection with no key at all is unaffected: nothing needs encrypting.
        var id = await fixture.Db(uow => service.CreateAsync(uow, "radarr", "No Key Needed", "http://10.1.1.6:7878"));
        Assert.True(id > 0);

        var row = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!;
        var updated = await Assert.ThrowsAsync<MediaManagerConnectionException>(
            () => fixture.Db(async uow => { await service.UpdateAsync(uow, row, apiKey: "new-key"); return 0; }));
        Assert.Equal(Core.Security.CredentialCipher.MissingSecretMessage, updated.Message);
    }

    /// <summary>
    /// #544 item 5: matching is an exact prefix comparison, not the SQL <c>LIKE</c> Python's
    /// <c>.startswith()</c> compiled to — so <c>_</c> and <c>%</c> in a folder name are plain characters, and a
    /// sibling folder whose name merely resembles this one is not folded into the hand-off's files.
    /// </summary>
    [Fact]
    public async Task File_prefix_matching_for_a_hand_off_is_exact_not_a_sql_wildcard()
    {
        using var fixture = new MediaManagerFixture();
        var libraryId = await fixture.LibraryAsync("movie", fixture.Store.Home.Join("movies"));
        await fixture.Store.Execute($"INSERT INTO refiner_files (library_id, relative_path, status) VALUES ({libraryId}, 'Foo_Bar/real.mkv', 'processed')");
        // Under SQL LIKE, "Foo_Bar/%" wildcards the "_" and matches this unrelated sibling folder too — an exact
        // prefix compare never does, on any platform.
        await fixture.Store.Execute($"INSERT INTO refiner_files (library_id, relative_path, status) VALUES ({libraryId}, 'FooXBar/other.mkv', 'processing')");
        // A pure case difference is not the wildcard bug: it follows the documented OS path-semantics decision
        // (case-insensitive on Windows, case-sensitive elsewhere), same as SQLite's LIKE default happened to give
        // for ASCII — kept, not changed, by this fix.
        await fixture.Store.Execute($"INSERT INTO refiner_files (library_id, relative_path, status) VALUES ({libraryId}, 'FOO_BAR/upper.mkv', 'processing')");

        var row = new HandoffLedgerRow(1, "deluno", "h1", libraryId, "Foo_Bar", HandoffLedgerRules.Queued, null, null, null);
        var files = await fixture.Db(uow => HandoffLedgerStore.FileRowsAsync(uow, row));
        var expected = OperatingSystem.IsWindows() ? ["Foo_Bar/real.mkv", "FOO_BAR/upper.mkv"] : new[] { "Foo_Bar/real.mkv" };
        Assert.Equal(expected, files.Select(f => f.RelativePath));
    }

    /// <summary>#544 item 5: the same defect, over a hand-off's job rows keyed by a dedupe key containing its id.</summary>
    [Fact]
    public async Task Job_dedupe_key_prefix_matching_for_a_hand_off_is_exact_not_a_sql_wildcard()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.Store.Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind) VALUES " +
            "('refiner.file.remux_pass.v1:deluno:handoff:h_1:part1', 'refiner.file.remux_pass.v1'), " +
            // Under SQL LIKE, "...:handoff:h_1:%" wildcards the "_" and matches this other hand-off's job too.
            "('refiner.file.remux_pass.v1:deluno:handoff:hX1:part2', 'refiner.file.remux_pass.v1')");

        var row = new HandoffLedgerRow(1, "deluno", "h_1", null, "h_1", HandoffLedgerRules.Queued, null, null, null);
        var jobs = await fixture.Db(uow => HandoffLedgerStore.JobsForAsync(uow, row));
        Assert.Equal(["refiner.file.remux_pass.v1:deluno:handoff:h_1:part1"], jobs.Select(j => j.DedupeKey));
    }

    /// <summary>
    /// #544 item 6: the presented secret is matched against every enabled connection of the kind, so a second
    /// connection of the same kind (a 4K Radarr next to a 1080p one) authenticates with its own secret instead
    /// of only the first one (by id) ever being considered.
    /// </summary>
    [Fact]
    public async Task Several_enabled_connections_of_one_kind_each_authenticate_with_their_own_secret()
    {
        using var fixture = new MediaManagerFixture();
        var id1 = await fixture.AddConnectionAsync("radarr", "1080p", "http://10.1.1.5:7878");
        var id2 = await fixture.AddConnectionAsync("radarr", "4K", "http://10.1.1.6:7878");
        var row1 = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id1)))!;
        var row2 = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id2)))!;
        var secret1 = await fixture.Db(uow => fixture.Connections.RotateWebhookSecretAsync(uow, row1));
        var secret2 = await fixture.Db(uow => fixture.Connections.RotateWebhookSecretAsync(uow, row2));
        Assert.NotEqual(secret1, secret2);

        await fixture.Db(async uow => { await fixture.Intake.AuthoriseAsync(uow, "radarr", secret1); return 0; });
        await fixture.Db(async uow => { await fixture.Intake.AuthoriseAsync(uow, "radarr", secret2); return 0; });

        var wrong = await Assert.ThrowsAsync<IntakeRefusedException>(
            () => fixture.Db(async uow => { await fixture.Intake.AuthoriseAsync(uow, "radarr", "neither-connections-secret"); return 0; }));
        Assert.Equal(401, wrong.StatusCode);
    }

    /// <summary>
    /// #544 item 7: Python's <c>secrets.compare_digest</c> raises <c>TypeError</c> for a non-ASCII <c>str</c>; the
    /// .NET port compares UTF-8 bytes (a deliberate difference kept from the original port), so it never crashes.
    /// </summary>
    [Fact]
    public void Non_ascii_secrets_compare_by_bytes_without_crashing()
    {
        Assert.True(MediaManagerConnectionService.CompareDigest("clé-secrète-日本語", "clé-secrète-日本語"));
        Assert.False(MediaManagerConnectionService.CompareDigest("clé-secrète-日本語", "clé-secrète-français"));
        Assert.False(MediaManagerConnectionService.CompareDigest("clé-secrète-日本語", string.Empty));
    }

    [Fact]
    public async Task Connections_validate_names_addresses_and_keep_or_clear_the_key()
    {
        using var fixture = new MediaManagerFixture();
        var id = await fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.142:5099/", "deluno_secret_key");
        var saved = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!;
        Assert.Equal("http://10.1.1.142:5099", saved.BaseUrl);
        Assert.Equal(["missing", "upgrade"], saved.Lanes.Select(l => l.Lane));
        Assert.Equal("deluno_secret_key", fixture.Cipher.Decrypt(saved.ApiKeyCiphertext));

        var duplicate = await Assert.ThrowsAsync<MediaManagerConnectionException>(() => fixture.AddConnectionAsync("radarr", " Deluno "));
        Assert.Equal("A connection named 'Deluno' already exists.", duplicate.Message);
        var badUrl = await Assert.ThrowsAsync<MediaManagerConnectionException>(() => fixture.AddConnectionAsync("radarr", "X", "not-a-url"));
        Assert.Equal("That address will not work: URL must be a valid http(s) URL.", badUrl.Message);
        await Assert.ThrowsAsync<MediaManagerConnectionException>(() => fixture.AddConnectionAsync("radarr", "  "));

        await fixture.Db(async uow => { await fixture.Connections.UpdateAsync(uow, saved, name: "Deluno renamed"); return 0; });
        var renamed = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!;
        Assert.Equal(("Deluno renamed", saved.ApiKeyCiphertext), (renamed.Name, renamed.ApiKeyCiphertext));
        await fixture.Db(async uow => { await fixture.Connections.UpdateAsync(uow, renamed, apiKey: " "); return 0; });
        Assert.Null((await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!.ApiKeyCiphertext);
    }

    [Fact]
    public async Task A_webhook_secret_is_shown_once_stored_encrypted_and_matched()
    {
        using var fixture = new MediaManagerFixture();
        var id = await fixture.AddConnectionAsync("deluno", "Deluno");
        var row = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!;
        Assert.True(fixture.Connections.WebhookSecretMatches(row, null));
        var secret = await fixture.Db(uow => fixture.Connections.RotateWebhookSecretAsync(uow, row));
        Assert.Matches("^[A-Za-z0-9_-]{43}$", secret);
        var stored = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!;
        Assert.DoesNotContain(secret, stored.WebhookSecretCiphertext, StringComparison.Ordinal);
        Assert.True(fixture.Connections.WebhookSecretMatches(stored, $" {secret} "));
        Assert.False(fixture.Connections.WebhookSecretMatches(stored, "wrong"));
    }

    [Fact]
    public async Task The_legacy_arr_settings_row_is_created_once_when_missing()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.Store.Execute("DELETE FROM arr_library_operator_settings");
        await fixture.Db(async uow => { await ArrLibraryOperatorSettingsStore.EnsureRowAsync(uow); return 0; });
        await fixture.Db(async uow => { await ArrLibraryOperatorSettingsStore.EnsureRowAsync(uow); return 0; });
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM arr_library_operator_settings WHERE id = 1 AND radarr_missing_search_max_items_per_run = 50"));
    }

    // --- completion reports --------------------------------------------------------------------

    private const string HandoffPayload =
        """{"relative_media_path":"a/b.mkv","media_scope":"movie","origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"/api/integrations/processors/events"}}""";

    private const string DelunoPayload =
        """{"relative_media_path":"Film/film.mkv","media_scope":"movie","origin":{"source_key":"deluno","handoff_id":"h1","library_id":"lib-movies","callback_path":"/api/integrations/processors/events"}}""";

    private static PyDict Result(string json) => (PyDict)PyJsonParser.Parse(json);

    private static Task<string> Report(MediaManagerFixture fixture, string? payload, string result) =>
        fixture.Db(uow => fixture.Reporter.ReportHandoffCompletionAsync(uow, payload, Result(result)), commit: false);

    [Fact]
    public async Task Reports_are_skipped_when_there_is_nothing_to_report_to()
    {
        using var fixture = new MediaManagerFixture();
        const string ok = """{"ok":true,"outcome":"live_output_written","output_file":"/out/b.mkv"}""";
        Assert.Equal("skipped: not a hand-off", await Report(fixture, """{"relative_media_path":"a.mkv"}""", ok));
        Assert.Equal("skipped: job payload is not readable", await Report(fixture, "{nope", ok));
        Assert.Contains("no enabled deluno connection", await Report(fixture, HandoffPayload, ok), StringComparison.Ordinal);
        await fixture.AddConnectionAsync("deluno", "Deluno", baseUrl: string.Empty);
        Assert.Contains("no address saved", await Report(fixture, HandoffPayload, ok), StringComparison.Ordinal);
        Assert.Empty(fixture.Http.Requests);
    }

    [Fact]
    public async Task The_outcome_is_posted_to_the_configured_manager_and_recorded_in_activity()
    {
        using var fixture = new MediaManagerFixture();
        fixture.Http.Route(HttpMethod.Post, "/api/integrations/processors/events", _ => FakeManagerHttp.Response(HttpStatusCode.OK));
        await fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        var status = await Report(fixture, DelunoPayload, """{"ok":true,"outcome":"live_output_written","output_file":"/out/b.mkv","relative_media_path":"Film/film.mkv"}""");
        Assert.Equal("reported completed to Deluno", status);
        var post = Assert.Single(fixture.Http.RequestsTo(HttpMethod.Post, "/api/integrations/processors/events"));
        Assert.Equal("http://10.1.1.9:5099/api/integrations/processors/events", post.Uri.ToString());
        Assert.Equal("k1", post.Headers["X-Api-Key"]);
        Assert.False(post.FollowRedirects);
        Assert.Equal(
            """{"handoffId":"h1","status":"completed","processorName":"Weir Refiner","libraryId":"lib-movies","outputPath":"/out/b.mkv","message":"Remux finished."}""",
            post.Body);
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE event_type = 'refiner.handoff_reported' AND title = 'Told Deluno that film.mkv is ready to import'"));
    }

    [Fact]
    public async Task An_unreachable_or_refusing_manager_is_reported_not_raised()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099");
        const string ok = """{"ok":true,"outcome":"live_output_written","output_file":"/out/b.mkv"}""";
        Assert.StartsWith("failed: could not reach Deluno", await Report(fixture, HandoffPayload, ok), StringComparison.Ordinal);
        fixture.Http.Json(HttpMethod.Post, "/api/integrations/processors/events", string.Empty, HttpStatusCode.Conflict);
        Assert.Equal("failed: Deluno answered HTTP 409", await Report(fixture, HandoffPayload, ok));
        Assert.Equal(2, await fixture.Store.Scalar("SELECT count(*) FROM activity_events WHERE title = 'Weir could not tell Deluno about a handed-over file'"));
    }

    [Theory]
    [InlineData("retry_scheduled", "will be retried")]
    [InlineData("pass_through_queued", "being handed back")]
    [InlineData("reject_queued", "being rejected")]
    public async Task A_failure_that_is_not_final_is_not_reported(string flag, string expected)
    {
        using var fixture = new MediaManagerFixture();
        await fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        var status = await Report(fixture, DelunoPayload, $$"""{"ok":false,"outcome":"failed_execution","reason":"ffmpeg failed","{{flag}}":true}""");
        Assert.StartsWith("skipped:", status, StringComparison.Ordinal);
        Assert.Contains(expected, status, StringComparison.Ordinal);
        Assert.Empty(fixture.Http.Requests);
    }

    [Fact]
    public async Task A_final_failure_is_reported_as_held_and_the_ledger_follows()
    {
        using var fixture = new MediaManagerFixture();
        fixture.Http.Json(HttpMethod.Post, "/api/integrations/processors/events", "{}", HttpStatusCode.Accepted);
        await fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        await fixture.Db(async uow => { await fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h1", null, "Film/film.mkv"); return 0; });
        var status = await Report(fixture, DelunoPayload, """{"ok":false,"outcome":"failed_execution","reason":"ffmpeg failed","retry_scheduled":false,"pass_through_queued":false,"failure_class":"execution"}""");
        Assert.Equal("reported failed to Deluno", status);
        var body = (PyDict)fixture.Http.Requests[0].Json!;
        Assert.Equal(("lib-movies", "held"), (((PyStr)body["libraryId"]).Value, ((PyStr)body["disposition"]).Value));
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM media_manager_handoffs WHERE state = 'failed' AND message = 'ffmpeg failed'"));
    }

    [Fact]
    public async Task A_completion_is_reported_in_the_managers_own_path_when_its_library_refines_before_import()
    {
        using var fixture = new MediaManagerFixture();
        var local = fixture.Store.Home.Join("Refined");
        fixture.Http
            .Json(HttpMethod.Post, "/api/integrations/processors/events", "{}", HttpStatusCode.Accepted)
            .Json(HttpMethod.Get, "/api/integrations/external/manifest", """{"libraries":[{"id":"lib-tv","mediaType":"tv","importWorkflow":"refine-before-import","processorOutputPath":"/data/tv-refined"},{"id":"lib-movies","mediaType":"movie","importWorkflow":"refine-before-import","processorOutputPath":"/data/refined"}]}""");
        await fixture.AddConnectionAsync("deluno", "Deluno", "http://10.1.1.9:5099", "k1");
        var result = new PyDict().Set("ok", true).Set("outcome", "live_output_written")
            .Set("output_file", Path.Join(local, "Film", "film.mkv")).Set("refiner_output_folder_resolved", local);
        var status = await fixture.Db(uow => fixture.Reporter.ReportHandoffCompletionAsync(uow, DelunoPayload, result), commit: false);
        Assert.Equal("reported completed to Deluno", status);
        Assert.Equal("/data/refined/Film/film.mkv", ((PyStr)((PyDict)fixture.Http.RequestsTo(HttpMethod.Post, "/api")[0].Json!)["outputPath"]).Value);
        Assert.Equal("k1", fixture.Http.RequestsTo(HttpMethod.Get, "/api/integrations/external/manifest")[0].Headers["X-Api-Key"]);

        // No matching library that refines before import, or a manifest that cannot be read: the local path is reported.
        fixture.Http.Json(HttpMethod.Get, "/api/integrations/external/manifest", """{"libraries":[{"id":"lib-movies","importWorkflow":"standard","processorOutputPath":"/data/refined"}]}""");
        await fixture.Db(uow => fixture.Reporter.ReportHandoffCompletionAsync(uow, DelunoPayload, result), commit: false);
        fixture.Http.Json(HttpMethod.Get, "/api/integrations/external/manifest", "not json");
        Assert.Equal("reported completed to Deluno", await fixture.Db(uow => fixture.Reporter.ReportHandoffCompletionAsync(uow, DelunoPayload, result), commit: false));
        var posts = fixture.Http.RequestsTo(HttpMethod.Post, "/api");
        Assert.Equal([Path.Join(local, "Film", "film.mkv"), Path.Join(local, "Film", "film.mkv")], posts.Skip(1).Select(p => ((PyStr)((PyDict)p.Json!)["outputPath"]).Value));
    }

    [Fact]
    public void Output_outside_the_local_folder_is_not_translated()
    {
        using var home = new TempDirectory();
        Assert.Null(HandoffCompletionReporter.TranslateOutputPath(home.Join("elsewhere", "film.mkv"), home.Join("Refined"), "/data/refined"));
        Assert.Equal(@"E:\Deluno\Refined\Show\S01E01.mkv", HandoffCompletionReporter.TranslateOutputPath(home.Join("Refined", "Show", "S01E01.mkv"), home.Join("Refined"), @"E:\Deluno\Refined"));
    }

    // --- metadata provider ---------------------------------------------------------------------

    private const string SearchPayload = """{"results":[{"id":42,"title":"Film","original_language":"fr","release_date":"2001-05-01"}]}""";

    [Fact]
    public async Task A_lookup_returns_the_original_language_and_repeats_come_from_the_cache()
    {
        var http = new FakeManagerHttp().Json(HttpMethod.Get, "/3/search/movie", SearchPayload);
        var provider = new TmdbMetadataProvider("k", http, cache: new MetadataLookupCache());
        var result = await provider.LookupMovieAsync("Film", 2001);
        Assert.True(result.Matched);
        Assert.Equal(("fr", 2001), (result.Metadata!.OriginalLanguage, result.Metadata.Year!.Value));
        await provider.LookupMovieAsync("film ", 2001);
        Assert.Equal("https://api.themoviedb.org/3/search/movie?api_key=k&query=Film&year=2001", Assert.Single(http.Requests).Uri.ToString());
    }

    [Fact]
    public async Task Provider_failures_are_statuses_never_exceptions()
    {
        var empty = new FakeManagerHttp().Json(HttpMethod.Get, "/3/search/movie", """{"results":[]}""");
        var cached = new TmdbMetadataProvider("k", empty, cache: new MetadataLookupCache());
        Assert.Equal(LookupResult.StatusNoMatch, (await cached.LookupMovieAsync("Unknown", 1999)).Status);
        await cached.LookupMovieAsync("Unknown", 1999);
        Assert.Single(empty.Requests);

        var none = new FakeManagerHttp();
        Assert.Equal(LookupResult.StatusNotConfigured, (await new TmdbMetadataProvider(string.Empty, none, cache: new MetadataLookupCache()).LookupMovieAsync("Film", 2001)).Status);
        var down = await new TmdbMetadataProvider("k", none, cache: new MetadataLookupCache()).LookupMovieAsync("Film", 2001);
        Assert.Equal(LookupResult.StatusUnreachable, down.Status);
        Assert.Contains("could not reach", down.Detail, StringComparison.Ordinal);

        var rejected = new FakeManagerHttp().Json(HttpMethod.Get, "/3/search/movie", string.Empty, HttpStatusCode.Unauthorized);
        var refusal = await new TmdbMetadataProvider("wrong", rejected, cache: new MetadataLookupCache()).LookupMovieAsync("Film", 2001);
        Assert.Equal(LookupResult.StatusNotConfigured, refusal.Status);
        Assert.Contains("rejected the configured key", refusal.Detail, StringComparison.Ordinal);

        var gateway = new FakeManagerHttp().Json(HttpMethod.Get, "/search/movie", SearchPayload);
        Assert.True((await new TmdbMetadataProvider("k", gateway, "https://metadata.example.workers.dev", new MetadataLookupCache()).LookupMovieAsync("Film", 2001)).Matched);
        var internalAddress = await new TmdbMetadataProvider("k", gateway, "http://169.254.169.254/latest", new MetadataLookupCache()).LookupMovieAsync("Film", 2001);
        Assert.Equal(LookupResult.StatusNotConfigured, internalAddress.Status);
        Assert.Contains("not usable", internalAddress.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public async Task The_saved_provider_is_built_from_suite_settings()
    {
        using var fixture = new MediaManagerFixture();
        var service = new MetadataProviderService(fixture.Cipher, fixture.Http);
        Assert.Equal(LookupResult.StatusNotConfigured, (await fixture.Db(uow => service.TestProviderAsync(uow))).Status);
        var ciphertext = service.StoreProviderKey("tmdb-key");
        await fixture.Db(uow => uow.ExecuteAsync("UPDATE suite_settings SET metadata_provider = 'TMDB', metadata_provider_key_ciphertext = $c WHERE id = 1", ("$c", ciphertext)));
        fixture.Http.Json(HttpMethod.Get, "/3/search/movie", SearchPayload);
        var tested = await fixture.Db(uow => service.TestProviderAsync(uow));
        Assert.Equal((LookupResult.StatusMatched, "The metadata provider answered."), (tested.Status, tested.Detail));
        Assert.Contains("query=Blade+Runner&year=1982", fixture.Http.Requests[0].Uri.Query, StringComparison.Ordinal);
    }

    // --- intake and the ledger -----------------------------------------------------------------

    private static MediaManagerImportEvent Handoff(string handoffId, string path, string scope = "movie") => new()
    {
        SourceKey = "deluno",
        EventKind = "handoff",
        MediaScope = scope,
        FilePath = path,
        HandoffId = handoffId,
        CallbackPath = "/api/integrations/processors/events",
        LibraryId = "lib-1",
    };

    private static async Task<List<(string Key, string Payload)>> Jobs(MediaManagerFixture fixture) =>
        (await fixture.Jobs.ListAsync()).Select(job => (job.DedupeKey, job.PayloadJson ?? string.Empty)).ToList();

    [Fact]
    public async Task A_hand_off_enqueues_one_remux_pass_per_file_and_records_the_ledger()
    {
        using var fixture = new MediaManagerFixture();
        var watched = fixture.Store.Home.Join("movies");
        Directory.CreateDirectory(Path.Join(watched, "Blade.Runner.2049", "Sample"));
        await File.WriteAllTextAsync(Path.Join(watched, "Blade.Runner.2049", "Blade.Runner.2049.mkv"), "12345");
        await File.WriteAllTextAsync(Path.Join(watched, "Blade.Runner.2049", "Sample", "sample.mkv"), "x");
        await File.WriteAllTextAsync(Path.Join(watched, "Blade.Runner.2049", "movie.nfo"), "x");
        var libraryId = await fixture.LibraryAsync("movie", watched);

        foreach (var _ in new[] { 1, 2 })
        {
            await fixture.Db(uow => fixture.Intake.EnqueueRefineAsync(uow, Handoff("h1", Path.Join(watched, "Blade.Runner.2049"))));
        }

        var job = Assert.Single(await Jobs(fixture));
        Assert.Equal("refiner.file.remux_pass.v1:deluno:handoff:h1:Blade.Runner.2049/Blade.Runner.2049.mkv", job.Key);
        Assert.Equal(
            $$$"""{"relative_media_path":"Blade.Runner.2049/Blade.Runner.2049.mkv","media_scope":"movie","trigger":"webhook","library_id":{{{libraryId}}},"origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"/api/integrations/processors/events","release_name":null,"library_id":"lib-1"}}""",
            job.Payload);
        Assert.Equal(1, await fixture.Store.Scalar("SELECT count(*) FROM media_manager_handoffs WHERE handoff_id = 'h1' AND state = 'queued' AND relative_path = 'Blade.Runner.2049'"));
        // #531: the handed-over file's size is known from the moment it arrives.
        Assert.Equal(5, await fixture.Store.Scalar("SELECT size_bytes FROM refiner_files WHERE relative_path = 'Blade.Runner.2049/Blade.Runner.2049.mkv'"));
    }

    [Fact]
    public async Task Hand_offs_that_cannot_be_placed_are_refused_with_the_reason()
    {
        using var fixture = new MediaManagerFixture();
        await fixture.Db(uow => uow.ExecuteAsync("UPDATE refiner_libraries SET watched_folder = ''"));
        var unset = await Assert.ThrowsAsync<IntakeRefusedException>(() => fixture.Db(uow => fixture.Intake.EnqueueRefineAsync(uow, Handoff("h", "/x/ep.mkv", "tv"))));
        Assert.Contains("watched folder is not set", unset.Message, StringComparison.Ordinal);

        var watched = fixture.Store.Home.Join("movies");
        Directory.CreateDirectory(Path.Join(watched, "Empty.Release"));
        await File.WriteAllTextAsync(Path.Join(watched, "Empty.Release", "readme.txt"), "x");
        await fixture.LibraryAsync("movie", watched);
        var empty = await Assert.ThrowsAsync<IntakeRefusedException>(() => fixture.Db(uow => fixture.Intake.EnqueueRefineAsync(uow, Handoff("h2", Path.Join(watched, "Empty.Release")))));
        Assert.Equal((400, "The hand-off names the folder 'Empty.Release', but it holds no video file Weir processes. Nothing was queued."), (empty.StatusCode, empty.Message));
        Assert.Empty(await Jobs(fixture));
    }

    [Fact]
    public async Task The_ledger_answers_queued_scheduled_and_cancelled_and_keeps_last_changed_still()
    {
        using var fixture = new MediaManagerFixture();
        fixture.Store.Clock.Set(DateTimeOffset.UtcNow);
        var watched = fixture.Store.Home.Join("movies");
        var libraryId = await fixture.LibraryAsync("movie", watched);
        await fixture.Db(uow => fixture.Intake.EnqueueRefineAsync(uow, Handoff("h1", Path.Join(watched, "Film", "film.mkv"))));
        var row = (await fixture.Db(uow => HandoffLedgerStore.FindAsync(uow, "deluno", "h1")))!;
        var first = await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row));
        Assert.Equal(("queued", (long?)1), (first.State, first.QueuePosition));
        var again = await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row));
        Assert.Equal(first.AsJson()["lastChangedUtc"].ToString(), again.AsJson()["lastChangedUtc"].ToString());

        // #531: a failure with a retry still owed stays scheduled after its backoff has ended.
        var retryAt = fixture.Store.Clock.GetUtcNow().AddMinutes(-5).ToString("yyyy-MM-dd HH:mm:ss.ffffff", CultureInfo.InvariantCulture);
        await fixture.Store.Execute("UPDATE refiner_jobs SET status = 'completed'");
        await fixture.Store.Execute($"INSERT INTO refiner_files (library_id, relative_path, status, next_retry_at, failure_attempts, status_reason) VALUES ({libraryId}, 'Film/film.mkv', 'processing_failed', '{retryAt}', 1, 'ffmpeg died.')");
        var scheduled = await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row));
        Assert.Equal(("scheduled", "ffmpeg died."), (scheduled.State, scheduled.Message));
        Assert.NotNull(scheduled.ScheduledFor);

        await fixture.Store.Execute("UPDATE refiner_files SET status = 'processed', next_retry_at = NULL");
        Assert.Equal("completed", (await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row))).State);
        await fixture.Store.Execute("DELETE FROM refiner_jobs; DELETE FROM refiner_files;");
        var pruned = (await fixture.Db(uow => HandoffLedgerStore.FindAsync(uow, "deluno", "h1")))!;
        Assert.Equal("completed", (await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, pruned))).State);
    }

    [Fact]
    public async Task Issue_545_item_3_the_ledger_reports_a_pass_through_jobs_own_state_and_its_final_failure()
    {
        // #545 item 3: a pass-through or reject job that is queued (but not yet delivered) must still be visible to
        // the manager polling the status API — as scheduled or working, never silently dropped — and one that
        // exhausted its own retries must be reported failed, with the reason, rather than vanish once it is no
        // longer pending or leased.
        using var fixture = new MediaManagerFixture();
        var watched = fixture.Store.Home.Join("movies");
        var libraryId = await fixture.LibraryAsync("movie", watched);
        await fixture.Store.Execute($"INSERT INTO refiner_files (library_id, relative_path, status) VALUES ({libraryId}, 'Film/film.mkv', 'processing_failed')");
        await fixture.Db(async uow => { await fixture.Ledger.RecordReceivedAsync(uow, "deluno", "h1", libraryId, "Film/film.mkv"); return 0; });
        var row = (await fixture.Db(uow => HandoffLedgerStore.FindAsync(uow, "deluno", "h1")))!;

        var dedupe = $"refiner.file.pass_through.v1:{libraryId}:Film/film.mkv:10-123";
        await fixture.Store.Execute(
            $"INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES " +
            $"('{dedupe}', 'refiner.file.pass_through.v1', '{{\"relative_media_path\":\"Film/film.mkv\",\"library_id\":{libraryId}}}', 'pending')");

        var pending = await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row));
        Assert.Equal("scheduled", pending.State);
        Assert.Null(pending.QueuePosition);

        await fixture.Store.Execute($"UPDATE refiner_jobs SET status = 'leased' WHERE dedupe_key = '{dedupe}'");
        var working = await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row));
        Assert.Equal("working", working.State);

        await fixture.Store.Execute($"UPDATE refiner_jobs SET status = 'failed', last_error = 'Weir could not deliver the file: disk full.' WHERE dedupe_key = '{dedupe}'");
        var failed = await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, row));
        Assert.Equal("failed", failed.State);
        Assert.Equal("Weir could not deliver the file: disk full.", failed.Message);
    }

    [Fact]
    public async Task Only_a_hand_off_that_has_not_started_can_be_cancelled_and_resending_starts_it_again()
    {
        using var fixture = new MediaManagerFixture();
        var watched = fixture.Store.Home.Join("movies");
        await fixture.LibraryAsync("movie", watched);
        var handoff = Handoff("h1", Path.Join(watched, "Film", "film.mkv"));
        await fixture.Db(uow => fixture.Intake.EnqueueRefineAsync(uow, handoff));
        var row = (await fixture.Db(uow => HandoffLedgerStore.FindAsync(uow, "deluno", "h1")))!;
        var (cancelled, sentence) = await fixture.Db(uow => fixture.Ledger.CancelAsync(uow, fixture.Jobs, row));
        Assert.True(cancelled);
        Assert.Equal(HandoffLedgerRules.CancelledMessage, sentence);
        var job = Assert.Single(await fixture.Jobs.ListAsync());
        Assert.Equal(("cancelled", "refiner.file.remux_pass.v1:deluno:handoff:h1:cancelled:" + job.Id), (job.Status, job.DedupeKey));

        var cancelledRow = (await fixture.Db(uow => HandoffLedgerStore.FindAsync(uow, "deluno", "h1")))!;
        var refused = await fixture.Db(uow => fixture.Ledger.CancelAsync(uow, fixture.Jobs, cancelledRow), commit: false);
        Assert.Equal((false, "This hand-off is cancelled, so Weir did not cancel it."), refused);

        await fixture.Db(uow => fixture.Intake.EnqueueRefineAsync(uow, handoff));
        var restarted = (await fixture.Db(uow => HandoffLedgerStore.FindAsync(uow, "deluno", "h1")))!;
        Assert.Equal("queued", (await fixture.Db(uow => fixture.Ledger.CurrentStatusAsync(uow, restarted))).State);

        await fixture.Store.Execute("UPDATE refiner_jobs SET status = 'leased' WHERE status = 'pending'");
        var working = await fixture.Db(uow => fixture.Ledger.CancelAsync(uow, fixture.Jobs, restarted), commit: false);
        Assert.Equal((false, "This hand-off is working, so Weir did not cancel it."), working);
    }

    [Fact]
    public async Task Webhook_secrets_prefer_the_connections_own_then_the_instance_secret()
    {
        using var open = new MediaManagerFixture();
        await open.Db(async uow => { await open.Intake.AuthoriseAsync(uow, "radarr", null); return 0; });
        var needs = await Assert.ThrowsAsync<IntakeRefusedException>(() => open.Db(async uow => { await open.Intake.RequireSecretAsync(uow, "x", null); return 0; }));
        Assert.Equal((403, IntakeRules.NeedsSecretDetail), (needs.StatusCode, needs.Message));

        using var instance = new MediaManagerFixture(("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", "s3cret"));
        await Assert.ThrowsAsync<IntakeRefusedException>(() => instance.Db(async uow => { await instance.Intake.AuthoriseAsync(uow, "radarr", "wrong"); return 0; }));
        await instance.Db(async uow => { await instance.Intake.AuthoriseAsync(uow, "radarr", " s3cret "); return 0; });
        var id = await instance.AddConnectionAsync("deluno", "Deluno");
        var row = (await instance.Db(uow => MediaManagerConnectionStore.GetAsync(uow, id)))!;
        var secret = await instance.Db(uow => instance.Connections.RotateWebhookSecretAsync(uow, row));
        await Assert.ThrowsAsync<IntakeRefusedException>(() => instance.Db(async uow => { await instance.Intake.AuthoriseAsync(uow, "deluno", "s3cret"); return 0; }));
        await instance.Db(async uow => { await instance.Intake.AuthoriseAsync(uow, "deluno", secret); return 0; });
        await instance.Db(async uow => { await instance.Intake.RequireSecretAsync(uow, "s3cret", "deluno"); return 0; });
        await instance.Db(async uow => { await instance.Intake.RequireSecretAsync(uow, secret, "deluno"); return 0; });
        var wrong = await Assert.ThrowsAsync<IntakeRefusedException>(() => instance.Db(async uow => { await instance.Intake.RequireSecretAsync(uow, secret, "radarr"); return 0; }));
        Assert.Equal(401, wrong.StatusCode);
    }

    // --- reconciliation ------------------------------------------------------------------------

    [Fact]
    public async Task Reconciliation_reports_missing_folders_and_removes_temp_artifacts_only_with_confirmation()
    {
        using var fixture = new MediaManagerFixture();
        var work = fixture.Store.Home.Join("work");
        Directory.CreateDirectory(work);
        var artifact = Path.Join(work, ".movie.mkv.partial");
        await File.WriteAllTextAsync(artifact, "partial");
        await fixture.Db(uow => uow.ExecuteAsync("UPDATE refiner_libraries SET work_folder = $w, watched_folder = $missing WHERE media_type = 'movie'", ("$w", work), ("$missing", fixture.Store.Home.Join("gone"))));

        var report = await fixture.Db(ReconciliationService.BuildReportAsync);
        var issues = ((PyList)report["issues"]).Items.Cast<PyDict>().ToList();
        Assert.Contains(issues, issue => ((PyStr)issue["kind"]).Value == "configured_folder_missing" && ((PyStr)issue["message"]).Value.EndsWith("watched folder is configured but is not currently reachable on disk.", StringComparison.Ordinal));
        Assert.Equal(["remove_refiner_temp_artifact"], ((PyList)report["repair_actions"]).Items.Select(item => ((PyStr)item).Value));

        var refused = await Assert.ThrowsAsync<PyValueErrorException>(() => fixture.Db(uow => ReconciliationService.RepairAsync(uow, "remove_refiner_temp_artifact", null, artifact, confirm: false)));
        Assert.Contains("confirm=true", refused.Message, StringComparison.Ordinal);
        Assert.True(File.Exists(artifact));
        await Assert.ThrowsAsync<PyValueErrorException>(() => fixture.Db(uow => ReconciliationService.RepairAsync(uow, "remove_refiner_temp_artifact", null, Path.Join(work, "film.mkv"), confirm: true)));
        Assert.True(((PyBool)(await fixture.Db(uow => ReconciliationService.RepairAsync(uow, "remove_refiner_temp_artifact", null, artifact, confirm: true)))["applied"]).Value);
        Assert.False(File.Exists(artifact));
        Assert.False(((PyBool)(await fixture.Db(uow => ReconciliationService.RepairAsync(uow, "remove_refiner_temp_artifact", null, artifact, confirm: true)))["applied"]).Value);
        await Assert.ThrowsAsync<FileLifecycleException>(() => fixture.Db(uow => ReconciliationService.RepairAsync(uow, "remove_refiner_temp_artifact", null, fixture.Store.Home.Join("elsewhere.tmp"), confirm: true)));
    }
}
