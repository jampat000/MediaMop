using System.Data;
using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Json;
using Weir.Core.Time;

namespace Weir.Infrastructure.Sqlite;

/// <summary>
/// One request's database work, with the transaction behaviour of the Python session
/// (<c>get_db_session</c> over pysqlite): reads run outside a transaction until the first write,
/// which begins one; the owner commits on success, and anything uncommitted is rolled back on dispose.
/// That transaction is always <c>BEGIN IMMEDIATE</c> — see <see cref="EnsureTransaction"/> for why a
/// deferred one could not survive another writer committing mid-unit (#586).
/// </summary>
public sealed class UnitOfWork : IAsyncDisposable
{
    private SqliteTransaction? _transaction;
    private List<Action>? _afterCommit;
    private Dictionary<string, object>? _items;

    private UnitOfWork(SqliteDatabase database, SqliteConnection connection)
    {
        Database = database;
        Connection = connection;
    }

    public SqliteDatabase Database { get; }

    public SqliteConnection Connection { get; }

    public bool InTransaction => _transaction is not null;

    /// <summary>Per-unit state for writers (SQLAlchemy's <c>session.info</c>); cleared when the unit commits or rolls back.</summary>
    public IDictionary<string, object> Items => _items ??= new Dictionary<string, object>(StringComparer.Ordinal);

    public static async Task<UnitOfWork> OpenAsync(SqliteDatabase database, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(database);
        var connection = await database.OpenAsync(cancellationToken).ConfigureAwait(false);
        return new UnitOfWork(database, connection);
    }

    /// <summary>
    /// Run <paramref name="callback"/> once, after the next successful commit (SQLAlchemy's <c>after_commit</c>
    /// event); a rollback discards it.
    /// </summary>
    public void OnCommitted(Action callback)
    {
        ArgumentNullException.ThrowIfNull(callback);
        (_afterCommit ??= []).Add(callback);
    }

    /// <summary>
    /// Begin the transaction now, before this unit has read or written anything (the bootstrap lock).
    /// Every transaction here is <c>BEGIN IMMEDIATE</c> (see <see cref="EnsureTransaction"/>); this is
    /// for a caller that wants the write lock held across its reads as well, and it must therefore come
    /// before them.
    /// </summary>
    public void BeginImmediate()
    {
        if (_transaction is not null)
        {
            throw new InvalidOperationException("A transaction is already open.");
        }

        EnsureTransaction();
    }

    /// <summary>
    /// The write transaction, begun now if this unit of work has not written yet: for code that issues its own
    /// commands on <see cref="Connection"/> as part of this unit of work (the job queue's enqueue). Such code
    /// may read before it writes, so this is the call that most depends on the transaction being immediate
    /// (<see cref="EnsureTransaction"/>, #586); ask for it at the point of the write, not before.
    /// </summary>
    public SqliteTransaction WriteTransaction()
    {
        EnsureTransaction();
        return _transaction!;
    }

    public async Task<int> ExecuteAsync(string sql, params (string Name, object? Value)[] parameters)
    {
        EnsureTransaction();
        var command = Create(sql, parameters);
        await using (command.ConfigureAwait(false))
        {
            return await command.ExecuteNonQueryAsync().ConfigureAwait(false);
        }
    }

    /// <summary>A write that returns a value (<c>INSERT … RETURNING</c> or <c>last_insert_rowid()</c>).</summary>
    public async Task<object?> ExecuteScalarWriteAsync(string sql, params (string Name, object? Value)[] parameters)
    {
        EnsureTransaction();
        var command = Create(sql, parameters);
        await using (command.ConfigureAwait(false))
        {
            return await command.ExecuteScalarAsync().ConfigureAwait(false);
        }
    }

    public async Task<object?> ScalarAsync(string sql, params (string Name, object? Value)[] parameters)
    {
        var command = Create(sql, parameters);
        await using (command.ConfigureAwait(false))
        {
            return await command.ExecuteScalarAsync().ConfigureAwait(false);
        }
    }

    public async Task<long> CountAsync(string sql, params (string Name, object? Value)[] parameters) =>
        Convert.ToInt64(await ScalarAsync(sql, parameters).ConfigureAwait(false) ?? 0L, CultureInfo.InvariantCulture);

