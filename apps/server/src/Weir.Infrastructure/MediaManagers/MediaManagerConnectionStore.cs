using Microsoft.Data.Sqlite;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>One <c>media_manager_search_lanes</c> row.</summary>
public sealed record MediaManagerSearchLaneRecord(
    long Id,
    long ConnectionId,
    string Lane,
    bool Enabled,
    long MaxItemsPerRun,
    long RetryDelayMinutes,
    bool ScheduleEnabled,
    string ScheduleDays,
    string ScheduleStart,
    string ScheduleEnd,
    long ScheduleIntervalSeconds)
{
    /// <summary><c>MediaManagerSearchLaneOut</c>.</summary>
    public PyDict ToOut() => new PyDict()
        .Set("lane", Lane)
        .Set("enabled", Enabled)
        .Set("max_items_per_run", MaxItemsPerRun)
        .Set("retry_delay_minutes", RetryDelayMinutes)
        .Set("schedule_enabled", ScheduleEnabled)
        .Set("schedule_days", ScheduleDays)
        .Set("schedule_start", ScheduleStart)
        .Set("schedule_end", ScheduleEnd)
        .Set("schedule_interval_seconds", ScheduleIntervalSeconds);
}

/// <summary>One <c>media_manager_connections</c> row with its lanes.</summary>
public sealed record MediaManagerConnectionRecord(
    long Id,
    string Kind,
    string Name,
    bool Enabled,
    string BaseUrl,
    string? ApiKeyCiphertext,
    string? WebhookSecretCiphertext,
    bool? LastTestOk,
    PyDateTime? LastTestAt,
    string? LastTestDetail)
{
    public IReadOnlyList<MediaManagerSearchLaneRecord> Lanes { get; init; } = [];

    /// <summary><c>_webhook_url_path</c>.</summary>
    public string WebhookUrlPath => $"/api/v1/intake/webhook/{Kind}";

    /// <summary><c>_to_out</c> (<c>MediaManagerConnectionOut</c>): secrets are reported only as saved or not.</summary>
    public PyDict ToOut() => new PyDict()
        .Set("id", Id)
        .Set("kind", Kind)
        .Set("name", Name)
        .Set("enabled", Enabled)
        .Set("base_url", BaseUrl)
        .Set("api_key_is_saved", !string.IsNullOrEmpty(ApiKeyCiphertext))
        .Set("webhook_secret_is_set", !string.IsNullOrEmpty(WebhookSecretCiphertext))
        .Set("webhook_url_path", WebhookUrlPath)
        .Set("last_test_ok", LastTestOk is { } ok ? PyJson.Of(ok) : PyJson.Null)
        .Set("last_test_at", LastTestAt is { } at ? at.PydanticJson() : null)
        .Set("last_test_detail", LastTestDetail)
        .Set("lanes", new PyList(Lanes.OrderBy(lane => lane.Lane, StringComparer.Ordinal).Select(lane => (PyJson)lane.ToOut())));
}

/// <summary>
/// The legacy singleton that migration 0009 copied out of but did not drop (port of <c>arr_operator_settings_repo</c>).
/// </summary>
public static class ArrLibraryOperatorSettingsStore
{
    /// <summary><c>ensure_arr_library_operator_settings_row</c>: row 1 with its defaults, created when missing.</summary>
    public static async Task EnsureRowAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        if (await uow.ScalarAsync("SELECT id FROM arr_library_operator_settings WHERE id = 1").ConfigureAwait(false) is null or DBNull)
        {
            await uow.ExecuteAsync("INSERT INTO arr_library_operator_settings (id) VALUES (1)").ConfigureAwait(false);
        }
    }
}

/// <summary>Explicit SQL over <c>media_manager_connections</c> and <c>media_manager_search_lanes</c>.</summary>
public static class MediaManagerConnectionStore
{
    private const string ConnectionColumns =
        "id, kind, name, enabled, base_url, api_key_ciphertext, webhook_secret_ciphertext, " +
        "last_connection_test_ok, last_connection_test_at, last_connection_test_detail";

    private const string LaneColumns =
        "id, connection_id, lane, enabled, max_items_per_run, retry_delay_minutes, schedule_enabled, schedule_days, " +
        "schedule_start, schedule_end, schedule_interval_seconds";

