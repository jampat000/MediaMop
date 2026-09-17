using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Activity;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Activity;

/// <summary>
/// Appends <c>activity_events</c> rows with the columns Python's <c>record_activity_event</c> writes:
/// the event, plus the <c>trigger</c>, <c>result</c>, <c>library_id</c>, <c>relative_path</c> and
/// <c>run_key</c> that <see cref="ActivityClassifier"/> lifts from the detail. <c>created_at</c> is the
/// database default. Live notification of listeners belongs to the Activity port (#519).
/// </summary>
/// <remarks>
/// The one insert for every producer: <see cref="RecordAsync(ActivityEventDraft, CancellationToken)"/>
/// in its own transaction, <see cref="Record"/> inside a caller's raw transaction (the job queue), and
/// <see cref="RecordAsync(UnitOfWork, ActivityEventDraft)"/> inside a unit of work (auth and settings).
/// </remarks>
public sealed class SqliteActivityWriter : IActivityWriter
{
    private const string InsertSql =
        "INSERT INTO activity_events (event_type, module, title, detail, \"trigger\", result, library_id, relative_path, run_key) " +
        "VALUES (@event_type, @module, @title, @detail, @trigger, @result, @library_id, @relative_path, @run_key) RETURNING id";

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
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = InsertSql;
        foreach (var (name, value) in Parameters(draft))
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        return Convert.ToInt64(command.ExecuteScalar(), CultureInfo.InvariantCulture);
    }

    /// <summary>Insert inside a unit of work (which opens its transaction on this first write if needed).</summary>
    public static async Task<long> RecordAsync(UnitOfWork uow, ActivityEventDraft draft)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(draft);
        var id = await uow.ExecuteScalarWriteAsync(InsertSql, Parameters(draft)).ConfigureAwait(false);
        return Convert.ToInt64(id, CultureInfo.InvariantCulture);
    }

    private static (string Name, object? Value)[] Parameters(ActivityEventDraft draft)
    {
        var facts = ActivityClassifier.Classify(draft.EventType, draft.Detail);
        return
        [
            ("@event_type", draft.EventType),
            ("@module", draft.Module),
            ("@title", draft.Title),
            ("@detail", draft.Detail),
            ("@trigger", facts.Trigger),
            ("@result", facts.Result),
            ("@library_id", facts.LibraryId),
            ("@relative_path", facts.RelativePath),
            ("@run_key", facts.RunKey),
        ];
    }
}