    public async Task<List<T>> QueryAsync<T>(string sql, Func<SqliteDataReader, T> map, params (string Name, object? Value)[] parameters)
    {
        ArgumentNullException.ThrowIfNull(map);
        var command = Create(sql, parameters);
        await using (command.ConfigureAwait(false))
        {
            var reader = await command.ExecuteReaderAsync().ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                var rows = new List<T>();
                while (await reader.ReadAsync().ConfigureAwait(false))
                {
                    rows.Add(map(reader));
                }

                return rows;
            }
        }
    }

    public async Task<T?> QuerySingleAsync<T>(string sql, Func<SqliteDataReader, T> map, params (string Name, object? Value)[] parameters)
        where T : class
    {
        var rows = await QueryAsync(sql, map, parameters).ConfigureAwait(false);
        return rows.Count > 0 ? rows[0] : null;
    }

    public async Task CommitAsync()
    {
        if (_transaction is not null)
        {
            await _transaction.CommitAsync().ConfigureAwait(false);
            await _transaction.DisposeAsync().ConfigureAwait(false);
            _transaction = null;
        }

        var callbacks = _afterCommit;
        _afterCommit = null;
        _items = null;
        foreach (var callback in callbacks ?? [])
        {
            callback();
        }
    }

    public async Task RollbackAsync()
    {
        _afterCommit = null;
        _items = null;
        if (_transaction is null)
        {
            return;
        }

        try
        {
            await _transaction.RollbackAsync().ConfigureAwait(false);
        }
        finally
        {
            await _transaction.DisposeAsync().ConfigureAwait(false);
            _transaction = null;
        }
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            await RollbackAsync().ConfigureAwait(false);
        }
        catch (SqliteException)
        {
            // Closing the connection discards the transaction anyway.
        }

        await Connection.DisposeAsync().ConfigureAwait(false);
    }

    /// <summary>
    /// Begin this unit's transaction, once, as <c>BEGIN IMMEDIATE</c>.
    /// </summary>
    /// <remarks>
    /// It was <c>BEGIN</c> (deferred) until #586. A deferred transaction takes the write lock at its first
    /// write, so when its first statement is a read instead — which is what <see cref="WriteTransaction"/>
    /// hands out, and what the job queue's enqueue does with it: look the dedupe key up, then insert — the
    /// connection's WAL read snapshot is pinned at that read. If any other connection commits a real write
    /// before the upgrade to a writer, SQLite refuses it with <c>SQLITE_BUSY_SNAPSHOT</c>. That is not a
    /// wait-and-retry condition and <c>busy_timeout</c> cannot clear it: the snapshot is permanently stale,
    /// so waiting can never make it current. Microsoft.Data.Sqlite nonetheless retries the statement until
    /// the command timeout (<see cref="SqliteDatabase.BusyTimeoutMilliseconds"/>) expires, which is why a
    /// single intervening commit — a real one; a write that changes no rows does not invalidate a snapshot —
    /// turned a webhook POST into thirty seconds of nothing followed by <c>database is locked</c>.
    ///
    /// Taking the write lock at <c>BEGIN</c> removes the window rather than coping with it: while this unit
    /// holds the lock nobody else can commit, so its snapshot cannot go stale and that error is unreachable.
    /// It costs nothing on the common path, where the first statement of the transaction is the write that
    /// began it and the lock would have been taken on the very next statement anyway; where it does move the
    /// acquisition earlier, it is by the handful of rows a store reads before its first insert. Reads before
    /// any transaction exists are untouched — they run in autocommit and still never take the write lock.
    ///
    /// Two writers both waiting at <c>BEGIN IMMEDIATE</c> cannot deadlock: SQLite has exactly one write lock
    /// per database, it is acquired whole in one step rather than accumulated, and a waiter that does not get
    /// it within <c>busy_timeout</c> fails instead of holding anything. Every other transaction in this server
    /// is already immediate; this was the only deferred one left.
    /// </remarks>
    private void EnsureTransaction()
    {
        _transaction ??= Connection.BeginTransaction(IsolationLevel.Serializable, deferred: false);
    }

    private SqliteCommand Create(string sql, (string Name, object? Value)[] parameters)
    {
        var command = Connection.CreateCommand();
        command.CommandText = sql;
        command.Transaction = _transaction;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        return command;
    }
}

/// <summary>Reading and writing column values the way SQLAlchemy's SQLite types do.</summary>
public static class SqliteValues
{
    /// <summary>SQLite's constraint violation (SQLAlchemy's <c>IntegrityError</c>).</summary>
    public const int SqliteConstraint = 19;

    public static bool IsIntegrityError(SqliteException exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        return exception.SqliteErrorCode == SqliteConstraint;
    }

    public static object ToSqlite(PyDateTime value) => value.ToSqlite();

    public static object ToSqlite(PyDateTime? value) => value is { } v ? v.ToSqlite() : DBNull.Value;

    public static string? GetStringOrNull(SqliteDataReader reader, int ordinal)
    {
        ArgumentNullException.ThrowIfNull(reader);
        return reader.IsDBNull(ordinal) ? null : Convert.ToString(reader.GetValue(ordinal), CultureInfo.InvariantCulture);
    }

    public static string GetString(SqliteDataReader reader, int ordinal) => GetStringOrNull(reader, ordinal) ?? string.Empty;

    public static long GetInt64(SqliteDataReader reader, int ordinal)
    {
        ArgumentNullException.ThrowIfNull(reader);
        if (reader.IsDBNull(ordinal))
        {
            return 0;
        }

        return reader.GetValue(ordinal) switch
        {
            long l => l,
            double d => (long)d,
            string s when long.TryParse(s.Trim(), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var parsed) => parsed,
            _ => 0,
        };
    }

    /// <summary>SQLAlchemy <c>Boolean</c> on SQLite: <c>bool(value)</c> of what is stored.</summary>
    public static bool GetBool(SqliteDataReader reader, int ordinal) => GetBoolOrNull(reader, ordinal) ?? false;

    public static bool? GetBoolOrNull(SqliteDataReader reader, int ordinal)
    {
        ArgumentNullException.ThrowIfNull(reader);
        return reader.IsDBNull(ordinal) ? null : PyConvert.FromDatabase(reader.GetValue(ordinal)).IsTruthy;
    }

    /// <summary>SQLAlchemy <c>DateTime</c> on SQLite: <c>datetime.fromisoformat</c> of the stored text.</summary>
    public static PyDateTime? GetDateTimeOrNull(SqliteDataReader reader, int ordinal)
    {
        ArgumentNullException.ThrowIfNull(reader);
        if (reader.IsDBNull(ordinal))
        {
            return null;
        }

        var text = Convert.ToString(reader.GetValue(ordinal), CultureInfo.InvariantCulture) ?? string.Empty;
        return PyDateTime.TryFromIsoFormat(text, out var value)
            ? value
            : throw new FormatException($"Invalid isoformat string: {PyStrings.Repr(text)}");
    }

    public static PyDateTime GetDateTime(SqliteDataReader reader, int ordinal) =>
        GetDateTimeOrNull(reader, ordinal) ?? throw new FormatException("A required timestamp column is NULL.");
}
