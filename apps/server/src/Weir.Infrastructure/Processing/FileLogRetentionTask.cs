using Microsoft.Extensions.Logging;
using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing;

/// <summary>
/// Periodic pruning of the per-file processing record (port of <c>processing_file_log_retention_periodic.py</c>).
/// Separate from the suite log's own retention: a suite log diagnoses the application, a per-file record
/// diagnoses a file, and the two need different lifetimes.
/// </summary>
public sealed class FileLogRetentionTask(SqliteDatabase database, TimeProvider time, ILogger<FileLogRetentionTask> logger) : IPeriodicTask
{
    public string Name => "processing-file-log-retention";

    public TimeSpan Interval => TimeSpan.FromSeconds(3600);

    /// <summary>Python's <c>_run_forever</c> prunes once before its first wait, so the .NET host does too.</summary>
    public bool RunAtStart => true;

    public TimeSpan? FailureCooldown => null;

    public string FailureMessage => "Processing-record retention failed.";

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        var uow = await UnitOfWork.OpenAsync(database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            var operatorRow = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
            if (operatorRow.FileLogRetentionDays <= 0)
            {
                return;
            }

            var removed = await FileLogStore.PruneAsync(uow, operatorRow.FileLogRetentionDays, time.GetUtcNow()).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
            if (removed > 0)
            {
                logger.LogInformation("Removed {Removed} processing record(s) past their retention window.", removed);
            }
        }
    }
}
