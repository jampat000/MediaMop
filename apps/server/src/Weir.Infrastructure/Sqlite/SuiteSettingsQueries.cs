using System.Globalization;

namespace Weir.Infrastructure.Sqlite;

/// <summary>Reads from the <c>suite_settings</c> singleton row.</summary>
public static class SuiteSettingsQueries
{
    /// <summary>The schema default for <c>suite_settings.log_retention_days</c>.</summary>
    public const int DefaultLogRetentionDays = 30;

    /// <summary>
    /// Days of <c>weir.log</c> to keep. Python creates the singleton row when it is missing; this
    /// read-only port uses the column default instead (the settings port, #518, owns writes).
    /// </summary>
    public static async Task<int> ReadLogRetentionDaysAsync(SqliteDatabase database, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(database);
        var connection = await database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            var command = connection.CreateCommand();
            await using (command.ConfigureAwait(false))
            {
                command.CommandText = "SELECT log_retention_days FROM suite_settings WHERE id = 1";
                var value = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
                return value is null or DBNull
                    ? DefaultLogRetentionDays
                    : Math.Max(1, Convert.ToInt32(value, CultureInfo.InvariantCulture));
            }
        }
    }
}
