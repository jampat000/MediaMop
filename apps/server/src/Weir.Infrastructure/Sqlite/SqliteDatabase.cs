using Microsoft.Data.Sqlite;

namespace Weir.Infrastructure.Sqlite;

/// <summary>
/// Opens connections to Weir's SQLite file with the same per-connection PRAGMAs the Python
/// engine applies on every new DB-API connection (<c>weir.core.db._register_sqlite_pragmas</c>):
/// WAL journal, foreign keys on, a 30 second busy timeout and <c>synchronous=NORMAL</c>.
/// </summary>
public sealed class SqliteDatabase
{
    /// <summary>
    /// Processing writes progress in short transactions; a transient writer collision should wait for
    /// that transaction rather than fail a completed media mutation.
    /// </summary>
    /// <remarks>
    /// The contract suite's HTTP client timeout (<c>REQUEST_TIMEOUT_S</c>, tests/contract/support/client.py)
    /// is deliberately held above this value — 45s against this 30s — and the two must not be made equal
    /// again. When they match, a request blocked on the write lock has the client give up at the same
    /// instant this ceiling expires, so the failure shows up as a bare <c>httpx.ReadTimeout</c> with no
    /// server-side error to go with it. That ambiguity is what made #586 take two investigations to pin
    /// down. If this value changes, move that one too, and keep it the larger of the pair.
    /// </remarks>
    public const int BusyTimeoutMilliseconds = 30_000;

    /// <param name="databasePath">The SQLite file.</param>
    /// <param name="pooling">
    /// Off only for a caller deliberately simulating several independent processes sharing one file in a
    /// single test process (e.g. a claim-concurrency stress test): every <see cref="SqliteDatabase"/>
    /// instance made from the same path otherwise shares one process-wide pool keyed by connection
    /// string, which is exactly right for production (repeated opens reuse a warm native handle) but
    /// means "separate workers" in such a test are not actually isolated the way separate real processes
    /// would be — each gets a genuinely fresh, unshared connection instead.
    /// </param>
    public SqliteDatabase(string databasePath, bool pooling = true)
    {
        ArgumentException.ThrowIfNullOrEmpty(databasePath);
        DatabasePath = databasePath;
        ConnectionString = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Private,
            Pooling = pooling,
            // Seconds a command waits on a locked database (complements PRAGMA busy_timeout).
            // Since #586 this only ever times a genuine wait for another writer's lock, which is what it
            // is for. It used to be reachable a second way: Microsoft.Data.Sqlite re-runs a statement that
            // answers SQLITE_BUSY until this expires, and SQLITE_BUSY_SNAPSHOT — a read-then-write upgrade
            // on a snapshot another connection has already overtaken — answers exactly that while never
            // being able to succeed, so the whole thirty seconds went by before the request failed. Units
            // of work now take the write lock at BEGIN (UnitOfWork.EnsureTransaction), so no transaction
            // here can hold a stale snapshot and that second path is gone.
            DefaultTimeout = BusyTimeoutMilliseconds / 1000,
        }.ToString();
    }

    public string DatabasePath { get; }

    public string ConnectionString { get; }

    /// <summary>
    /// Releases this database's own pooled connections, e.g. so its file can be deleted once every
    /// caller is done with it. Scoped to <see cref="ConnectionString"/> alone: unlike
    /// <see cref="SqliteConnection.ClearAllPools"/>, it never touches another database's pool, so it is
    /// safe to call while other connections (elsewhere in the process, such as a concurrently running
    /// test) are still open.
    /// </summary>
    public void ClearPool()
    {
        using var connection = new SqliteConnection(ConnectionString);
        SqliteConnection.ClearPool(connection);
    }

    public async Task<SqliteConnection> OpenAsync(CancellationToken cancellationToken = default)
    {
        var connection = new SqliteConnection(ConnectionString);
        try
        {
            await connection.OpenAsync(cancellationToken).ConfigureAwait(false);
            await ApplyPragmasAsync(connection, cancellationToken).ConfigureAwait(false);
            return connection;
        }
        catch
        {
            await connection.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    public SqliteConnection Open()
    {
        var connection = new SqliteConnection(ConnectionString);
        try
        {
            connection.Open();
            ApplyPragmasAsync(connection, CancellationToken.None).GetAwaiter().GetResult();
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    /// <summary>
    /// The health probe: <c>SELECT 1</c> with a one second busy timeout, so a long writer makes
    /// health slow for at most a second instead of thirty. Never throws.
    /// </summary>
    public async Task<bool> IsConnectedAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var connection = await OpenAsync(cancellationToken).ConfigureAwait(false);
            await using (connection.ConfigureAwait(false))
            {
                await ExecuteAsync(connection, "PRAGMA busy_timeout=1000", cancellationToken).ConfigureAwait(false);
                try
                {
                    await ExecuteAsync(connection, "SELECT 1", cancellationToken).ConfigureAwait(false);
                }
                finally
                {
                    await ExecuteAsync(connection, $"PRAGMA busy_timeout={BusyTimeoutMilliseconds}", CancellationToken.None)
                        .ConfigureAwait(false);
                }
            }

            return true;
        }
        catch (Exception exception) when (exception is SqliteException or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static async Task ApplyPragmasAsync(SqliteConnection connection, CancellationToken cancellationToken)
    {
        await ExecuteAsync(connection, "PRAGMA journal_mode=WAL", cancellationToken).ConfigureAwait(false);
        await ExecuteAsync(connection, "PRAGMA foreign_keys=ON", cancellationToken).ConfigureAwait(false);
        await ExecuteAsync(connection, $"PRAGMA busy_timeout={BusyTimeoutMilliseconds}", cancellationToken).ConfigureAwait(false);
        await ExecuteAsync(connection, "PRAGMA synchronous=NORMAL", cancellationToken).ConfigureAwait(false);
    }

    private static async Task ExecuteAsync(SqliteConnection connection, string sql, CancellationToken cancellationToken)
    {
        var command = connection.CreateCommand();
        await using (command.ConfigureAwait(false))
        {
            command.CommandText = sql;
            await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }
    }
}
