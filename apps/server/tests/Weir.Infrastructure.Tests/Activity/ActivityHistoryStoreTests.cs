using System.Text;
using System.Text.Json;
using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Settings;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Jobs;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Activity;

/// <summary>
/// Activity history reads, commit-time notification and processing-record retention (ports of
/// <c>test_activity_stream.py</c> and <c>test_refiner_file_log.py</c>'s pruning), plus byte-for-byte
/// comparisons with the Python router on the same database.
/// </summary>
public sealed class ActivityHistoryStoreTests
{
    [Fact]
    public async Task Record_activity_event_notifies_only_after_commit()
    {
        using var fixture = new StoreFixture();
        var notifier = ActivityNotifications.For(fixture.Database);
        var uow = await UnitOfWork.OpenAsync(fixture.Database);
        await using (uow)
        {
            var id = await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(ActivityEventTypes.AuthLoginSucceeded, "auth", "Commit-time notify test", "alice"));
            await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(ActivityEventTypes.AuthLogout, "auth", "Second", "alice"));
            Assert.Equal(new ActivityLatest(null, 0), notifier.Snapshot());
            await uow.CommitAsync();
            Assert.Equal(new ActivityLatest(id + 1, 1), notifier.Snapshot());

            await uow.CommitAsync();
            Assert.Equal(1, notifier.Snapshot().Version);
        }
    }

    [Fact]
    public async Task A_rollback_notifies_nobody()
    {
        using var fixture = new StoreFixture();
        var notifier = ActivityNotifications.For(fixture.Database);
        var uow = await UnitOfWork.OpenAsync(fixture.Database);
        await using (uow)
        {
            await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(ActivityEventTypes.AuthLogout, "auth", "Rolled back", "alice"));
            await uow.RollbackAsync();
            await uow.CommitAsync();
        }

        Assert.Equal(new ActivityLatest(null, 0), notifier.Snapshot());
        Assert.Equal(0, await fixture.Scalar("SELECT count(*) FROM activity_events WHERE title = 'Rolled back'"));
    }

    [Fact]
    public async Task Update_activity_event_reclassifies_and_notifies_the_same_row_after_commit()
    {
        using var fixture = new StoreFixture();
        var notifier = ActivityNotifications.For(fixture.Database);
        var writer = new SqliteActivityWriter(fixture.Database);
        var id = await writer.RecordAsync(new ActivityEventDraft(ActivityEventTypes.RefinerFileProcessingProgress, "refiner", "Refiner is processing movie.mkv", "{\"percent\":10}"));
        Assert.Equal(new ActivityLatest(id, 1), notifier.Snapshot());

        var uow = await UnitOfWork.OpenAsync(fixture.Database);
        await using (uow)
        {
            Assert.True(await SqliteActivityWriter.UpdateAsync(uow, id, eventType: ActivityEventTypes.RefinerFileRemuxPassCompleted, detail: "{\"percent\":42,\"ok\":false,\"relative_media_path\":\"m.mkv\"}"));
            Assert.False(await SqliteActivityWriter.UpdateAsync(uow, id + 100, title: "missing"));
            Assert.Equal(new ActivityLatest(id, 1), notifier.Snapshot());
            await uow.CommitAsync();
        }

        Assert.Equal(new ActivityLatest(id, 2), notifier.Snapshot());
        Assert.Equal(1, await fixture.Scalar(
            $"SELECT count(*) FROM activity_events WHERE id = {id} AND title = 'Refiner is processing movie.mkv' AND result = 'failed' AND relative_path = 'm.mkv' AND event_type = 'refiner.file_remux_pass_completed'"));
    }

    [Fact]
    public async Task Activity_written_in_a_job_store_transaction_notifies_after_its_commit()
    {
        using var db = new JobsTestDatabase(keepSeedRows: true);
        var notifier = ActivityNotifications.For(db.Database);
        var id = await db.Store.InTransactionAsync((connection, transaction) =>
        {
            var inserted = SqliteActivityWriter.Record(connection, transaction, new ActivityEventDraft("refiner.x_completed", "refiner", "raw", null));
            Assert.Equal(0, notifier.Snapshot().Version);
            return inserted;
        });
        Assert.Equal(new ActivityLatest(id, 1), notifier.Snapshot());
    }

    [Fact]
    public async Task Processing_records_past_their_retention_are_pruned_and_zero_keeps_everything()
    {
        using var db = new JobsTestDatabase(keepSeedRows: true);
        var now = new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero);
        db.Execute(
            "INSERT INTO refiner_file_logs (relative_path, recorded_at) VALUES ('old.mkv', '2026-03-01 11:59:59.000000'), ('edge.mkv', '2026-03-03 12:00:00.000000'), ('new.mkv', '2026-05-31 00:00:00')");

        db.Execute("UPDATE refiner_operator_settings SET file_log_retention_days = 0");
        Assert.Equal(0, await RefinerFileLogRetention.PruneOnceAsync(db.Store, now));

        db.Execute("UPDATE refiner_operator_settings SET file_log_retention_days = 90");
        Assert.Equal(1, await RefinerFileLogRetention.PruneOnceAsync(db.Store, now));
        Assert.Equal(2, db.Count("SELECT count(*) FROM refiner_file_logs"));

        // No settings row: Python creates it with 90 days.
        db.Execute("DELETE FROM refiner_operator_settings");
        Assert.Equal(0, await RefinerFileLogRetention.PruneOnceAsync(db.Store, now));
        Assert.Equal(1, await RefinerFileLogRetention.PruneOnceAsync(db.Store, now.AddDays(1)));
        Assert.Equal("new.mkv", db.Scalar("SELECT group_concat(relative_path) FROM refiner_file_logs"));
    }

    [Fact]
    public void Csv_quotes_only_what_the_excel_dialect_quotes()
    {
        var row = new ActivityEventRow(7, PyDateTime.Naive(new DateTime(2026, 1, 2, 3, 4, 5)), "a.b", "refiner", "comma, \"quote\"", "line\nbreak", null, null, null, "plain;tab\t", null);
        Assert.Equal(
            "id,created_at,module,event_type,trigger,result,library_id,relative_path,title,detail\r\n" +
            "7,2026-01-02T03:04:05,refiner,a.b,,,,plain;tab\t,\"comma, \"\"quote\"\"\",\"line\nbreak\"\r\n",
            ActivityHistory.ExportCsv([row]));
    }

    /// <summary>The same rows and filters answered by the Python router functions and by .NET, compared byte for byte.</summary>
    [PythonFact]
    public async Task Recent_and_export_bytes_match_the_python_router_on_the_same_database()
    {
        using var fixture = new StoreFixture();
        await fixture.Execute(
            "INSERT INTO activity_events (created_at, event_type, module, title, detail, \"trigger\", result, library_id, relative_path, run_key) VALUES " +
            "('2026-01-02 03:04:05', 'refiner.file_remux_pass_completed', 'refiner', 'plain', NULL, NULL, 'success', NULL, NULL, NULL), " +
            "('2026-01-02 03:04:05', 'refiner.file_remux_pass_completed', 'refiner', 'comma, \"Quote\"', 'line1\nline2\r\nline3', 'manual', 'success', 3, 'Film/ä ö.mkv', 'run:1'), " +
            "('2026-01-02 03:04:05.123456', 'auth.login_succeeded', 'auth', 'unicode ☃ 😀', 'alice', 'manual', 'success', NULL, NULL, NULL), " +
            "('2026-01-03 00:00:00+00:00', 'refiner.worker_failure', 'refiner', 'aware', '{\"x\": \"tab\there\"}', 'retry', 'failed', 1, '', 'run:9'), " +
            "('2025-12-31 23:59:59.5', 'system.reconciliation.repair', 'system', 'oldest', ';', 'manual', NULL, NULL, 'Show/S01E01.mkv', NULL), " +
            "('2026-01-02 03:04:05', 'auth.logout', 'auth', 'tie a', 'alice', 'manual', NULL, NULL, NULL, NULL), " +
            "('2026-01-02 03:04:05', 'refiner.file_passed_through', 'refiner', 'tie b', NULL, 'manual', 'success', 3, 'Film/ä ö.mkv', NULL), " +
            "('2026-01-02 03:04:05', 'refiner.file_passed_through', 'refiner', 'tie c', NULL, 'webhook', 'success', 1, 'x.mkv', NULL)");

        (string Kind, string Query)[] cases =
        [
            ("recent", "limit=50"),
            ("recent", "limit=2"),
            ("recent", "limit=2&before_id=3"),
            ("recent", "limit=1&before_id=8"),
            ("recent", "limit=3&before_id=8"),
            ("recent", "limit=2&before_id=8&module=refiner"),
            ("recent", "limit=2&before_id=8&module=system"),
            ("recent", "limit=1&before_id=8&trigger=manual"),
            ("recent", "limit=2&before_id=9&file=mkv"),
            ("recent", "limit=2&before_id=9&relative_path=x&library_id=3"),
            ("recent", "limit=3"),
            ("recent", "limit=3&module=refiner"),
            ("recent", "module=system"),
            ("recent", "module=refiner&search=QUOTE"),
            ("recent", "file=%C3%A4"),
            ("recent", "trigger=MANUAL&result=success"),
            ("recent", "date_from=2026-01-02T03:04:05"),
            ("recent", "date_from=2026-01-02&date_to=2026-01-03T00:00:00Z"),
            ("recent", "library_id=3&event_type=refiner.file_remux_pass_completed"),
            ("export", "format=csv"),
            ("export", "format=json"),
            ("export", "format=csv&module=refiner&date_to=2026-01-02 03:04:05.5"),
            ("export", "format=json&search=%E2%98%83"),
        ];

        var casesPath = fixture.Home.Join("cases.json");
        var outputPath = fixture.Home.Join("python-output.json");
        await File.WriteAllTextAsync(casesPath, JsonSerializer.Serialize(cases.Select(c => new[] { c.Kind, c.Query })));
        PythonBackend.Run(
            "import base64, json, os\n" +
            "from urllib.parse import parse_qsl\n" +
            "import weir.api.factory  # registers every ORM model\n" +
            "from weir.core.config import WeirSettings\n" +
            "from weir.core.db import create_db_engine, create_session_factory\n" +
            "from weir.platform.activity.router import get_activity_export, get_activity_recent\n" +
            "s = WeirSettings.load()\n" +
            "fac = create_session_factory(create_db_engine(s))\n" +
            "out = []\n" +
            "for kind, query in json.load(open(os.environ['CASES'], encoding='utf-8')):\n" +
            "    q = dict(parse_qsl(query))\n" +
            "    kw = {k: q.get(k) for k in ('module', 'event_type', 'search', 'date_from', 'date_to', 'trigger', 'result', 'file')}\n" +
            "    kw['library_id'] = int(q['library_id']) if 'library_id' in q else None\n" +
            "    with fac() as db:\n" +
            "        if kind == 'recent':\n" +
            "            r = get_activity_recent(None, db, limit=int(q.get('limit', 50)), before_id=int(q['before_id']) if 'before_id' in q else None, **kw)\n" +
            "            body = json.dumps(r.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':')).encode('utf-8')\n" +
            "        else:\n" +
            "            body = get_activity_export(None, db, export_format=q['format'], **kw).body\n" +
            "    out.append(base64.b64encode(body).decode('ascii'))\n" +
            "json.dump(out, open(os.environ['OUT'], 'w', encoding='utf-8'))\n",
            new Dictionary<string, string> { ["WEIR_HOME"] = fixture.Home.Path, ["CASES"] = casesPath, ["OUT"] = outputPath });

        var python = JsonSerializer.Deserialize<string[]>(await File.ReadAllTextAsync(outputPath))!.Select(Convert.FromBase64String).ToArray();
        for (var index = 0; index < cases.Length; index++)
        {
            var (kind, query) = cases[index];
            var dotnet = await fixture.WithUnitOfWork(uow => DotnetBodyAsync(uow, kind, query));
            Assert.True(
                python[index].AsSpan().SequenceEqual(dotnet),
                $"{kind}?{query}\npython: {Encoding.UTF8.GetString(python[index])}\ndotnet: {Encoding.UTF8.GetString(dotnet)}");
        }
    }

    private static async Task<byte[]> DotnetBodyAsync(UnitOfWork uow, string kind, string query)
    {
        var q = query.Split('&').Select(part => part.Split('=', 2)).ToDictionary(pair => pair[0], pair => Uri.UnescapeDataString(pair[1]), StringComparer.Ordinal);
        string? Get(string name) => q.TryGetValue(name, out var value) ? value : null;
        PyDateTime? When(string name) => Get(name) is { } raw && PyDateTime.TryFromIsoFormat(raw, out var value) ? value : null;
        var filter = new ActivityFilter(
            Get("module"), Get("event_type"), Get("search"), When("date_from"), When("date_to"), Get("trigger"), Get("result"),
            Get("library_id") is { } library ? long.Parse(library, System.Globalization.CultureInfo.InvariantCulture) : null,
            Get("file"));
        if (kind == "recent")
        {
            var limit = Get("limit") is { } rawLimit ? long.Parse(rawLimit, System.Globalization.CultureInfo.InvariantCulture) : 50;
            long? beforeId = Get("before_id") is { } before ? long.Parse(before, System.Globalization.CultureInfo.InvariantCulture) : null;
            var rows = await ActivityHistoryStore.ListRecentAsync(uow, filter, limit, beforeId);
            var body = ActivityHistory.RecentOut(
                rows,
                await ActivityHistoryStore.CountAsync(uow, filter),
                await ActivityHistoryStore.CountSystemAsync(uow, filter),
                (await SuiteSettingsStore.EnsureAsync(uow)).ActivityRetentionDays,
                await ActivityHistoryStore.OldestCreatedAtAsync(uow));
            return PyJsonWriter.DumpsUtf8(body, PyJsonFormat.Response);
        }

        var exported = await ActivityHistoryStore.ListForExportAsync(uow, filter);
        return Encoding.UTF8.GetBytes(Get("format") == "json" ? ActivityHistory.ExportJson(exported) : ActivityHistory.ExportCsv(exported));
    }
}
