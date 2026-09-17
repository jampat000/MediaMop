using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Activity;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Activity;

/// <summary>
/// Reading and removing Activity history (the query half of <c>weir.platform.activity.service</c>, plus the
/// processing-record statements of its router). The SQL is the text SQLAlchemy compiles, clause for clause,
/// except for the defects fixed in #543 (the <c>total</c>/<c>has_more</c> count, date-filter comparison,
/// paging order, and the file-history library fallback) — each documented where it is fixed. Python keeps
/// those defects; the byte-for-byte comparisons against it are only for cases they do not touch.
/// </summary>
public static class ActivityHistoryStore
{
    private const string Columns =
        "activity_events.id, activity_events.created_at, activity_events.event_type, activity_events.module, activity_events.title, " +
        "activity_events.detail, activity_events.\"trigger\", activity_events.result, activity_events.library_id, " +
        "activity_events.relative_path, activity_events.run_key";

    /// <summary>
    /// <c>list_recent_activity_events</c>: newest first, at most 100. #543 item 3: ordered by
    /// <c>(created_at DESC, id DESC)</c>, a total order that no longer depends on which plan SQLite
    /// chooses for ties (the old code range-scanned the rowid with a unary-plus hint to keep .NET's
    /// SQLite 3.53 choosing the same plan as the Python backend's 3.45; needless once ties have an
    /// explicit tie-breaker). <paramref name="beforeId"/> pages by that same key: everything strictly
    /// after the cursor row in the order, not just a smaller id, so a row tied on <c>created_at</c> with
    /// the cursor is never skipped or repeated. Python still pages by id alone (bug kept there on purpose).
    /// </summary>
    public static async Task<List<ActivityEventRow>> ListRecentAsync(UnitOfWork uow, ActivityFilter filter, long limit, long? beforeId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var (where, parameters) = Where(filter);
        if (beforeId is { } before)
        {
            var cursor = await uow.ScalarAsync(
                "SELECT activity_events.created_at FROM activity_events WHERE activity_events.id = @before_id",
                ("@before_id", before)).ConfigureAwait(false);
            if (cursor is string beforeCreatedAt)
            {
                where.Add(
                    "(activity_events.created_at < @before_created_at OR " +
                    "(activity_events.created_at = @before_created_at AND activity_events.id < @before_id))");
                parameters.Add(("@before_created_at", beforeCreatedAt));
                parameters.Add(("@before_id", before));
            }
            else
            {
                // The cursor row is gone (deleted since the page it came from was read): no created_at to
                // anchor on, so fall back to Weir's best guess, an id-only cursor.
                where.Add("activity_events.id < @before_id");
                parameters.Add(("@before_id", before));
            }
        }

        parameters.Add(("@limit", Math.Max(1, Math.Min(limit, 100))));
        return await uow.QueryAsync(
            $"SELECT {Columns} FROM activity_events{WhereText(where)} ORDER BY activity_events.created_at DESC, activity_events.id DESC LIMIT @limit OFFSET 0",
            ReadRow,
            [.. parameters]).ConfigureAwait(false);
    }

