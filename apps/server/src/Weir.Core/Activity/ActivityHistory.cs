using System.Globalization;
using System.Text;
using Weir.Core.Json;
using Weir.Core.Time;

namespace Weir.Core.Activity;

/// <summary>One persisted <c>activity_events</c> row (<c>weir.platform.activity.models.ActivityEvent</c>).</summary>
public sealed record ActivityEventRow(
    long Id,
    PyDateTime CreatedAt,
    string EventType,
    string Module,
    string Title,
    string? Detail,
    string? Trigger,
    string? Result,
    long? LibraryId,
    string? RelativePath,
    string? RunKey);

/// <summary>
/// The history filters of <c>_filtered_activity_stmt</c>. Each is applied when it is present and non-empty,
/// exactly as Python tests it (so a value of spaces is applied, stripped to nothing).
/// </summary>
public sealed record ActivityFilter(
    string? Module = null,
    string? EventType = null,
    string? Search = null,
    PyDateTime? DateFrom = null,
    PyDateTime? DateTo = null,
    string? Trigger = null,
    string? Result = null,
    long? LibraryId = null,
    string? File = null)
{
    public static readonly ActivityFilter None = new();
}

/// <summary>What removing one file's history would delete, or did delete.</summary>
public sealed record FileHistoryCounts(string RelativePath, long ActivityEvents, long ProcessingRecords);

/// <summary>The response shapes and export formats of <c>weir.platform.activity.router</c> and <c>schemas</c>.</summary>
public static class ActivityHistory
{
    /// <summary><c>RECENT_DEFAULT_LIMIT</c>.</summary>
    public const int RecentDefaultLimit = 50;

    /// <summary><c>EXPORT_MAX_ROWS</c>.</summary>
    public const int ExportMaxRows = 50_000;

    /// <summary><c>_SYSTEM_MODULES</c>: <c>module=system</c> means every module but these.</summary>
    public static readonly IReadOnlyList<string> SystemModules = ["refiner"];

    /// <summary><c>_EXPORT_COLUMNS</c>.</summary>
    public static readonly IReadOnlyList<string> ExportColumns =
        ["id", "created_at", "module", "event_type", "trigger", "result", "library_id", "relative_path", "title", "detail"];

    /// <summary><c>json.dumps(records, ensure_ascii=False, indent=2)</c>.</summary>
    public static readonly PyJsonFormat ExportJsonFormat = new(false, ",", ": ", 2, false);

    /// <summary><c>ActivityEventItemOut</c>.</summary>
    public static PyDict ItemOut(ActivityEventRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return new PyDict()
            .Set("id", row.Id)
            .Set("created_at", row.CreatedAt.PydanticJson())
            .Set("event_type", row.EventType)
            .Set("module", row.Module)
            .Set("title", row.Title)
            .Set("detail", row.Detail)
            .Set("trigger", row.Trigger)
            .Set("result", row.Result)
            .Set("library_id", row.LibraryId)
            .Set("relative_path", row.RelativePath)
            .Set("run_key", row.RunKey);
    }

    /// <summary>
    /// <c>ActivityRecentOut</c> as <c>get_activity_recent</c> builds it: the total is never smaller than the
    /// page, and <c>has_more</c> compares the unclamped count with the page.
    /// </summary>
    public static PyDict RecentOut(IReadOnlyList<ActivityEventRow> rows, long total, long systemEvents, long retentionDays, PyDateTime? oldestEventAt)
    {
        ArgumentNullException.ThrowIfNull(rows);
        return new PyDict()
            .Set("items", new PyList(rows.Select(row => (PyJson)ItemOut(row))))
            .Set("total", Math.Max(total, rows.Count))
            .Set("system_events", systemEvents)
            .Set("has_more", total > rows.Count)
            .Set("retention_days", retentionDays)
            .Set("oldest_event_at", oldestEventAt?.PydanticJson());
    }

    /// <summary>One export record: <c>created_at</c> is <c>isoformat()</c>, every other column as stored.</summary>
    public static PyDict ExportRecord(ActivityEventRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return new PyDict()
            .Set("id", row.Id)
            .Set("created_at", row.CreatedAt.IsoFormat())
            .Set("module", row.Module)
            .Set("event_type", row.EventType)
            .Set("trigger", row.Trigger)
            .Set("result", row.Result)
            .Set("library_id", row.LibraryId)
            .Set("relative_path", row.RelativePath)
            .Set("title", row.Title)
            .Set("detail", row.Detail);
    }

