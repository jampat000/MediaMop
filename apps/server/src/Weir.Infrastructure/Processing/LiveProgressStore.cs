using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing;

/// <summary>How far the pass currently working on a file has got (<c>LiveProgress</c>).</summary>
public sealed record LiveProgress(double? Percent, string? Message, double? EtaSeconds);

/// <summary>
/// Reads the live per-file progress Activity row a running pass keeps updated (port of
/// <c>processing_live_progress.py</c>, #463). Read-only: nothing here writes a second source of truth.
/// </summary>
public static class LiveProgressStore
{
    private static readonly TimeSpan StaleAfter = TimeSpan.FromMinutes(2);
    private static readonly HashSet<string> LiveStatuses = new(StringComparer.Ordinal) { "processing", "finishing" };
    private const int MaxRows = 64;

    /// <summary><c>live_progress_by_path</c>: maps <c>relative_media_path</c> to the progress of the pass running on it.</summary>
    public static async Task<Dictionary<string, LiveProgress>> ByPathAsync(UnitOfWork uow, TimeProvider time)
    {
        var cutoff = time.GetUtcNow() - StaleAfter;
        var rows = await uow.QueryAsync(
            "SELECT detail FROM activity_events WHERE event_type = @type AND created_at >= @cutoff ORDER BY created_at DESC LIMIT " + MaxRows,
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@type", ActivityEventTypes.ProcessingFileProcessingProgress),
            ("@cutoff", SqliteValues.ToSqlite(PyDateTime.FromUtc(cutoff.UtcDateTime)))).ConfigureAwait(false);

        var result = new Dictionary<string, LiveProgress>(StringComparer.Ordinal);
        foreach (var raw in rows)
        {
            if (string.IsNullOrWhiteSpace(raw))
            {
                continue;
            }

            PyJson parsed;
            try
            {
                parsed = PyJsonParser.Parse(raw);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (parsed is not PyDict payload)
            {
                continue;
            }

            var status = payload.TryGetValue("status", out var statusValue) && statusValue is PyStr statusStr ? statusStr.Value.Trim().ToLowerInvariant() : string.Empty;
            if (!LiveStatuses.Contains(status))
            {
                continue;
            }

            var path = payload.TryGetValue("relative_media_path", out var pathValue) && pathValue is PyStr pathStr ? pathStr.Value.Trim() : string.Empty;
            if (path.Length == 0 || result.ContainsKey(path))
            {
                continue;
            }

            result[path] = new LiveProgress(
                CoercePercent(payload.TryGetValue("percent", out var p) ? p : null),
                payload.TryGetValue("message", out var m) && m is PyStr messageStr && messageStr.Value.Trim().Length > 0 ? messageStr.Value.Trim() : null,
                CoerceSeconds(payload.TryGetValue("eta_seconds", out var e) ? e : null));
        }

        return result;
    }

    private static double? CoercePercent(PyJson? value)
    {
        var number = Number(value);
        return number is null || double.IsNaN(number.Value) ? null : Math.Clamp(number.Value, 0.0, 100.0);
    }

    private static double? CoerceSeconds(PyJson? value)
    {
        var number = Number(value);
        return number is null || double.IsNaN(number.Value) || number.Value < 0 ? null : number.Value;
    }

    private static double? Number(PyJson? value) => value switch
    {
        PyInt i => (double)i.Value,
        PyFloat f => f.Value,
        PyBool b => b.Value ? 1.0 : 0.0,
        PyStr s when double.TryParse(s.Value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var parsed) => parsed,
        _ => null,
    };
}
