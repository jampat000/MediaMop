using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>The custody-screen overview counters (<c>RefinerOverviewStatsOut</c>).</summary>
public sealed record RefinerOverviewStats(
    int WindowDays,
    long FilesProcessed,
    long FilesFailed,
    double SuccessRatePercent,
    long OutputWrittenCount,
    long AlreadyOptimizedCount,
    long NetSpaceSavedBytes,
    double NetSpaceSavedPercent);

/// <summary>Port of <c>refiner_overview_stats_service.py</c>.</summary>
public static class OverviewStatsStore
{
    private const string RemuxPassJobKind = "refiner.file.remux_pass.v1";
    private const string OutcomeLiveOutputWritten = "live_output_written";
    private const string OutcomeLiveSkippedNotRequired = "live_skipped_not_required";

    public static async Task<RefinerOverviewStats> BuildAsync(UnitOfWork uow, int windowDays, TimeProvider time)
    {
        var days = Math.Max(1, windowDays);
        var since = time.GetUtcNow().AddDays(-days);
        var sinceParam = SqliteValues.ToSqlite(PyDateTime.FromUtc(since.UtcDateTime));

        var failed = await uow.CountAsync(
            "SELECT COUNT(*) FROM refiner_jobs WHERE job_kind = @kind AND status IN ('failed', 'handler_ok_finalize_failed') AND updated_at >= @since",
            ("@kind", RemuxPassJobKind), ("@since", sinceParam)).ConfigureAwait(false);

        var detailRows = await uow.QueryAsync(
            "SELECT detail FROM activity_events WHERE event_type = @type AND created_at >= @since",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@type", ActivityEventTypes.RefinerFileRemuxPassCompleted), ("@since", sinceParam)).ConfigureAwait(false);

        long outputWrittenCount = 0;
        long alreadyOptimizedCount = 0;
        long totalSourceBytes = 0;
        long totalOutputBytes = 0;
        foreach (var raw in detailRows)
        {
            if (string.IsNullOrEmpty(raw))
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

            var outcome = payload.TryGetValue("outcome", out var outcomeValue) && outcomeValue is PyStr outcomeStr ? outcomeStr.Value.Trim() : string.Empty;
            if (outcome == OutcomeLiveOutputWritten)
            {
                outputWrittenCount++;
                var sourceBytes = JsonInt(payload.TryGetValue("source_size_bytes", out var sb) ? sb : null);
                var outputBytes = JsonInt(payload.TryGetValue("output_size_bytes", out var ob) ? ob : null);
                if (sourceBytes is not null && outputBytes is not null)
                {
                    totalSourceBytes += Math.Max(0, sourceBytes.Value);
                    totalOutputBytes += Math.Max(0, outputBytes.Value);
                }
            }
            else if (outcome == OutcomeLiveSkippedNotRequired)
            {
                if (payload.TryGetValue("output_copied_without_remux", out var copied) && copied is PyBool { Value: true })
                {
                    alreadyOptimizedCount++;
                }
            }
        }

        var completed = outputWrittenCount + alreadyOptimizedCount;
        var terminal = completed + failed;
        var rate = terminal > 0 ? Math.Round((double)completed / terminal * 100.0, 1) : 0.0;
        var netSaved = totalSourceBytes - totalOutputBytes;
        var netSavedPercent = totalSourceBytes > 0 ? Math.Round((double)netSaved / totalSourceBytes * 100.0, 1) : 0.0;

        return new RefinerOverviewStats(days, completed, failed, rate, outputWrittenCount, alreadyOptimizedCount, netSaved, netSavedPercent);
    }

    private static long? JsonInt(PyJson? value) => value switch
    {
        PyInt i => (long)i.Value,
        PyFloat f => (long)f.Value,
        PyStr s when long.TryParse(s.Value.Trim(), out var parsed) => parsed,
        PyStr s when double.TryParse(s.Value.Trim(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var parsedDouble) => (long)parsedDouble,
        _ => null,
    };
}
