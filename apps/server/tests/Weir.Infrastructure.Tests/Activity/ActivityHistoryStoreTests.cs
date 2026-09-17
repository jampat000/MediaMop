using System.Text;
using System.Text.Json;
using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Refiner;
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

        async Task<int> PruneOnceAsync(DateTimeOffset moment)
        {
            var uow = await UnitOfWork.OpenAsync(db.Database);
            await using (uow)
            {
                var operatorRow = await OperatorSettingsStore.EnsureAsync(uow);
                if (operatorRow.FileLogRetentionDays <= 0)
                {
                    return 0;
                }

                var removed = await FileLogStore.PruneAsync(uow, operatorRow.FileLogRetentionDays, moment);
                await uow.CommitAsync();
                return removed;
            }
        }

        db.Execute("UPDATE refiner_operator_settings SET file_log_retention_days = 0");
        Assert.Equal(0, await PruneOnceAsync(now));

        db.Execute("UPDATE refiner_operator_settings SET file_log_retention_days = 90");
        Assert.Equal(1, await PruneOnceAsync(now));
        Assert.Equal(2, db.Count("SELECT count(*) FROM refiner_file_logs"));

        // No settings row: Python creates it with 90 days.
        db.Execute("DELETE FROM refiner_operator_settings");
        Assert.Equal(0, await PruneOnceAsync(now));
        Assert.Equal(1, await PruneOnceAsync(now.AddDays(1)));
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

    /// <summary>#543 item 1: Python's dropped-FROM count query always counts one row with no filter; .NET counts them all.</summary>
    [Fact]
    public async Task Count_activity_events_counts_every_row_even_unfiltered()
    {
        using var fixture = new StoreFixture();
        await fixture.Execute(
            "INSERT INTO activity_events (created_at, event_type, module, title) VALUES " +
            "('2026-01-01 00:00:01', 'a.1', 'refiner', 'one'), " +
            "('2026-01-01 00:00:02', 'a.2', 'refiner', 'two'), " +
            "('2026-01-01 00:00:03', 'a.3', 'refiner', 'three')");

        Assert.Equal(3, await fixture.WithUnitOfWork(uow => ActivityHistoryStore.CountAsync(uow, ActivityFilter.None)));

        var (total, hasMore, pageCount) = await fixture.WithUnitOfWork(async uow =>
        {
            var rows = await ActivityHistoryStore.ListRecentAsync(uow, ActivityFilter.None, limit: 2, beforeId: null);
            var count = await ActivityHistoryStore.CountAsync(uow, ActivityFilter.None);
            var body = ActivityHistory.RecentOut(rows, count, 0, 90, null);
            using var doc = JsonDocument.Parse(PyJsonWriter.DumpsUtf8(body, PyJsonFormat.Response));
            return (doc.RootElement.GetProperty("total").GetInt64(), doc.RootElement.GetProperty("has_more").GetBoolean(), rows.Count);
        });
        Assert.Equal(3, total);
        Assert.True(hasMore);
        Assert.Equal(2, pageCount);
    }

    /// <summary>
    /// #543 item 3: ordered by <c>(created_at DESC, id DESC)</c>, and <c>before_id</c> pages by that same key.
    /// Row 2 is chronologically the oldest despite its small id, and rows 1 and 3 tie — an arrangement plain
    /// <c>id &lt; before_id</c> paging (Python's, and .NET's before #543) gets wrong: it would repeat row 4 on
    /// a later page (its id is small, but it was already returned) or lose rows entirely.
    /// </summary>
    [Fact]
    public async Task List_recent_pages_by_before_id_without_skipping_or_repeating_a_tied_row()
    {
        using var fixture = new StoreFixture();
        await fixture.Execute(
            "INSERT INTO activity_events (created_at, event_type, module, title) VALUES " +
            "('2026-01-01 00:00:10', 'a.1', 'refiner', 'A'), " + // id 1, ties id 3
            "('2026-01-01 00:00:05', 'a.2', 'refiner', 'B'), " + // id 2, older than id 1 and id 3
            "('2026-01-01 00:00:10', 'a.3', 'refiner', 'C'), " + // id 3, ties id 1
            "('2026-01-01 00:00:01', 'a.4', 'refiner', 'D')"); // id 4, oldest

        var first = await fixture.WithUnitOfWork(uow => ActivityHistoryStore.ListRecentAsync(uow, ActivityFilter.None, limit: 2, beforeId: null));
        Assert.Equal(["C", "A"], first.Select(r => r.Title)); // the tie broken by id DESC: 3 before 1

        var second = await fixture.WithUnitOfWork(uow => ActivityHistoryStore.ListRecentAsync(uow, ActivityFilter.None, limit: 2, beforeId: first[^1].Id));
        Assert.Equal(["B", "D"], second.Select(r => r.Title)); // never id 1 again, never loses B or D

        Assert.Equal(4, first.Concat(second).Select(r => r.Id).Distinct().Count());
    }

    /// <summary>A cursor row that no longer exists (deleted since the page it came from was read) still pages, by id alone.</summary>
    [Fact]
    public async Task List_recent_before_a_missing_cursor_row_falls_back_to_id_only_paging()
    {
        using var fixture = new StoreFixture();
        await fixture.Execute(
            "INSERT INTO activity_events (created_at, event_type, module, title) VALUES " +
            "('2026-01-01 00:00:01', 'a.1', 'refiner', 'one'), " +
            "('2026-01-01 00:00:02', 'a.2', 'refiner', 'two')");

        var rows = await fixture.WithUnitOfWork(uow => ActivityHistoryStore.ListRecentAsync(uow, ActivityFilter.None, limit: 10, beforeId: 999));
        Assert.Equal(["two", "one"], rows.Select(r => r.Title));
    }

    /// <summary>
    /// #543 item 2: a query offset must be honored (not silently taken as the naive wall clock), and a stored
    /// row without a fractional part must not be excluded from a boundary that names its exact second.
    /// </summary>
    [Fact]
    public async Task Date_filters_normalize_to_utc_and_compare_stored_shapes_not_raw_text()
    {
        using var fixture = new StoreFixture();
        // Stored with no fractional part: the shape SQLAlchemy (and Weir) write for an exact second.
        await fixture.Execute(
            "INSERT INTO activity_events (created_at, event_type, module, title) VALUES ('2026-01-02 03:04:05', 'a.1', 'refiner', 'exact')");

        Assert.True(PyDateTime.TryFromIsoFormat("2026-01-02T03:04:05", out var naiveBoundary));
        var atBoundary = new ActivityFilter(DateFrom: naiveBoundary);
        Assert.Single(await fixture.WithUnitOfWork(uow => ActivityHistoryStore.ListRecentAsync(uow, atBoundary, limit: 10, beforeId: null)));

        // The same instant, named with a +02:00 offset: an ignored offset would compare "05:04:05" against
        // the stored "03:04:05" and wrongly exclude the row.
        Assert.True(PyDateTime.TryFromIsoFormat("2026-01-02T05:04:05+02:00", out var sameInstantOffset));
        var atOffsetBoundary = new ActivityFilter(DateFrom: sameInstantOffset);
        Assert.Single(await fixture.WithUnitOfWork(uow => ActivityHistoryStore.ListRecentAsync(uow, atOffsetBoundary, limit: 10, beforeId: null)));

        // One second later in the same offset: now past the row, in either timezone.
        Assert.True(PyDateTime.TryFromIsoFormat("2026-01-02T06:04:06+02:00", out var pastIt));
        var pastFilter = new ActivityFilter(DateFrom: pastIt);
        Assert.Empty(await fixture.WithUnitOfWork(uow => ActivityHistoryStore.ListRecentAsync(uow, pastFilter, limit: 10, beforeId: null)));
    }

    /// <summary>
    /// #543 item 4: <c>_file_history_filter</c> (Activity events) already matches a row that never recorded a
    /// library id even when one is given; processing records now get the same fallback, so removing one
    /// file's history with a library id cleans up both consistently instead of leaving old records behind.
    /// </summary>
    [Fact]
    public async Task File_history_removal_gives_processing_records_the_same_library_null_fallback_as_events()
    {
        using var fixture = new StoreFixture();
        await fixture.Execute(
            "INSERT INTO activity_events (created_at, event_type, module, title, relative_path, library_id) VALUES " +
            "('2026-01-01 00:00:01', 'a.1', 'refiner', 'no library recorded', 'Film/movie.mkv', NULL)");
        await fixture.Execute(
            "INSERT INTO refiner_file_logs (relative_path, recorded_at, library_id) VALUES ('Film/movie.mkv', '2026-01-01 00:00:01', NULL)");

        var counts = await fixture.WithUnitOfWork(uow => ActivityHistoryStore.CountFileHistoryAsync(uow, libraryId: 7, "Film/movie.mkv"));
        Assert.Equal(1, counts.ActivityEvents);
        Assert.Equal(1, counts.ProcessingRecords);

        var deleted = await fixture.WithUnitOfWork(uow => ActivityHistoryStore.DeleteFileHistoryAsync(uow, libraryId: 7, "Film/movie.mkv"));
        Assert.Equal(1, deleted.ActivityEvents);
        Assert.Equal(1, deleted.ProcessingRecords);
    }

    /// <summary>
    /// The same rows and filters answered by the Python router functions and by .NET, compared byte for byte —
    /// except the cases tagged with a <c>#543</c> issue number, where .NET now gives the *fixed* answer and
    /// Python still gives the old, buggy one (items 1 and 3; both kept faithfully everywhere else). Those
    /// cases assert the two bodies differ, so a Python fix (or an accidental regression back to parity) is
    /// caught rather than silently ignored; <see cref="Count_activity_events_counts_every_row_even_unfiltered"/>
    /// and <see cref="List_recent_pages_by_before_id_without_skipping_or_repeating_a_tied_row"/> assert what the
    /// fixed .NET answer actually is.
    /// </summary>
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

        // DivergesForIssue: null keeps byte-for-byte parity; #543 marks a case whose .NET answer is now the
        // fixed one (item 1: total/has_more with no filter; item 3: created_at ties and before_id paging).
        (string Kind, string Query, int? DivergesForIssue)[] cases =
        [
            ("recent", "limit=50", null),
            ("recent", "limit=2", 543), // item 1: 8 rows exist; python's total is still the dropped-FROM 1
            ("recent", "limit=2&before_id=3", 543), // item 3: python pages id<3 alone; .NET anchors on id 3's created_at too
            ("recent", "limit=1&before_id=8", 543), // item 3: python repeats id 4 here, already returned before id 8
            ("recent", "limit=3&before_id=8", 543), // item 3: same repeat, over a longer page
            ("recent", "limit=2&before_id=8&module=refiner", 543), // item 3: paging order, with a filter applied too
            ("recent", "limit=2&before_id=8&module=system", 543), // item 3: paging order, with a filter applied too
            ("recent", "limit=1&before_id=8&trigger=manual", 543), // item 3: paging order, with a filter applied too
            ("recent", "limit=2&before_id=9&file=mkv", null), // before_id 9 has no row either side of the fix: same fallback
            ("recent", "limit=2&before_id=9&relative_path=x&library_id=3", null), // same: id 9 never existed
            ("recent", "limit=3", 543), // item 1 total (8 rows, page of 3) and item 3's created_at-tie order both move
            ("recent", "limit=3&module=refiner", 543), // item 3: the tied refiner rows now cut off in id-DESC order
            ("recent", "module=system", null),
            ("recent", "module=refiner&search=QUOTE", null),
            ("recent", "file=%C3%A4", null),
            ("recent", "trigger=MANUAL&result=success", null),
            ("recent", "date_from=2026-01-02T03:04:05", 543), // item 2: python excludes the exact-second rows; .NET keeps them
            ("recent", "date_from=2026-01-02&date_to=2026-01-03T00:00:00Z", null), // no row sits on a text-format boundary here
            ("recent", "library_id=3&event_type=refiner.file_remux_pass_completed", null),
            ("export", "format=csv", null),
            ("export", "format=json", null),
            ("export", "format=csv&module=refiner&date_to=2026-01-02 03:04:05.5", null),
            ("export", "format=json&search=%E2%98%83", null),
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
        var failures = new List<string>();
        for (var index = 0; index < cases.Length; index++)
        {
            var (kind, query, divergesForIssue) = cases[index];
            var dotnet = await fixture.WithUnitOfWork(uow => DotnetBodyAsync(uow, kind, query));
            var matches = python[index].AsSpan().SequenceEqual(dotnet);
            if (divergesForIssue is { } issue)
            {
                // The fix must actually change the answer: an accidental match here means either Python's bug
                // was fixed too (drop the marker) or .NET's fix silently stopped applying (a regression).
                if (matches)
                {
                    failures.Add(
                        $"{kind}?{query}\nmarked as diverging for #{issue}, but matched Python byte for byte:\n{Encoding.UTF8.GetString(dotnet)}");
                }
            }
            else if (!matches)
            {
                failures.Add($"{kind}?{query}\npython: {Encoding.UTF8.GetString(python[index])}\ndotnet: {Encoding.UTF8.GetString(dotnet)}");
            }
        }
        Assert.True(failures.Count == 0, string.Join("\n---\n", failures));
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
