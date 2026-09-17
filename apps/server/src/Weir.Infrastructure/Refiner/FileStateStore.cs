using Microsoft.Data.Sqlite;
using Weir.Core.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>SQLite access for <c>refiner_files</c> (port of the read/list/forget parts of <c>refiner_file_state_service.py</c>).</summary>
public static class FileStateStore
{
    private const string Columns =
        "id, library_id, relative_path, status, status_reason, blocked_by_connection, size_bytes, video_width, video_height, " +
        "video_codec, audio_track_count, subtitle_track_count, duration_seconds, audio_codecs, video_bit_depth, size_changed_at, " +
        "hold_until, failure_class, failure_attempts, next_retry_at, output_collision_policy, output_collision_action, " +
        "output_collision_reason, hardware_method, hardware_fell_back_to_software, hardware_reason, last_seen_at, last_attempt_at, " +
        "created_at, updated_at";

    public static Task<RefinerFileRecord?> GetAsync(UnitOfWork uow, long id) =>
        uow.QuerySingleAsync($"SELECT {Columns} FROM refiner_files WHERE id = @id", Read, ("@id", id));

    public static Task<RefinerFileRecord?> FindAsync(UnitOfWork uow, long libraryId, string relativePath) =>
        uow.QuerySingleAsync(
            $"SELECT {Columns} FROM refiner_files WHERE library_id = @lib AND relative_path = @path",
            Read, ("@lib", libraryId), ("@path", relativePath));

    /// <summary><c>list_files</c>.</summary>
    public static Task<List<RefinerFileRecord>> ListAsync(UnitOfWork uow, RefinerFileListFilter filter)
    {
        var clauses = new List<string>();
        var parameters = new List<(string, object?)>();
        if (filter.LibraryId is { } libraryId)
        {
            clauses.Add("library_id = @library_id");
            parameters.Add(("@library_id", libraryId));
        }

        if (!string.IsNullOrEmpty(filter.Status))
        {
            clauses.Add("status = @status");
            parameters.Add(("@status", filter.Status));
        }

        if (!string.IsNullOrEmpty(filter.PathContains))
        {
            clauses.Add("relative_path LIKE @path_contains ESCAPE '\\'");
            parameters.Add(("@path_contains", "%" + EscapeLike(filter.PathContains) + "%"));
        }

        if (filter.Since is { } since)
        {
            clauses.Add("last_seen_at >= @since");
            parameters.Add(("@since", SqliteValues.ToSqlite(since)));
        }

        var where = clauses.Count > 0 ? "WHERE " + string.Join(" AND ", clauses) : string.Empty;
        var sql = $"SELECT {Columns} FROM refiner_files {where} ORDER BY last_seen_at DESC, id DESC LIMIT {filter.ClampedLimit}";
        return uow.QueryAsync(sql, Read, [.. parameters]);
    }

    private static string EscapeLike(string value) => value.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);

    /// <summary><c>status_counts</c>: a count per known status, zero-filled.</summary>
    public static async Task<Dictionary<string, long>> StatusCountsAsync(UnitOfWork uow, long? libraryId)
    {
        var counts = RefinerFileStatuses.All.ToDictionary(s => s, _ => 0L, StringComparer.Ordinal);
        var sql = "SELECT status, COUNT(*) FROM refiner_files" + (libraryId is not null ? " WHERE library_id = @lib" : string.Empty) + " GROUP BY status";
        var rows = libraryId is { } id
            ? await uow.QueryAsync(sql, reader => (Status: reader.GetString(0), Count: reader.GetInt64(1)), ("@lib", id)).ConfigureAwait(false)
            : await uow.QueryAsync(sql, reader => (Status: reader.GetString(0), Count: reader.GetInt64(1))).ConfigureAwait(false);
        foreach (var (status, count) in rows)
        {
            if (counts.ContainsKey(status))
            {
                counts[status] = count;
            }
        }

        return counts;
    }

    /// <summary><c>forget_file</c>: removes Weir's record; never touches the file on disk.</summary>
    public static Task ForgetAsync(UnitOfWork uow, long id) => uow.ExecuteAsync("DELETE FROM refiner_files WHERE id = @id", ("@id", id));

    /// <summary>Every library's name, keyed by id (for the Files list's <c>library_name</c> field).</summary>
    public static Task<Dictionary<long, string>> LibraryNamesAsync(UnitOfWork uow) =>
        uow.QueryAsync("SELECT id, name FROM refiner_libraries", reader => (Id: reader.GetInt64(0), Name: reader.GetString(1)))
           .ContinueWith(t => t.Result.ToDictionary(x => x.Id, x => x.Name), TaskScheduler.Default);

    private static RefinerFileRecord Read(SqliteDataReader reader) => new()
    {
        Id = reader.GetInt64(0),
        LibraryId = reader.GetInt64(1),
        RelativePath = SqliteValues.GetString(reader, 2),
        Status = SqliteValues.GetString(reader, 3),
        StatusReason = SqliteValues.GetString(reader, 4),
        BlockedByConnection = SqliteValues.GetStringOrNull(reader, 5),
        SizeBytes = SqliteValues.GetInt64(reader, 6),
        VideoWidth = reader.IsDBNull(7) ? null : reader.GetInt64(7),
        VideoHeight = reader.IsDBNull(8) ? null : reader.GetInt64(8),
        VideoCodec = SqliteValues.GetStringOrNull(reader, 9),
        AudioTrackCount = reader.IsDBNull(10) ? null : reader.GetInt64(10),
        SubtitleTrackCount = reader.IsDBNull(11) ? null : reader.GetInt64(11),
        DurationSeconds = reader.IsDBNull(12) ? null : reader.GetDouble(12),
        AudioCodecs = SqliteValues.GetStringOrNull(reader, 13),
        VideoBitDepth = reader.IsDBNull(14) ? null : reader.GetInt64(14),
        SizeChangedAt = SqliteValues.GetDateTimeOrNull(reader, 15),
        HoldUntil = SqliteValues.GetDateTimeOrNull(reader, 16),
        FailureClass = SqliteValues.GetStringOrNull(reader, 17),
        FailureAttempts = SqliteValues.GetInt64(reader, 18),
        NextRetryAt = SqliteValues.GetDateTimeOrNull(reader, 19),
        OutputCollisionPolicy = SqliteValues.GetStringOrNull(reader, 20),
        OutputCollisionAction = SqliteValues.GetStringOrNull(reader, 21),
        OutputCollisionReason = SqliteValues.GetStringOrNull(reader, 22),
        HardwareMethod = SqliteValues.GetStringOrNull(reader, 23),
        HardwareFellBackToSoftware = SqliteValues.GetBool(reader, 24),
        HardwareReason = SqliteValues.GetStringOrNull(reader, 25),
        LastSeenAt = SqliteValues.GetDateTimeOrNull(reader, 26),
        LastAttemptAt = SqliteValues.GetDateTimeOrNull(reader, 27),
        CreatedAt = SqliteValues.GetDateTime(reader, 28),
        UpdatedAt = SqliteValues.GetDateTime(reader, 29),
    };
}
