using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Activity;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// Appends <c>activity_events</c> rows with the same columns Python's <c>record_activity_event</c>
/// writes, including the classified <c>trigger</c>, <c>result</c>, <c>library_id</c>,
/// <c>relative_path</c> and <c>run_key</c>. Live notification of listeners belongs to the Activity
/// port (#519).
/// </summary>
public sealed class SqliteActivityWriter : IActivityWriter
{
    private readonly SqliteDatabase _database;

    public SqliteActivityWriter(SqliteDatabase database)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
    }

    public async Task<long> RecordAsync(ActivityEventDraft draft, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(draft);
        var connection = await _database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            var transaction = connection.BeginTransaction(deferred: false);
            await using (transaction.ConfigureAwait(false))
            {
                var id = Record(connection, transaction, draft);
                await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
                return id;
            }
        }
    }

    /// <summary>Insert inside a caller's transaction.</summary>
    public static long Record(SqliteConnection connection, SqliteTransaction transaction, ActivityEventDraft draft)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(draft);
        var facts = ActivityFacts.Classify(draft.EventType, draft.Detail);
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText =
            "INSERT INTO activity_events (event_type, module, title, detail, \"trigger\", result, library_id, relative_path, run_key) " +
            "VALUES (@event_type, @module, @title, @detail, @trigger, @result, @library_id, @relative_path, @run_key) RETURNING id";
        command.Parameters.AddWithValue("@event_type", draft.EventType);
        command.Parameters.AddWithValue("@module", draft.Module);
        command.Parameters.AddWithValue("@title", draft.Title);
        command.Parameters.AddWithValue("@detail", (object?)draft.Detail ?? DBNull.Value);
        command.Parameters.AddWithValue("@trigger", (object?)facts.Trigger ?? DBNull.Value);
        command.Parameters.AddWithValue("@result", (object?)facts.Result ?? DBNull.Value);
        command.Parameters.AddWithValue("@library_id", (object?)facts.LibraryId ?? DBNull.Value);
        command.Parameters.AddWithValue("@relative_path", (object?)facts.RelativePath ?? DBNull.Value);
        command.Parameters.AddWithValue("@run_key", (object?)facts.RunKey ?? DBNull.Value);
        return Convert.ToInt64(command.ExecuteScalar(), CultureInfo.InvariantCulture);
    }
}
