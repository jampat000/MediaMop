using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>SQLite access for <c>refiner_file_logs</c> (port of <c>refiner_file_log_service.py</c>).</summary>
public static class FileLogStore
{
    public const int MaxDetailChars = 200_000;

    private const string Columns = "id, file_id, library_id, relative_path, library_name, outcome, title, detail_json, recorded_at";

    /// <summary><c>logs_for_file</c>: every retained pass over this file, newest first, matched by path.</summary>
    public static Task<List<RefinerFileLogRecord>> LogsForFileAsync(UnitOfWork uow, string relativePath, int limit) =>
        uow.QueryAsync(
            $"SELECT {Columns} FROM refiner_file_logs WHERE relative_path = @path ORDER BY recorded_at DESC, id DESC LIMIT {Math.Max(1, Math.Min(limit, 500))}",
            Read, ("@path", relativePath));

    /// <summary>Parse a stored detail payload as a <see cref="PyDict"/>, never raising.</summary>
    public static PyDict ParseDetail(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return new PyDict();
        }

        try
        {
            return PyJsonParser.Parse(raw) switch
            {
                PyDict dict => dict,
                PyJson other => new PyDict().Set("detail", other),
            };
        }
        catch (PyJsonDecodeException)
        {
            return new PyDict().Set("unparsed_detail", raw);
        }
    }

    /// <summary><c>render_log_text</c>: a plain-text rendering for attaching to a bug report.</summary>
    public static string RenderLogText(IReadOnlyList<RefinerFileLogRecord> rows)
    {
        if (rows.Count == 0)
        {
            return "Weir has no retained processing records for this file.\n";
        }

        var lines = new List<string>();
        var first = rows[0];
        lines.Add($"Weir — processing record for {first.RelativePath}");
        if (first.LibraryName.Length > 0)
        {
            lines.Add($"Library: {first.LibraryName}");
        }

        lines.Add($"Records retained: {rows.Count} (newest first)");
        lines.Add(string.Empty);

        foreach (var row in rows)
        {
            lines.Add(new string('=', 78));
            lines.Add($"{row.RecordedAt.PydanticJson()}  —  {(row.Outcome.Length > 0 ? row.Outcome : "no outcome recorded")}");
            if (row.Title.Length > 0)
            {
                lines.Add(row.Title);
            }

            lines.Add(new string('-', 78));
            var detail = ParseDetail(row.DetailJson);
            foreach (var key in detail.Keys.Order(StringComparer.Ordinal))
            {
                var value = detail[key];
                var rendered = value is PyDict or PyList ? PyJsonWriter.Dumps(value, PyJsonFormat.Compact) : PlainValue(value);
                lines.Add($"{key}: {rendered}");
            }

            lines.Add(string.Empty);
        }

        return string.Join('\n', lines) + "\n";
    }

    private static string PlainValue(PyJson value) => value switch
    {
        PyStr s => s.Value,
        PyInt i => i.Value.ToString(CultureInfo.InvariantCulture),
        PyFloat f => f.Value.ToString(CultureInfo.InvariantCulture),
        PyBool b => b.Value ? "True" : "False",
        PyNull => "None",
        _ => string.Empty,
    };

    /// <summary><c>prune_file_logs</c>: delete records older than the retention window. 0 keeps everything.</summary>
    public static async Task<int> PruneAsync(UnitOfWork uow, long retentionDays, DateTimeOffset now)
    {
        if (retentionDays <= 0)
        {
            return 0;
        }

        var cutoff = now.AddDays(-retentionDays);
        return await uow.ExecuteAsync(
            "DELETE FROM refiner_file_logs WHERE recorded_at < @cutoff",
            ("@cutoff", SqliteValues.ToSqlite(PyDateTime.FromUtc(cutoff.UtcDateTime)))).ConfigureAwait(false);
    }

    private static RefinerFileLogRecord Read(SqliteDataReader reader) => new()
    {
        Id = reader.GetInt64(0),
        FileId = reader.IsDBNull(1) ? null : reader.GetInt64(1),
        LibraryId = reader.IsDBNull(2) ? null : reader.GetInt64(2),
        RelativePath = SqliteValues.GetString(reader, 3),
        LibraryName = SqliteValues.GetString(reader, 4),
        Outcome = SqliteValues.GetString(reader, 5),
        Title = SqliteValues.GetString(reader, 6),
        DetailJson = SqliteValues.GetString(reader, 7),
        RecordedAt = SqliteValues.GetDateTime(reader, 8),
    };
}
