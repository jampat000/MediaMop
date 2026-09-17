using System.Globalization;
using Weir.Core.Json;
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
/// Records each swap on its job row: <c>refiner_jobs.payload_json</c> gains a <c>library_swap</c> object
/// (<c>state</c>, <c>original_path</c>, <c>temp_path</c>, <c>backup_path</c>) and, once committed, <c>swap_committed: true</c>.
/// </summary>
/// <remarks>
/// A job row rather than a new table: ADR-0017 keeps the SQLite schema fixed until the switch (#523), so both backends keep
/// opening the same database, and the issue asks for <c>swap_committed</c> on the job row. The payload is read, changed and
/// written back in one <c>BEGIN IMMEDIATE</c> transaction, keeping every other key and its order; the Python backend ignores
/// keys it does not know.
/// </remarks>
public sealed class RefinerJobSwapJournal : ISwapJournal
{
    public const string PayloadKey = "library_swap";
    public const string CommittedKey = "swap_committed";

    private readonly SqliteDatabase _database;

    public RefinerJobSwapJournal(SqliteDatabase database)
    {
        _database = database;
    }

    public async Task RecordAsync(SwapJournalEntry entry, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(entry);
        await using var connection = await _database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using var transaction = connection.BeginTransaction();
        string? payloadJson;
        await using (var select = connection.CreateCommand())
        {
            select.Transaction = transaction;
            select.CommandText = "SELECT payload_json FROM refiner_jobs WHERE id = $id";
            select.Parameters.AddWithValue("$id", entry.JobId);
            await using var reader = await select.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
            {
                throw new InvalidOperationException(
                    string.Create(CultureInfo.InvariantCulture, $"Job {entry.JobId} does not exist, so its swap could not be recorded."));
            }

            payloadJson = reader.IsDBNull(0) ? null : reader.GetString(0);
        }

        var payload = ParsePayload(payloadJson)
            ?? throw new InvalidOperationException(
                string.Create(CultureInfo.InvariantCulture, $"Job {entry.JobId}'s payload is not a JSON object, so its swap was not recorded over it."));
        payload.Set(
            PayloadKey,
            new PyDict()
                .Set("state", StateName(entry.State))
                .Set("original_path", entry.OriginalPath)
                .Set("temp_path", SafeSwapRules.TempPath(entry.OriginalPath))
                .Set("backup_path", SafeSwapRules.BackupPath(entry.OriginalPath)));
        if (entry.State is SwapJournalState.Committed or SwapJournalState.Finished)
        {
            payload.Set(CommittedKey, true);
        }

        await using (var update = connection.CreateCommand())
        {
            update.Transaction = transaction;
            update.CommandText = "UPDATE refiner_jobs SET payload_json = $payload WHERE id = $id";
            update.Parameters.AddWithValue("$payload", PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));
            update.Parameters.AddWithValue("$id", entry.JobId);
            await update.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<SwapJournalEntry>> ListUnfinishedAsync(CancellationToken cancellationToken = default)
    {
        var entries = new List<SwapJournalEntry>();
        await using var connection = await _database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using var command = connection.CreateCommand();
        command.CommandText = "SELECT id, payload_json FROM refiner_jobs WHERE payload_json LIKE $marker ORDER BY id";
        command.Parameters.AddWithValue("$marker", $"%\"{PayloadKey}\"%");
        await using var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
        {
            if (reader.IsDBNull(1)
                || ParsePayload(reader.GetString(1))?.Get(PayloadKey) is not PyDict swap
                || swap.Get("original_path") is not PyStr { Value.Length: > 0 } original
                || swap.Get("state") is not PyStr state
                || ParseState(state.Value) is not { } parsed)
            {
                continue;
            }

            var entry = new SwapJournalEntry(reader.GetInt64(0), original.Value, parsed);
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

    private static PyDict? ParsePayload(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return new PyDict();
        }

        try
        {
            return PyJsonParser.Parse(json) as PyDict;
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }
    }
}
