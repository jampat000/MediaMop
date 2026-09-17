using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Tests.MediaManagers;

/// <summary>
/// The media manager area checked against the Python backend itself: connections and credentials saved by either
/// server work on the other, and the same webhook bodies leave byte-identical job rows and the same hand-off answers.
/// </summary>
public sealed class MediaManagerCrossBackendTests
{
    private const string Secret = "cross-check-session-secret-0123456789";
    private const string CredentialsSecret = "cross-check-credentials-secret";

    private static Dictionary<string, string> PythonEnvironment(MediaManagerFixture fixture, params (string Name, string Value)[] extra)
    {
        var environment = new Dictionary<string, string>
        {
            ["WEIR_HOME"] = fixture.Store.Home.Path,
            ["WEIR_SESSION_SECRET"] = Secret,
            ["WEIR_CREDENTIALS_SECRET"] = CredentialsSecret,
        };
        foreach (var (name, value) in extra)
        {
            environment[name] = value;
        }

        return environment;
    }

    private const string PythonPrelude =
        "import json, os\n" +
        "import weir.api.factory  # registers every ORM model\n" +
        "from weir.core.config import WeirSettings\n" +
        "from weir.core.db import create_db_engine, create_session_factory\n" +
        "s = WeirSettings.load()\n" +
        "fac = create_session_factory(create_db_engine(s))\n";