    public static string ExportJson(IReadOnlyList<ActivityEventRow> rows)
    {
        ArgumentNullException.ThrowIfNull(rows);
        return PyJsonWriter.Dumps(new PyList(rows.Select(row => (PyJson)ExportRecord(row))), ExportJsonFormat);
    }

    /// <summary><c>csv.DictWriter</c> with the <c>excel</c> dialect: a header, then one line per row, <c>\r\n</c> after each.</summary>
    public static string ExportCsv(IReadOnlyList<ActivityEventRow> rows)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var builder = new StringBuilder();
        AppendCsvLine(builder, ExportColumns);
        foreach (var row in rows)
        {
            AppendCsvLine(
                builder,
                [
                    row.Id.ToString(CultureInfo.InvariantCulture),
                    row.CreatedAt.IsoFormat(),
                    row.Module,
                    row.EventType,
                    row.Trigger ?? string.Empty,
                    row.Result ?? string.Empty,
                    row.LibraryId?.ToString(CultureInfo.InvariantCulture) ?? string.Empty,
                    row.RelativePath ?? string.Empty,
                    row.Title,
                    row.Detail ?? string.Empty,
                ]);
        }

        return builder.ToString();
    }

    /// <summary><c>weir-activity-{stamp}.{extension}</c> with the local time, as <c>datetime.now().strftime("%Y%m%d-%H%M%S")</c>.</summary>
    public static string ExportFileName(DateTimeOffset localNow, string extension) =>
        string.Create(CultureInfo.InvariantCulture, $"weir-activity-{localNow:yyyyMMdd-HHmmss}.{extension}");

    /// <summary><c>ActivityFileHistoryCountOut</c>.</summary>
    public static PyDict FileHistoryCountOut(FileHistoryCounts counts)
    {
        ArgumentNullException.ThrowIfNull(counts);
        return new PyDict()
            .Set("relative_path", counts.RelativePath)
            .Set("activity_events", counts.ActivityEvents)
            .Set("processing_records", counts.ProcessingRecords)
            .Set(
                "message",
                string.Create(
                    CultureInfo.InvariantCulture,
                    $"This removes {counts.ActivityEvents} Activity event(s) and {counts.ProcessingRecords} processing record(s) about {counts.RelativePath}. ") +
                "It does not touch the file itself, its current status on the Files screen, or anything else's history.");
    }

    /// <summary><c>ActivityFileHistoryRemoveOut</c>.</summary>
    public static PyDict FileHistoryRemoveOut(FileHistoryCounts deleted)
    {
        ArgumentNullException.ThrowIfNull(deleted);
        return new PyDict()
            .Set("relative_path", deleted.RelativePath)
            .Set("activity_events_deleted", deleted.ActivityEvents)
            .Set("processing_records_deleted", deleted.ProcessingRecords);
    }

    /// <summary>The <c>event: activity.latest</c> frame of the live stream.</summary>
    public static string LatestEventFrame(long latestEventId, long activityRevision) =>
        string.Create(
            CultureInfo.InvariantCulture,
            $"event: activity.latest\ndata: {{\"latest_event_id\":{latestEventId},\"activity_revision\":{activityRevision}}}\n\n");

    /// <summary>
    /// CPython's <c>_csv</c> writer with <c>QUOTE_MINIMAL</c>: a field is quoted when it holds the delimiter,
    /// the quote character, <c>\r</c> or <c>\n</c>; quotes inside are doubled.
    /// </summary>
    private static void AppendCsvLine(StringBuilder builder, IReadOnlyList<string> fields)
    {
        for (var index = 0; index < fields.Count; index++)
        {
            if (index > 0)
            {
                builder.Append(',');
            }

            var field = fields[index];
            if (field.AsSpan().IndexOfAny(",\"\r\n") < 0)
            {
                builder.Append(field);
                continue;
            }

            builder.Append('"').Append(field.Replace("\"", "\"\"", StringComparison.Ordinal)).Append('"');
        }

        builder.Append("\r\n");
    }
}
