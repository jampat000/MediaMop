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
    /// Refiner writes progress in short transactions; a transient writer collision should wait for
    /// that transaction rather than fail a completed media mutation.
    /// </summary>
    public const int BusyTimeoutMilliseconds = 30_000;

    public SqliteDatabase(string databasePath)
    {
        ArgumentException.ThrowIfNullOrEmpty(databasePath);
        DatabasePath = databasePath;
        ConnectionString = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Private,
            Pooling = true,
            // Seconds a command waits on a locked database (complements PRAGMA busy_timeout).
            DefaultTimeout = BusyTimeoutMilliseconds / 1000,
        }.ToString();
    }

    public string DatabasePath { get; }

    public string ConnectionString { get; }

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