    /// <summary><c>list_connections</c>: by id.</summary>
    public static async Task<List<MediaManagerConnectionRecord>> ListAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync($"SELECT {ConnectionColumns} FROM media_manager_connections ORDER BY id", ReadConnection).ConfigureAwait(false);
        return await WithLanesAsync(uow, rows).ConfigureAwait(false);
    }

    /// <summary>Enabled connections by id (<c>_enabled_rows</c>).</summary>
    public static async Task<List<MediaManagerConnectionRecord>> ListEnabledAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return await uow.QueryAsync($"SELECT {ConnectionColumns} FROM media_manager_connections WHERE enabled IS 1 ORDER BY id", ReadConnection).ConfigureAwait(false);
    }

    /// <summary><c>get_connection</c>.</summary>
    public static async Task<MediaManagerConnectionRecord?> GetAsync(UnitOfWork uow, long connectionId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var row = await uow.QuerySingleAsync($"SELECT {ConnectionColumns} FROM media_manager_connections WHERE id = $id", ReadConnection, ("$id", connectionId)).ConfigureAwait(false);
        return row is null ? null : (await WithLanesAsync(uow, [row]).ConfigureAwait(false))[0];
    }

    /// <summary><c>connection_for_kind</c>: the first enabled connection of a kind.</summary>
    public static Task<MediaManagerConnectionRecord?> FirstEnabledForKindAsync(UnitOfWork uow, string kind)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QuerySingleAsync(
            $"SELECT {ConnectionColumns} FROM media_manager_connections WHERE kind = $kind AND enabled IS 1 ORDER BY id LIMIT 1",
            ReadConnection,
            ("$kind", kind));
    }

    /// <summary>Enabled connections that have a webhook secret saved, by id (as <c>_require_secret</c> reads them).</summary>
    public static Task<List<MediaManagerConnectionRecord>> ListEnabledWithWebhookSecretAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QueryAsync(
            $"SELECT {ConnectionColumns} FROM media_manager_connections WHERE enabled IS 1 AND webhook_secret_ciphertext IS NOT NULL",
            ReadConnection);
    }

    public static async Task<bool> NameExistsAsync(UnitOfWork uow, string name, long? exceptId = null)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var id = await uow.ScalarAsync("SELECT id FROM media_manager_connections WHERE name = $name LIMIT 1", ("$name", name)).ConfigureAwait(false);
        return id is not null and not DBNull && (exceptId is null || Convert.ToInt64(id, System.Globalization.CultureInfo.InvariantCulture) != exceptId);
    }

    /// <summary>Insert a connection and its two default lanes; returns the new id.</summary>
    public static async Task<long> InsertAsync(UnitOfWork uow, string kind, string name, bool enabled, string baseUrl, string? apiKeyCiphertext)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var id = Convert.ToInt64(
            await uow.ExecuteScalarWriteAsync(
                "INSERT INTO media_manager_connections (kind, name, enabled, base_url, api_key_ciphertext, webhook_secret_ciphertext, " +
                "last_connection_test_ok, last_connection_test_at, last_connection_test_detail) " +
                "VALUES ($kind, $name, $enabled, $base_url, $key, NULL, NULL, NULL, NULL) RETURNING id",
                ("$kind", kind),
                ("$name", name),
                ("$enabled", enabled ? 1 : 0),
                ("$base_url", baseUrl),
                ("$key", apiKeyCiphertext)).ConfigureAwait(false),
            System.Globalization.CultureInfo.InvariantCulture);
        foreach (var lane in MediaManagerKinds.SearchLanes)
        {
            await uow.ExecuteAsync(
                "INSERT INTO media_manager_search_lanes (connection_id, lane) VALUES ($id, $lane)",
                ("$id", id),
                ("$lane", lane)).ConfigureAwait(false);
        }

        return id;
    }

    /// <summary>Write the changed columns, stamping <c>updated_at</c> as the ORM's <c>onupdate</c> does. Nothing changed, nothing written.</summary>
    public static async Task UpdateColumnsAsync(UnitOfWork uow, long connectionId, IReadOnlyList<(string Column, object? Value)> changes)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(changes);
        if (changes.Count == 0)
        {
            return;
        }

        var sets = changes.Select((change, index) => $"{change.Column} = $v{index}");
        var parameters = changes.Select((change, index) => ($"$v{index}", change.Value)).Append(("$id", (object?)connectionId)).ToArray();
        await uow.ExecuteAsync(
            $"UPDATE media_manager_connections SET {string.Join(", ", sets)}, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
            parameters).ConfigureAwait(false);
    }

    /// <summary>The ORM delete: the lanes first (cascade "all, delete-orphan"), then the connection.</summary>
    public static async Task DeleteAsync(UnitOfWork uow, long connectionId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        await uow.ExecuteAsync("DELETE FROM media_manager_search_lanes WHERE connection_id = $id", ("$id", connectionId)).ConfigureAwait(false);
        await uow.ExecuteAsync("DELETE FROM media_manager_connections WHERE id = $id", ("$id", connectionId)).ConfigureAwait(false);
    }

    /// <summary>The conditional test-result write: 0 when the connection was removed meanwhile.</summary>
    public static Task<int> RecordTestResultAsync(UnitOfWork uow, long connectionId, bool ok, PyDateTime checkedAt, string detail)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.ExecuteAsync(
            "UPDATE media_manager_connections SET last_connection_test_ok = $ok, last_connection_test_at = $at, " +
            "last_connection_test_detail = $detail, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
            ("$ok", ok ? 1 : 0),
            ("$at", checkedAt.ToSqlite()),
            ("$detail", detail),
            ("$id", connectionId));
    }

    public static Task<MediaManagerSearchLaneRecord?> GetLaneAsync(UnitOfWork uow, long connectionId, string lane)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QuerySingleAsync(
            $"SELECT {LaneColumns} FROM media_manager_search_lanes WHERE connection_id = $id AND lane = $lane LIMIT 1",
            ReadLane,
            ("$id", connectionId),
            ("$lane", lane));
    }

    /// <summary>Save one lane whole: insert it when missing, otherwise update what changed.</summary>
    public static async Task<MediaManagerSearchLaneRecord> SaveLaneAsync(UnitOfWork uow, MediaManagerSearchLaneRecord wanted)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(wanted);
        var existing = await GetLaneAsync(uow, wanted.ConnectionId, wanted.Lane).ConfigureAwait(false);
        (string, object?)[] values =
        [
            ("$enabled", wanted.Enabled ? 1 : 0),
            ("$max", wanted.MaxItemsPerRun),
            ("$retry", wanted.RetryDelayMinutes),
            ("$sched", wanted.ScheduleEnabled ? 1 : 0),
            ("$days", wanted.ScheduleDays),
            ("$start", wanted.ScheduleStart),
            ("$end", wanted.ScheduleEnd),
            ("$interval", wanted.ScheduleIntervalSeconds),
        ];
        if (existing is null)
        {
            await uow.ExecuteAsync(
                "INSERT INTO media_manager_search_lanes (connection_id, lane, enabled, max_items_per_run, retry_delay_minutes, schedule_enabled, " +
                "schedule_days, schedule_start, schedule_end, schedule_interval_seconds) " +
                "VALUES ($id, $lane, $enabled, $max, $retry, $sched, $days, $start, $end, $interval)",
                [("$id", wanted.ConnectionId), ("$lane", wanted.Lane), .. values]).ConfigureAwait(false);
        }
        else if (existing with { Id = 0 } != wanted with { Id = 0 })
        {
            await uow.ExecuteAsync(
                "UPDATE media_manager_search_lanes SET enabled = $enabled, max_items_per_run = $max, retry_delay_minutes = $retry, " +
                "schedule_enabled = $sched, schedule_days = $days, schedule_start = $start, schedule_end = $end, " +
                "schedule_interval_seconds = $interval, updated_at = CURRENT_TIMESTAMP WHERE id = $row",
                [("$row", existing.Id), .. values]).ConfigureAwait(false);
        }

        return (await GetLaneAsync(uow, wanted.ConnectionId, wanted.Lane).ConfigureAwait(false))!;
    }

    private static async Task<List<MediaManagerConnectionRecord>> WithLanesAsync(UnitOfWork uow, List<MediaManagerConnectionRecord> rows)
    {
        if (rows.Count == 0)
        {
            return rows;
        }

        var lanes = await uow.QueryAsync($"SELECT {LaneColumns} FROM media_manager_search_lanes ORDER BY id", ReadLane).ConfigureAwait(false);
        return [.. rows.Select(row => row with { Lanes = [.. lanes.Where(lane => lane.ConnectionId == row.Id)] })];
    }

    private static MediaManagerConnectionRecord ReadConnection(SqliteDataReader reader) => new(
        SqliteValues.GetInt64(reader, 0),
        SqliteValues.GetString(reader, 1),
        SqliteValues.GetString(reader, 2),
        SqliteValues.GetBool(reader, 3),
        SqliteValues.GetString(reader, 4),
        SqliteValues.GetStringOrNull(reader, 5),
        SqliteValues.GetStringOrNull(reader, 6),
        SqliteValues.GetBoolOrNull(reader, 7),
        SqliteValues.GetDateTimeOrNull(reader, 8),
        SqliteValues.GetStringOrNull(reader, 9));

    private static MediaManagerSearchLaneRecord ReadLane(SqliteDataReader reader) => new(
        SqliteValues.GetInt64(reader, 0),
        SqliteValues.GetInt64(reader, 1),
        SqliteValues.GetString(reader, 2),
        SqliteValues.GetBool(reader, 3),
        SqliteValues.GetInt64(reader, 4),
        SqliteValues.GetInt64(reader, 5),
        SqliteValues.GetBool(reader, 6),
        SqliteValues.GetString(reader, 7),
        SqliteValues.GetString(reader, 8),
        SqliteValues.GetString(reader, 9),
        SqliteValues.GetInt64(reader, 10));
}
