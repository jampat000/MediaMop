using Microsoft.Data.Sqlite;
using Weir.Core.Notifications;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Notifications;

/// <summary>The <c>notification_channels</c> table (port of <c>weir.platform.notifications.ops</c>).</summary>
public static class NotificationChannelStore
{
    private const string Columns = "id, label, provider, url, events_json, enabled, created_at, updated_at";

    public static Task<List<NotificationChannelRecord>> ListAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QueryAsync($"SELECT {Columns} FROM notification_channels ORDER BY notification_channels.id", Read);
    }

    public static Task<NotificationChannelRecord?> GetAsync(UnitOfWork uow, long id)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QuerySingleAsync($"SELECT {Columns} FROM notification_channels WHERE notification_channels.id = $id", Read, ("$id", id));
    }

    /// <summary><c>get_channels_for_event</c>.</summary>
    public static async Task<List<NotificationChannelRecord>> ForEventAsync(UnitOfWork uow, string jobEvent)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync($"SELECT {Columns} FROM notification_channels WHERE notification_channels.enabled IS 1", Read).ConfigureAwait(false);
        return [.. rows.Where(row => NotificationRules.ParseEvents(row.EventsJson).Contains(jobEvent, StringComparer.Ordinal))];
    }

    /// <summary><c>create_notification_channel</c> (validation is the caller's).</summary>
    public static async Task<NotificationChannelRecord> CreateAsync(UnitOfWork uow, string label, string provider, string url, IReadOnlyList<string> events, bool enabled)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var id = await uow.ExecuteScalarWriteAsync(
            "INSERT INTO notification_channels (label, provider, url, events_json, enabled) VALUES ($label, $provider, $url, $events, $enabled) RETURNING id",
            ("$label", label.Trim()),
            ("$provider", provider),
            ("$url", url),
            ("$events", NotificationRules.SerializeEvents(events)),
            ("$enabled", enabled ? 1 : 0)).ConfigureAwait(false);
        return await GetAsync(uow, Convert.ToInt64(id, System.Globalization.CultureInfo.InvariantCulture)).ConfigureAwait(false)
            ?? throw new InvalidOperationException("Notification channel was not created.");
    }

    /// <summary><c>update_notification_channel</c> for an existing row.</summary>
    public static async Task<NotificationChannelRecord> UpdateAsync(
        UnitOfWork uow, NotificationChannelRecord row, string label, string provider, string url, IReadOnlyList<string> events, bool enabled)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(row);
        var sets = new List<string>();
        var parameters = new List<(string, object?)> { ("$id", row.Id) };
        void Set(string column, bool changed, object value)
        {
            if (changed)
            {
                sets.Add($"{column}=${column}");
                parameters.Add(($"${column}", value));
            }
        }

        var trimmed = label.Trim();
        var eventsJson = NotificationRules.SerializeEvents(events);
        Set("label", row.Label != trimmed, trimmed);
        Set("provider", row.Provider != provider, provider);
        Set("url", row.Url != url, url);
        Set("events_json", row.EventsJson != eventsJson, eventsJson);
        Set("enabled", row.Enabled != enabled, enabled ? 1 : 0);
        if (sets.Count > 0)
        {
            sets.Add("updated_at=CURRENT_TIMESTAMP");
            await uow.ExecuteAsync(
                $"UPDATE notification_channels SET {string.Join(", ", sets)} WHERE notification_channels.id = $id",
                [.. parameters]).ConfigureAwait(false);
        }

        return await GetAsync(uow, row.Id).ConfigureAwait(false) ?? row;
    }

    public static Task<int> DeleteAsync(UnitOfWork uow, long id)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.ExecuteAsync("DELETE FROM notification_channels WHERE notification_channels.id = $id", ("$id", id));
    }

    private static NotificationChannelRecord Read(SqliteDataReader reader) => new(
        SqliteValues.GetInt64(reader, 0),
        SqliteValues.GetString(reader, 1),
        SqliteValues.GetString(reader, 2),
        SqliteValues.GetString(reader, 3),
        SqliteValues.GetString(reader, 4),
        SqliteValues.GetBool(reader, 5),
        SqliteValues.GetDateTime(reader, 6),
        SqliteValues.GetDateTime(reader, 7));
}
