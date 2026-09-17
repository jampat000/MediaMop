using Weir.Core.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>Read-only <c>refiner_jobs</c> listing for operators (port of <c>refiner_jobs_inspection_service.py</c>).</summary>
public static class JobsInspectionStore
{
    private static readonly HashSet<string> AllowedStatuses = new(StringComparer.Ordinal)
    {
        RefinerJobStatus.Pending, RefinerJobStatus.Leased, RefinerJobStatus.Completed,
        RefinerJobStatus.Failed, RefinerJobStatus.HandlerOkFinalizeFailed, RefinerJobStatus.Cancelled,
    };

    /// <summary><c>validate_refiner_inspection_statuses</c>.</summary>
    public static void ValidateStatuses(IReadOnlyList<string> statuses)
    {
        var unknown = statuses.Where(s => !AllowedStatuses.Contains(s)).ToList();
        if (unknown.Count > 0)
        {
            throw new ArgumentException(
                $"Invalid status filter values: {string.Join(", ", unknown)}; allowed={string.Join(", ", AllowedStatuses.Order(StringComparer.Ordinal))}");
        }
    }

    /// <summary>
    /// <c>list_refiner_jobs_for_inspection</c>: up to <paramref name="limit"/> rows, newest <c>updated_at</c>
    /// first. With no status filter, excludes completed watched-folder scan-dispatch rows so frequent,
    /// successful periodic checks do not crowd out real work.
    /// </summary>
    public static async Task<(List<RefinerJob> Rows, bool DefaultRecentSlice)> ListAsync(UnitOfWork uow, int limit, IReadOnlyList<string>? statuses)
    {
        const string columns = "id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count, " +
                                "max_attempts, last_error, not_before, runner_cost, priority, created_at, updated_at";
        if (statuses is { Count: > 0 })
        {
            var placeholders = string.Join(",", statuses.Select((_, i) => $"@status{i}"));
            var parameters = statuses.Select((s, i) => ($"@status{i}", (object?)s)).ToArray();
            var rows = await uow.QueryAsync(
                $"SELECT {columns} FROM refiner_jobs WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT {limit}",
                Read, parameters).ConfigureAwait(false);
            return (rows, false);
        }

        var recent = await uow.QueryAsync(
            $"SELECT {columns} FROM refiner_jobs WHERE NOT (status = @completed AND job_kind = @scan_kind) ORDER BY updated_at DESC LIMIT {limit}",
            Read,
            ("@completed", RefinerJobStatus.Completed),
            ("@scan_kind", "refiner.watched_folder.remux_scan_dispatch.v1")).ConfigureAwait(false);
        return (recent, true);
    }

    private static DateTimeOffset? ToOffset(Weir.Core.Time.PyDateTime? value) => value is { } v ? new DateTimeOffset(v.AsUtc, TimeSpan.Zero) : null;

    private static RefinerJob Read(Microsoft.Data.Sqlite.SqliteDataReader reader) => new(
        reader.GetInt64(0),
        reader.GetString(1),
        reader.GetString(2),
        reader.IsDBNull(3) ? null : reader.GetString(3),
        reader.GetString(4),
        reader.IsDBNull(5) ? null : reader.GetString(5),
        ToOffset(SqliteValues.GetDateTimeOrNull(reader, 6)),
        (int)SqliteValues.GetInt64(reader, 7),
        (int)SqliteValues.GetInt64(reader, 8),
        reader.IsDBNull(9) ? null : reader.GetString(9),
        ToOffset(SqliteValues.GetDateTimeOrNull(reader, 10)),
        (int)SqliteValues.GetInt64(reader, 11),
        (int)SqliteValues.GetInt64(reader, 12),
        ToOffset(SqliteValues.GetDateTime(reader, 13)) ?? DateTimeOffset.MinValue,
        ToOffset(SqliteValues.GetDateTime(reader, 14)) ?? DateTimeOffset.MinValue);
}
