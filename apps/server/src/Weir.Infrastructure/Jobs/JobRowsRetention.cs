using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Jobs;

namespace Weir.Infrastructure.Jobs;

/// <summary>What one retention tick removed.</summary>
public sealed record JobRowsPruneCounts(int Processing, int HandoffLedger, int Activity)
{
    public int Total => Processing + Activity;
}

/// <summary>
/// Periodic pruning of terminal job rows (port of <c>weir.platform.jobs.job_rows_retention_periodic</c>):
/// terminal <c>jobs</c> rows past <c>WEIR_JOB_ROWS_RETENTION_DAYS</c>, terminal hand-off ledger
/// rows past 90 days, and Activity past the suite's <c>activity_retention_days</c>, in one transaction.
/// </summary>
public static class JobRowsRetention
{
    /// <summary><c>LEDGER_RETENTION_DAYS</c>: hand-off answers outlive job rows on purpose (#480).</summary>
    public const int LedgerRetentionDays = 90;

    /// <summary><c>ensure_suite_settings_row</c>'s default when the row does not exist yet.</summary>
    public const int DefaultActivityRetentionDays = 90;

    /// <summary>The ledger's terminal states, sorted as Python binds them.</summary>
    public static readonly IReadOnlyList<string> LedgerTerminalStates = ["cancelled", "completed", "failed", "passed-through", "rejected"];

    /// <summary><c>prune_job_rows</c>: terminal rows whose <c>updated_at</c> is older than <paramref name="cutoff"/>.</summary>
    public static int PruneJobRows(SqliteConnection connection, SqliteTransaction transaction, DateTimeOffset cutoff)
    {
        var statuses = ProcessingJobStatus.Terminal;
        var names = statuses.Select((_, index) => $"@s{index}").ToArray();
        var parameters = statuses.Select((status, index) => ($"@s{index}", (object?)status))
            .Append(("@cutoff", PythonTimestamps.Orm(cutoff)))
            .ToArray();
        return ProcessingJobStore.Execute(
            connection,
            transaction,
            $"DELETE FROM jobs WHERE status IN ({string.Join(", ", names)}) AND updated_at < @cutoff",
            parameters);
    }

    /// <summary><c>_run_prune_tick</c>.</summary>
    public static Task<JobRowsPruneCounts> RunTickAsync(ProcessingJobStore queue, int jobRowsRetentionDays, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(queue);
        return queue.InTransactionAsync(
            (connection, transaction) =>
            {
                var processing = PruneJobRows(connection, transaction, now - TimeSpan.FromDays(jobRowsRetentionDays));
                var ledger = PruneLedger(connection, transaction, now);
                var activity = PruneActivity(connection, transaction, ActivityRetentionDays(connection, transaction), now);
                return new JobRowsPruneCounts(processing, ledger, activity);
            },
            cancellationToken);
    }

    private static int PruneLedger(SqliteConnection connection, SqliteTransaction transaction, DateTimeOffset now)
    {
        var names = LedgerTerminalStates.Select((_, index) => $"@state{index}").ToArray();
        var parameters = LedgerTerminalStates.Select((state, index) => ($"@state{index}", (object?)state))
            .Append(("@cutoff", PythonTimestamps.Orm(now - TimeSpan.FromDays(LedgerRetentionDays))))
            .ToArray();
        return ProcessingJobStore.Execute(
            connection,
            transaction,
            $"DELETE FROM media_manager_handoffs WHERE state IN ({string.Join(", ", names)}) AND last_changed_at < @cutoff",
            parameters);
    }

    /// <summary><c>prune_activity_events</c>: zero or less keeps everything.</summary>
    private static int PruneActivity(SqliteConnection connection, SqliteTransaction transaction, int retentionDays, DateTimeOffset now)
    {
        if (retentionDays <= 0)
        {
            return 0;
        }

        return ProcessingJobStore.Execute(
            connection,
            transaction,
            "DELETE FROM activity_events WHERE created_at < @cutoff",
            ("@cutoff", PythonTimestamps.Orm(now - TimeSpan.FromDays(retentionDays))));
    }

    private static int ActivityRetentionDays(SqliteConnection connection, SqliteTransaction transaction)
    {
        var value = ProcessingJobStore.Scalar(connection, transaction, "SELECT activity_retention_days FROM suite_settings WHERE id = 1");
        return value is null or DBNull ? DefaultActivityRetentionDays : (int)Convert.ToInt64(value, CultureInfo.InvariantCulture);
    }
}