    /// <summary><c>list_activity_events_for_export</c>: oldest first, up to <see cref="ActivityHistory.ExportMaxRows"/>.</summary>
    public static Task<List<ActivityEventRow>> ListForExportAsync(UnitOfWork uow, ActivityFilter filter)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var (where, parameters) = Where(filter);
        parameters.Add(("@limit", ActivityHistory.ExportMaxRows));
        return uow.QueryAsync(
            $"SELECT {Columns} FROM activity_events{WhereText(where)} ORDER BY activity_events.created_at, activity_events.id LIMIT @limit OFFSET 0",
            ReadRow,
            [.. parameters]);
    }

    /// <summary>
    /// <c>count_activity_events</c>. #543 item 1: Python's SQLAlchemy statement replaces the columns with
    /// <c>count(*)</c> and, when there is no filter, drops the FROM clause along with them — the statement
    /// becomes <c>SELECT count(*)</c>, which always counts one regardless of how many rows exist. Fixed here:
    /// always count from <c>activity_events</c>, filtered or not.
    /// </summary>
    public static Task<long> CountAsync(UnitOfWork uow, ActivityFilter filter)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var (where, parameters) = Where(filter);
        return uow.CountAsync($"SELECT count(*) AS count_1 FROM activity_events{WhereText(where)}", [.. parameters]);
    }

    /// <summary><c>count_system_activity_events</c>: everything outside Refiner, with the other filters that apply to it.</summary>
    public static Task<long> CountSystemAsync(UnitOfWork uow, ActivityFilter filter)
    {
        ArgumentNullException.ThrowIfNull(filter);
        return CountAsync(uow, new ActivityFilter(Module: "system", EventType: filter.EventType, Search: filter.Search, DateFrom: filter.DateFrom, DateTo: filter.DateTo));
    }

    /// <summary><c>get_oldest_activity_event_at</c>.</summary>
    public static async Task<PyDateTime?> OldestCreatedAtAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync("SELECT min(activity_events.created_at) AS min_1 FROM activity_events", reader => SqliteValues.GetDateTimeOrNull(reader, 0)).ConfigureAwait(false);
        return rows.Count == 0 ? null : rows[0];
    }

    /// <summary><c>get_latest_activity_event_id</c>: the cheap freshness probe of the live stream.</summary>
    public static async Task<long?> LatestIdAsync(SqliteDatabase database, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(database);
        var connection = await database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            var command = connection.CreateCommand();
            await using (command.ConfigureAwait(false))
            {
                command.CommandText = "SELECT max(activity_events.id) AS max_1 FROM activity_events";
                var value = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
                return value is null or DBNull ? null : Convert.ToInt64(value, CultureInfo.InvariantCulture);
            }
        }
    }

    /// <summary><c>count_file_activity_history</c> and the processing-record count of <c>get_activity_file_history</c>.</summary>
    public static async Task<FileHistoryCounts> CountFileHistoryAsync(UnitOfWork uow, long? libraryId, string relativePath)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var (clause, parameters) = FileHistoryClause(libraryId, relativePath);
        var events = await uow.CountAsync($"SELECT count(*) AS count_1 FROM activity_events WHERE {clause}", parameters).ConfigureAwait(false);
        var (recordsClause, recordsParameters) = ProcessingRecordsClause(libraryId, relativePath);
        var records = await uow.CountAsync(
            "SELECT count(*) AS count_1 FROM (SELECT refiner_file_logs.id AS id, refiner_file_logs.file_id AS file_id, " +
            "refiner_file_logs.library_id AS library_id, refiner_file_logs.relative_path AS relative_path, " +
            "refiner_file_logs.library_name AS library_name, refiner_file_logs.outcome AS outcome, refiner_file_logs.title AS title, " +
            "refiner_file_logs.detail_json AS detail_json, refiner_file_logs.recorded_at AS recorded_at FROM refiner_file_logs " +
            $"WHERE {recordsClause}) AS anon_1",
            recordsParameters).ConfigureAwait(false);
        return new FileHistoryCounts(relativePath, events, records);
    }

    /// <summary><c>delete_file_activity_history</c> and the processing-record delete of <c>post_activity_file_history_remove</c>.</summary>
    public static async Task<FileHistoryCounts> DeleteFileHistoryAsync(UnitOfWork uow, long? libraryId, string relativePath)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var (clause, parameters) = FileHistoryClause(libraryId, relativePath);
        var events = await uow.ExecuteAsync($"DELETE FROM activity_events WHERE {clause}", parameters).ConfigureAwait(false);
        var (recordsClause, recordsParameters) = ProcessingRecordsClause(libraryId, relativePath);
        var records = await uow.ExecuteAsync($"DELETE FROM refiner_file_logs WHERE {recordsClause}", recordsParameters).ConfigureAwait(false);
        return new FileHistoryCounts(relativePath, events, records);
    }

    /// <summary><c>_filtered_activity_stmt</c>'s WHERE clauses, in Python's order.</summary>
    private static (List<string> Where, List<(string Name, object? Value)> Parameters) Where(ActivityFilter filter)
    {
        ArgumentNullException.ThrowIfNull(filter);
        var where = new List<string>();
        var parameters = new List<(string Name, object? Value)>();
        if (!string.IsNullOrEmpty(filter.Trigger))
        {
            where.Add("activity_events.\"trigger\" = @trigger");
            parameters.Add(("@trigger", Core.Json.PyStrings.Strip(filter.Trigger).ToLowerInvariant()));
        }

        if (!string.IsNullOrEmpty(filter.Result))
        {
            where.Add("activity_events.result = @result");
            parameters.Add(("@result", Core.Json.PyStrings.Strip(filter.Result).ToLowerInvariant()));
        }

        if (filter.LibraryId is { } libraryId)
        {
            where.Add("activity_events.library_id = @library_id");
            parameters.Add(("@library_id", libraryId));
        }

        if (!string.IsNullOrEmpty(filter.File))
        {
            // A file's whole history: its path, or its name anywhere in a path.
            where.Add("lower(activity_events.relative_path) LIKE lower(@relative_path)");
            parameters.Add(("@relative_path", "%" + Core.Json.PyStrings.Strip(filter.File) + "%"));
        }

        if (!string.IsNullOrEmpty(filter.Module))
        {
            var module = Core.Json.PyStrings.Strip(filter.Module).ToLowerInvariant();
            if (module == "system")
            {
                var names = ActivityHistory.SystemModules.Select((_, index) => $"@module_{index}").ToArray();
                where.Add($"(activity_events.module NOT IN ({string.Join(", ", names)}))");
                parameters.AddRange(ActivityHistory.SystemModules.Select((name, index) => ($"@module_{index}", (object?)name)));
            }
            else
            {
                where.Add("activity_events.module = @module");
                parameters.Add(("@module", module));
            }
        }

        if (!string.IsNullOrEmpty(filter.EventType))
        {
            where.Add("activity_events.event_type = @event_type");
            parameters.Add(("@event_type", Core.Json.PyStrings.Strip(filter.EventType)));
        }

        if (!string.IsNullOrEmpty(filter.Search))
        {
            where.Add(
                "(lower(activity_events.title) LIKE lower(@search_title) OR lower(activity_events.detail) LIKE lower(@search_detail) " +
                "OR lower(activity_events.event_type) LIKE lower(@search_event_type) OR lower(activity_events.module) LIKE lower(@search_module))");
            var pattern = "%" + Core.Json.PyStrings.Strip(filter.Search) + "%";
            parameters.Add(("@search_title", pattern));
            parameters.Add(("@search_detail", pattern));
            parameters.Add(("@search_event_type", pattern));
            parameters.Add(("@search_module", pattern));
        }

        // #543 item 2: Python compares raw text, so a query offset is ignored (only the wall-clock digits
        // are ever bound) and a stored row missing its ".000000" (an exact second) sorts as "less than" the
        // same instant written with one, silently excluding it. Fixed here: normalize the query value to
        // UTC — a naive value is already the server's own clock, so it needs no conversion, only an aware
        // one does — and compare with julianday(), which parses both stored shapes to the same instant.
        if (filter.DateFrom is { } from)
        {
            where.Add("julianday(activity_events.created_at) >= julianday(@date_from)");
            parameters.Add(("@date_from", PyDateTime.FromUtc(from.AsUtc).ToSqlite()));
        }

        if (filter.DateTo is { } to)
        {
            where.Add("julianday(activity_events.created_at) <= julianday(@date_to)");
            parameters.Add(("@date_to", PyDateTime.FromUtc(to.AsUtc).ToSqlite()));
        }

        return (where, parameters);
    }

    private static string WhereText(List<string> where) => where.Count == 0 ? string.Empty : " WHERE " + string.Join(" AND ", where);

    /// <summary><c>_file_history_filter</c>: with a library, events that never recorded one still belong to the file.</summary>
    private static (string Clause, (string Name, object? Value)[] Parameters) FileHistoryClause(long? libraryId, string relativePath)
    {
        var path = Core.Json.PyStrings.Strip(relativePath);
        return libraryId is { } id
            ? ("activity_events.relative_path = @relative_path AND (activity_events.library_id = @library_id OR activity_events.library_id IS NULL)",
                [("@relative_path", path), ("@library_id", id)])
            : ("activity_events.relative_path = @relative_path", [("@relative_path", path)]);
    }

    /// <summary>
    /// <c>_processing_records</c>. #543 item 4: Python requires an exact <c>library_id</c> match here, unlike
    /// <see cref="FileHistoryClause"/>'s events, which also match a record that never recorded one — so
    /// removing one file's history with a library id left processing records about it (recorded before the
    /// library was known) behind. Fixed to match: give processing records the same null fallback.
    /// </summary>
    private static (string Clause, (string Name, object? Value)[] Parameters) ProcessingRecordsClause(long? libraryId, string relativePath) =>
        libraryId is { } id
            ? ("refiner_file_logs.relative_path = @relative_path AND (refiner_file_logs.library_id = @library_id OR refiner_file_logs.library_id IS NULL)",
                [("@relative_path", relativePath), ("@library_id", id)])
            : ("refiner_file_logs.relative_path = @relative_path", [("@relative_path", relativePath)]);

    private static ActivityEventRow ReadRow(SqliteDataReader reader) => new(
        SqliteValues.GetInt64(reader, 0),
        SqliteValues.GetDateTime(reader, 1),
        SqliteValues.GetString(reader, 2),
        SqliteValues.GetString(reader, 3),
        SqliteValues.GetString(reader, 4),
        SqliteValues.GetStringOrNull(reader, 5),
        SqliteValues.GetStringOrNull(reader, 6),
        SqliteValues.GetStringOrNull(reader, 7),
        reader.IsDBNull(8) ? null : SqliteValues.GetInt64(reader, 8),
        SqliteValues.GetStringOrNull(reader, 9),
        SqliteValues.GetStringOrNull(reader, 10));
}
