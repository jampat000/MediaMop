using Weir.Core.LibraryMode;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>Where a swap had got to when it was last recorded.</summary>
public enum SwapJournalState
{
    /// <summary>Preflight passed; the cleaned copy is being written to the temp file.</summary>
    Writing,

    /// <summary>Validated and unchanged; about to rename the original aside.</summary>
    Committing,

    /// <summary><c>swap_committed</c>: the cleaned copy has the original's name. The backup may still exist.</summary>
    Committed,

    /// <summary>Committed and the backup is gone.</summary>
    Finished,

    /// <summary>Stopped before the commit and undone.</summary>
    RolledBack,

    /// <summary>Left unfinished by a crash and put right by the startup sweep.</summary>
    Recovered,
}

/// <summary>One job's swap record.</summary>
public sealed record SwapJournalEntry(long JobId, string OriginalPath, SwapJournalState State)
{
    public bool IsUnfinished => State is SwapJournalState.Writing or SwapJournalState.Committing or SwapJournalState.Committed;
}

/// <summary>The durable record of swaps in progress, so the startup sweep can go straight to the files a crash left behind.</summary>
public interface ISwapJournal
{
    Task RecordAsync(SwapJournalEntry entry, CancellationToken cancellationToken = default);

    Task<IReadOnlyList<SwapJournalEntry>> ListUnfinishedAsync(CancellationToken cancellationToken = default);
}

/// <summary>
/// Records each swap in the <c>library_swaps</c> table, one row per job (upserted by <c>job_id</c>): #557's
/// migration (0040_library_swaps) moved this off <c>jobs.payload_json</c>'s <c>library_swap</c>
/// object and <c>swap_committed</c> flag, which <c>ProcessingJobSwapJournal</c> used to pack in there while
/// ADR-0017 froze the schema and both backends needed to open the same database.
/// </summary>
public sealed class ProcessingJobSwapJournal : ISwapJournal
{
    private readonly SqliteDatabase _database;

    public ProcessingJobSwapJournal(SqliteDatabase database)
    {
        _database = database;
    }

    public async Task RecordAsync(SwapJournalEntry entry, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(entry);
        await using var connection = await _database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using var transaction = connection.BeginTransaction();
        using (var exists = connection.CreateCommand())
        {
            exists.Transaction = transaction;
            exists.CommandText = "SELECT COUNT(*) FROM jobs WHERE id = $id";
            exists.Parameters.AddWithValue("$id", entry.JobId);
            var count = Convert.ToInt64(await exists.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false), System.Globalization.CultureInfo.InvariantCulture);
            if (count == 0)
            {
                throw new InvalidOperationException(
                    string.Create(System.Globalization.CultureInfo.InvariantCulture, $"Job {entry.JobId} does not exist, so its swap could not be recorded."));
            }
        }

        using (var upsert = connection.CreateCommand())
        {
            upsert.Transaction = transaction;
            upsert.CommandText =
                """
                INSERT INTO library_swaps (job_id, state, original_path, temp_path, backup_path, committed, updated_at)
                VALUES ($job_id, $state, $original_path, $temp_path, $backup_path, $committed, CURRENT_TIMESTAMP)
                ON CONFLICT(job_id) DO UPDATE SET state = excluded.state, original_path = excluded.original_path,
                    temp_path = excluded.temp_path, backup_path = excluded.backup_path,
                    committed = committed OR excluded.committed, updated_at = CURRENT_TIMESTAMP
                """;
            upsert.Parameters.AddWithValue("$job_id", entry.JobId);
            upsert.Parameters.AddWithValue("$state", StateName(entry.State));
            upsert.Parameters.AddWithValue("$original_path", entry.OriginalPath);
            upsert.Parameters.AddWithValue("$temp_path", SafeSwapRules.TempPath(entry.OriginalPath));
            upsert.Parameters.AddWithValue("$backup_path", SafeSwapRules.BackupPath(entry.OriginalPath));
            upsert.Parameters.AddWithValue("$committed", entry.State is SwapJournalState.Committed or SwapJournalState.Finished ? 1 : 0);
            await upsert.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<SwapJournalEntry>> ListUnfinishedAsync(CancellationToken cancellationToken = default)
    {
        var entries = new List<SwapJournalEntry>();
        await using var connection = await _database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using var command = connection.CreateCommand();
        command.CommandText = "SELECT job_id, original_path, state FROM library_swaps ORDER BY job_id";
        await using var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
        {
            if (reader.IsDBNull(1) || ParseState(reader.GetString(2)) is not { } parsed)
            {
                continue;
            }

            var entry = new SwapJournalEntry(reader.GetInt64(0), reader.GetString(1), parsed);
            if (entry.IsUnfinished)
            {
                entries.Add(entry);
            }
        }

        return entries;
    }

    public static string StateName(SwapJournalState state) => state switch
    {
        SwapJournalState.Writing => "writing",
        SwapJournalState.Committing => "committing",
        SwapJournalState.Committed => "committed",
        SwapJournalState.Finished => "finished",
        SwapJournalState.RolledBack => "rolled_back",
        SwapJournalState.Recovered => "recovered",
        _ => throw new ArgumentOutOfRangeException(nameof(state), state, null),
    };

    private static SwapJournalState? ParseState(string name) =>
        Enum.GetValues<SwapJournalState>().Where(state => StateName(state) == name).Select(state => (SwapJournalState?)state).FirstOrDefault();
}
