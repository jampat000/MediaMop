using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>
/// Periodic pruning of the per-file processing record (port of <c>refiner_file_log_retention_periodic.py</c>).
/// Separate from the suite log's own retention: a suite log diagnoses the application, a per-file record
/// diagnoses a file, and the two need different lifetimes.
/// </summary>
public sealed class FileLogRetentionTask(SqliteDatabase database, TimeProvider time) : IPeriodicTask
{
    public string Name => "refiner-file-log-retention";

    public TimeSpan Interval => TimeSpan.FromSeconds(3600);

    public bool RunAtStart => false;

    public TimeSpan? FailureCooldown => null;

    public string FailureMessage => "Refiner processing-record retention failed.";

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

            await FileLogStore.PruneAsync(uow, operatorRow.FileLogRetentionDays, time.GetUtcNow()).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
        }
    }
}
