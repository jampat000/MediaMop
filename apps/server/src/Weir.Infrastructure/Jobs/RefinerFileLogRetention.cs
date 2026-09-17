using System.Globalization;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Weir.Infrastructure.Scheduling;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// Pruning of the per-file processing record (port of <c>weir.refiner.refiner_file_log_retention_periodic</c>
/// and <c>prune_file_logs</c>). Separate from the suite log's retention on purpose: someone may ask about a
/// file long after the application log that mentioned it is gone.
/// </summary>
public static class RefinerFileLogRetention
{
    /// <summary><c>ensure_refiner_operator_settings_row</c>'s <c>file_log_retention_days</c> when the row does not exist yet.</summary>
    public const int DefaultRetentionDays = 90;

    /// <summary><c>prune_once</c>: records older than <c>file_log_retention_days</c>; zero or less keeps everything.</summary>
    public static Task<int> PruneOnceAsync(RefinerJobStore store, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(store);
        return store.InTransactionAsync(
            (connection, transaction) =>
            {
                var value = RefinerJobStore.Scalar(connection, transaction, "SELECT file_log_retention_days FROM refiner_operator_settings WHERE id = 1");
                var days = value is null or DBNull ? DefaultRetentionDays : Convert.ToInt64(value, CultureInfo.InvariantCulture);
                return days <= 0 ? 0 : Prune(connection, transaction, days, now);
            },
            cancellationToken);
    }

    /// <summary><c>prune_file_logs</c>: select the doomed ids, then delete exactly those.</summary>
    public static int Prune(SqliteConnection connection, SqliteTransaction transaction, long retentionDays, DateTimeOffset now)
    {
        if (retentionDays <= 0)
        {
            return 0;
        }

        var cutoff = PythonTimestamps.Orm(now - TimeSpan.FromDays(retentionDays));
        return RefinerJobStore.Execute(
            connection,
            transaction,
            "DELETE FROM refiner_file_logs WHERE refiner_file_logs.id IN " +
            "(SELECT refiner_file_logs.id FROM refiner_file_logs WHERE refiner_file_logs.recorded_at < @cutoff)",
            ("@cutoff", cutoff));
    }
}

/// <summary><c>refiner-file-log-retention</c>: prune on start, then hourly; a failure is logged and retried next hour.</summary>
public sealed class RefinerFileLogRetentionTask : IPeriodicTask
{
    /// <summary><c>PRUNE_INTERVAL_SECONDS</c>.</summary>
    public static readonly TimeSpan PruneInterval = TimeSpan.FromSeconds(3600);

    private readonly RefinerJobStore _store;
    private readonly TimeProvider _time;
    private readonly ILogger _logger;

    public RefinerFileLogRetentionTask(RefinerJobStore store, TimeProvider time, ILoggerFactory loggerFactory)
    {
        ArgumentNullException.ThrowIfNull(loggerFactory);
        _store = store;
        _time = time;
        _logger = loggerFactory.CreateLogger("weir.refiner.refiner_file_log_retention_periodic");
    }

    public string Name => "refiner-file-log-retention";

    public TimeSpan Interval => PruneInterval;

    public bool RunAtStart => true;

    public TimeSpan? FailureCooldown => null;

    public string FailureMessage => "Refiner processing-record retention failed.";

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        var removed = await RefinerFileLogRetention.PruneOnceAsync(_store, _time.GetUtcNow(), cancellationToken).ConfigureAwait(false);
        if (removed > 0)
        {
            _logger.LogInformation("Refiner removed {Removed} processing record(s) past their retention window.", removed);
        }
    }
}