    [PythonFact]
    public async Task Connections_and_credentials_saved_by_either_server_work_on_the_other()
    {
        using var fixture = new MediaManagerFixture(("WEIR_SESSION_SECRET", Secret), ("WEIR_CREDENTIALS_SECRET", CredentialsSecret));
        fixture.Store.Database.ClearPool();
        var output = PythonBackend.Run(
            PythonPrelude +
            "from weir.platform.media_managers.connection_service import create_connection, rotate_webhook_secret\n" +
            "with fac() as db:\n" +
            "    row = create_connection(db, s, kind='deluno', name='From Python', base_url='http://10.1.1.9:5099/', api_key='python-key')\n" +
            "    secret = rotate_webhook_secret(db, s, row)\n" +
            "    db.commit()\n" +
            "    print(json.dumps({'id': row.id, 'secret': secret}))\n",
            PythonEnvironment(fixture));
        var created = (PyDict)PyJsonParser.Parse(output.Split('\n')[^1]);
        var pythonId = (long)((PyInt)created["id"]).Value;
        var pythonSecret = ((PyStr)created["secret"]).Value;

        var fromPython = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, pythonId)))!;
        Assert.Equal(["missing", "upgrade"], fromPython.Lanes.Select(lane => lane.Lane));
        Assert.Equal(new ResolvedCallbackTargetView("http://10.1.1.9:5099", "python-key"), ResolvedCallbackTargetView.From(fixture.Connections.ResolveCallbackTarget(fromPython)!));
        Assert.True(fixture.Connections.WebhookSecretMatches(fromPython, pythonSecret));
        Assert.Equal(["Deluno (From Python)"], (await fixture.Db(uow => fixture.Connections.ConnectionsForScopeAsync(uow, "tv"))).Select(c => c.Label));

        var dotnetId = await fixture.AddConnectionAsync("radarr", "From Dotnet", "http://10.1.1.5:7878", "dotnet-key");
        var dotnetRow = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, dotnetId)))!;
        var dotnetSecret = await fixture.Db(uow => fixture.Connections.RotateWebhookSecretAsync(uow, dotnetRow));
        fixture.Store.Database.ClearPool();
        var check = PythonBackend.Run(
            PythonPrelude +
            "from weir.platform.media_managers.connection_service import get_connection, webhook_secret_matches, resolve_callback_target\n" +
            "from weir.platform.media_managers.manager_binding import connections_for_scope\n" +
            "from weir.platform.media_managers.connections_api import _to_out\n" +
            "with fac() as db:\n" +
            "    row = get_connection(db, int(os.environ['ID']))\n" +
            "    print(webhook_secret_matches(s, row, os.environ['SECRET']), resolve_callback_target(s, row).api_key)\n" +
            "    print([c.label for c in connections_for_scope(db, s, media_scope='movie')])\n" +
            "    print(_to_out(row).model_dump_json())\n",
            PythonEnvironment(fixture, ("ID", dotnetId.ToString(System.Globalization.CultureInfo.InvariantCulture)), ("SECRET", dotnetSecret)));
        var lines = check.Split('\n').Select(line => line.Trim()).ToArray();
        Assert.Equal("True dotnet-key", lines[0]);
        Assert.Equal("['Deluno (From Python)', 'Radarr (From Dotnet)']", lines[1]);
        var dotnetOut = (await fixture.Db(uow => MediaManagerConnectionStore.GetAsync(uow, dotnetId)))!.ToOut();
        Assert.Equal(lines[2], PyJsonWriter.Dumps(dotnetOut, PyJsonFormat.Response));
    }

    private sealed record ResolvedCallbackTargetView(string BaseUrl, string? ApiKey)
    {
        public static ResolvedCallbackTargetView From(ResolvedCallbackTarget target) => new(target.BaseUrl, target.ApiKey);
    }

    /// <summary>Webhook bodies whose intake is compared (the no-hand-off-id case uses a random key and is compared by shape).</summary>
    private static string[] WebhookBodies(string movies, string tv) =>
    [
        Json(new PyDict().Set("eventType", "deluno.processor-handoff").Set("handoffId", "h-file").Set("libraryId", "lib-1").Set("mediaType", "movies")
            .Set("sourcePath", Path.Join(movies, "Blade.Runner.2049", "film é.mkv")).Set("releaseName", "Blade.Runner.2049").Set("callbackPath", "/api/integrations/processors/events")),
        Json(new PyDict().Set("eventType", "deluno.processor-handoff").Set("handoffId", "h-folder").Set("mediaType", "movie")
            .Set("sourcePath", Path.Join(movies, "Folder.Release"))),
        Json(new PyDict().Set("eventType", "deluno.processor-handoff").Set("handoffId", "h-tv").Set("mediaType", "series")
            .Set("sourcePath", Path.Join(tv, "Show", "S01E01.mkv")).Set("callbackPath", "cb")),
        Json(new PyDict().Set("event", "handoff").Set("mediaScope", "movie").Set("filePath", Path.Join(movies, "4k", "Nested", "n.mkv")).Set("handoffId", "n-1").Set("library_id", "x")),
        Json(new PyDict().Set("event", "handoff").Set("mediaScope", "tv").Set("filePath", Path.Join(tv, "Show", "S01E02.mkv"))),
    ];

    private static string Json(PyDict body) => PyJsonWriter.Dumps(body, PyJsonFormat.Default);

    [PythonFact]
    public async Task The_same_webhook_bodies_leave_byte_identical_jobs_and_the_same_hand_off_answers()
    {
        using var media = new TempDirectory();
        var movies = media.Join("movies");
        var tv = media.Join("tv");
        Directory.CreateDirectory(Path.Join(movies, "Folder.Release", "Sample"));
        Directory.CreateDirectory(Path.Join(movies, "4k", "Nested"));
        Directory.CreateDirectory(Path.Join(tv, "Show"));
        await File.WriteAllTextAsync(Path.Join(movies, "Folder.Release", "b.mkv"), "b");
        await File.WriteAllTextAsync(Path.Join(movies, "Folder.Release", "A.mp4"), "a");
        await File.WriteAllTextAsync(Path.Join(movies, "Folder.Release", "Sample", "sample.mkv"), "s");
        await File.WriteAllTextAsync(Path.Join(movies, "Folder.Release", "info.nfo"), "n");
        var bodies = WebhookBodies(movies, tv);

        async Task<MediaManagerFixture> PrepareAsync()
        {
            var fixture = new MediaManagerFixture(("WEIR_SESSION_SECRET", Secret), ("WEIR_CREDENTIALS_SECRET", CredentialsSecret));
            await fixture.LibraryAsync("movie", movies);
            await fixture.LibraryAsync("tv", tv);
            await fixture.LibraryAsync("movie", Path.Join(movies, "4k"), "Movies 4K");
            return fixture;
        }

        using var python = await PrepareAsync();
        using var dotnet = await PrepareAsync();
        var bodiesPath = python.Store.Home.Join("bodies.json");
        await File.WriteAllTextAsync(bodiesPath, PyJsonWriter.Dumps(new PyList(bodies.Select(body => (PyJson)new PyStr(body))), PyJsonFormat.Default));
        python.Store.Database.ClearPool();
        var pythonOutput = PythonBackend.Run(
            PythonPrelude +
            "from weir.platform.media_managers.import_events import dialect_for_source\n" +
            "from weir.platform.media_managers.intake_api import _enqueue_refine\n" +
            "for raw in json.load(open(os.environ['BODIES'], encoding='utf-8')):\n" +
            "    body = json.loads(raw)\n" +
            "    source = 'deluno' if 'eventType' in body else 'native'\n" +
            "    with fac() as db:\n" +
            "        _enqueue_refine(db, dialect_for_source(source).normalize(body))\n" +
            "        db.commit()\n",
            PythonEnvironment(python, ("BODIES", bodiesPath)));
        Assert.Equal(string.Empty, pythonOutput);

        foreach (var raw in bodies)
        {
            var body = (PyDict)PyJsonParser.Parse(raw);
            var dialect = ImportEvents.DialectForSource(body.ContainsKey("eventType") ? "deluno" : "native")!;
            await dotnet.Db(uow => dotnet.Intake.EnqueueRefineAsync(uow, dialect.Normalize(body)!));
        }

        static async Task<List<string>> JobRows(MediaManagerFixture fixture) =>
            [.. (await fixture.Jobs.ListAsync()).Select(job =>
                $"{(job.DedupeKey.Contains(":handoff:", StringComparison.Ordinal) ? job.DedupeKey : "<fresh key>")}|{job.JobKind}|{job.Status}|{job.MaxAttempts}|{job.RunnerCost}|{job.Priority}|{job.PayloadJson}")];

        var pythonJobs = await JobRows(python);
        Assert.Equal(6, pythonJobs.Count);
        Assert.Equal(pythonJobs, await JobRows(dotnet));
        Assert.Matches("^refiner\\.file\\.remux_pass\\.v1:[0-9a-f]{32}$", (await dotnet.Jobs.ListAsync()).Single(job => !job.DedupeKey.Contains(":handoff:", StringComparison.Ordinal)).DedupeKey);

        const string LedgerSql = "SELECT group_concat(source_key || '|' || handoff_id || '|' || coalesce(library_id, '') || '|' || relative_path || '|' || state, ';') FROM (SELECT * FROM media_manager_handoffs ORDER BY id)";
        Assert.Equal(await ScalarText(python, LedgerSql), await ScalarText(dotnet, LedgerSql));

        // The same Files rows and job states on both sides give the same answers to a manager asking.
        const string Seed =
            "UPDATE refiner_jobs SET status = 'completed' WHERE dedupe_key LIKE '%h-file%';" +
            "INSERT INTO refiner_files (library_id, relative_path, status, status_reason, failure_attempts, next_retry_at) " +
            "VALUES (1, 'Blade.Runner.2049/film é.mkv', 'processing_failed', 'ffmpeg died.', 1, '2099-01-01 00:00:00.000000') " +
            "ON CONFLICT (library_id, relative_path) DO UPDATE SET status = excluded.status, status_reason = excluded.status_reason, " +
            "failure_attempts = excluded.failure_attempts, next_retry_at = excluded.next_retry_at;" +
            "UPDATE refiner_jobs SET status = 'completed' WHERE dedupe_key LIKE '%h-tv%';" +
            "INSERT INTO refiner_files (library_id, relative_path, status, status_reason) VALUES (2, 'Show/S01E01.mkv', 'processed', 'Done.') " +
            "ON CONFLICT (library_id, relative_path) DO UPDATE SET status = excluded.status, status_reason = excluded.status_reason;";
        await python.Store.Execute(Seed);
        await dotnet.Store.Execute(Seed);
        python.Store.Database.ClearPool();
        var answers = PythonBackend.Run(
            PythonPrelude +
            "from weir.platform.media_managers.handoff_ledger import current_status, find_handoff\n" +
            "for source, hid in [('deluno','h-file'),('deluno','h-folder'),('deluno','h-tv'),('native','n-1')]:\n" +
            "    with fac() as db:\n" +
            "        a = current_status(db, find_handoff(db, source_key=source, handoff_id=hid)).as_json()\n" +
            "        a.pop('lastChangedUtc')\n" +
            "        print(json.dumps(a, separators=(',', ':'), ensure_ascii=False))\n",
            PythonEnvironment(python));
        var dotnetAnswers = new List<string>();
        foreach (var (source, handoffId) in new[] { ("deluno", "h-file"), ("deluno", "h-folder"), ("deluno", "h-tv"), ("native", "n-1") })
        {
            var row = (await dotnet.Db(uow => HandoffLedgerStore.FindAsync(uow, source, handoffId)))!;
            var json = (await dotnet.Db(uow => dotnet.Ledger.CurrentStatusAsync(uow, row))).AsJson();
            var trimmed = new PyDict();
            foreach (var (key, value) in json.Items.Where(pair => pair.Key != "lastChangedUtc"))
            {
                trimmed.Set(key, value);
            }

            dotnetAnswers.Add(PyJsonWriter.Dumps(trimmed, PyJsonFormat.Response));
        }

        Assert.Equal(string.Join('\n', answers.Split('\n').Select(line => line.Trim())), string.Join('\n', dotnetAnswers));
    }

    private static async Task<string> ScalarText(MediaManagerFixture fixture, string sql)
    {
        using var connection = fixture.Store.Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(await command.ExecuteScalarAsync(), System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty;
    }
}
