using Microsoft.Data.Sqlite;
using Weir.Core.Processing;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing;

/// <summary>SQLite access for <c>files</c> (port of <c>processing_file_state_service.py</c>: the
/// read/list/forget parts, plus the upsert/mark-status writes the watched-folder scan performs).</summary>
public static class FileStateStore
{
    private const string Columns =
        "id, library_id, relative_path, status, status_reason, blocked_by_connection, size_bytes, video_width, video_height, " +
        "video_codec, audio_track_count, subtitle_track_count, duration_seconds, audio_codecs, video_bit_depth, size_changed_at, " +
        "hold_until, failure_class, failure_attempts, next_retry_at, output_collision_policy, output_collision_action, " +
        "output_collision_reason, hardware_method, hardware_fell_back_to_software, hardware_reason, last_seen_at, last_attempt_at, " +
        "created_at, updated_at";

    public static Task<ProcessingFileRecord?> GetAsync(UnitOfWork uow, long id) =>
        uow.QuerySingleAsync($"SELECT {Columns} FROM files WHERE id = @id", Read, ("@id", id));

    public static Task<ProcessingFileRecord?> FindAsync(UnitOfWork uow, long libraryId, string relativePath) =>
        uow.QuerySingleAsync(
            $"SELECT {Columns} FROM files WHERE library_id = @lib AND relative_path = @path",
            Read, ("@lib", libraryId), ("@path", relativePath));

    /// <summary><c>list_files</c>.</summary>
    public static Task<List<ProcessingFileRecord>> ListAsync(UnitOfWork uow, ProcessingFileListFilter filter)
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
        var sql = $"SELECT {Columns} FROM files {where} ORDER BY last_seen_at DESC, id DESC LIMIT {filter.ClampedLimit}";
        return uow.QueryAsync(sql, Read, [.. parameters]);
    }

    private static string EscapeLike(string value) => value.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);

    /// <summary><c>status_counts</c>: a count per known status, zero-filled.</summary>
    public static async Task<Dictionary<string, long>> StatusCountsAsync(UnitOfWork uow, long? libraryId)
    {
        var counts = ProcessingFileStatuses.All.ToDictionary(s => s, _ => 0L, StringComparer.Ordinal);
        var sql = "SELECT status, COUNT(*) FROM files" + (libraryId is not null ? " WHERE library_id = @lib" : string.Empty) + " GROUP BY status";
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
    public static Task ForgetAsync(UnitOfWork uow, long id) => uow.ExecuteAsync("DELETE FROM files WHERE id = @id", ("@id", id));

    /// <summary><c>existing_file_row</c>: the row a previous scan left, or <see langword="null"/>. Settling
    /// compares against this. An alias for <see cref="FindAsync"/> under the Python name callers expect.</summary>
    public static Task<ProcessingFileRecord?> ExistingFileRowAsync(UnitOfWork uow, long libraryId, string relativePath) =>
        FindAsync(uow, libraryId, relativePath);

    /// <summary>
    /// <c>record_file_state</c>: upsert one file's state. Safe to call on every scan. <paramref name="sizeBytes"/>
    /// and <paramref name="sizeChangedAt"/> of <see langword="null"/> mean "not supplied" (leave the
    /// stored value alone), distinct from a genuine zero.
    /// </summary>
    public static async Task<long> RecordFileStateAsync(
        UnitOfWork uow,
        long libraryId,
        string relativePath,
        FileStateVerdict verdict,
        long? sizeBytes,
        DateTimeOffset? sizeChangedAt,
        DateTimeOffset seenAt,
        bool isAttempt = false)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(verdict);
        var existingId = await uow.ScalarAsync(
            "SELECT id FROM files WHERE library_id = @lib AND relative_path = @path",
            ("@lib", libraryId), ("@path", relativePath)).ConfigureAwait(false);

        var seen = PyDateTime.FromDateTimeOffset(seenAt);
        var holdUntil = verdict.HoldUntil is { } hold ? PyDateTime.FromDateTimeOffset(hold) : (PyDateTime?)null;
        var changedAt = sizeChangedAt is { } changed ? PyDateTime.FromDateTimeOffset(changed) : (PyDateTime?)null;

        if (existingId is null or DBNull)
        {
            await uow.ExecuteAsync(
                "INSERT INTO files (library_id, relative_path, status, status_reason, blocked_by_connection, hold_until, " +
                "size_bytes, size_changed_at, last_seen_at, last_attempt_at) VALUES (@lib, @path, @status, @reason, @blocked, @hold, " +
                "@size, @size_changed, @seen, @attempt)",
                ("@lib", libraryId),
                ("@path", relativePath),
                ("@status", verdict.Status),
                ("@reason", verdict.Reason),
                ("@blocked", verdict.BlockedByConnection),
                ("@hold", SqliteValues.ToSqlite(holdUntil)),
                ("@size", sizeBytes ?? 0),
                ("@size_changed", SqliteValues.ToSqlite(changedAt)),
                ("@seen", SqliteValues.ToSqlite(seen)),
                ("@attempt", isAttempt ? SqliteValues.ToSqlite(seen) : null)).ConfigureAwait(false);
            return Convert.ToInt64(await uow.ScalarAsync(
                "SELECT id FROM files WHERE library_id = @lib AND relative_path = @path",
                ("@lib", libraryId), ("@path", relativePath)).ConfigureAwait(false), System.Globalization.CultureInfo.InvariantCulture);
        }

        var id = Convert.ToInt64(existingId, System.Globalization.CultureInfo.InvariantCulture);
        var sets = new List<string>
        {
            "status = @status", "status_reason = @reason", "blocked_by_connection = @blocked", "hold_until = @hold",
            "last_seen_at = @seen", "updated_at = CURRENT_TIMESTAMP",
        };
        var parameters = new List<(string, object?)>
        {
            ("@status", verdict.Status),
            ("@reason", verdict.Reason),
            ("@blocked", verdict.BlockedByConnection),
            ("@hold", SqliteValues.ToSqlite(holdUntil)),
            ("@seen", SqliteValues.ToSqlite(seen)),
            ("@id", id),
        };
        if (sizeBytes is { } size)
        {
            sets.Add("size_bytes = @size");
            parameters.Add(("@size", size));
        }

        if (changedAt is { } changed2)
        {
            sets.Add("size_changed_at = @size_changed");
            parameters.Add(("@size_changed", SqliteValues.ToSqlite(changed2)));
        }

        if (isAttempt)
        {
            sets.Add("last_attempt_at = @attempt");
            parameters.Add(("@attempt", SqliteValues.ToSqlite(seen)));
        }

        await uow.ExecuteAsync($"UPDATE files SET {string.Join(", ", sets)} WHERE id = @id", [.. parameters]).ConfigureAwait(false);
        return id;
    }

    /// <summary><c>mark_file_status</c>: move a file Weir has already seen into a new state. No-op when the
    /// row does not exist (matches Python returning <see langword="null"/> silently).</summary>
    public static async Task MarkFileStatusAsync(UnitOfWork uow, long libraryId, string relativePath, string status, string reason)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var sets = new List<string> { "status = @status", "status_reason = @reason", "updated_at = CURRENT_TIMESTAMP" };
        var parameters = new List<(string, object?)> { ("@status", status), ("@reason", reason), ("@lib", libraryId), ("@path", relativePath) };
        if (status is ProcessingFileStatuses.Processing or ProcessingFileStatuses.Processed or ProcessingFileStatuses.ProcessingFailed)
        {
            sets.Add("last_attempt_at = CURRENT_TIMESTAMP");
        }

        if (status != ProcessingFileStatuses.BlockedUpstream)
        {
            sets.Add("blocked_by_connection = NULL");
        }

        if (status != ProcessingFileStatuses.OnHold)
        {
            sets.Add("hold_until = NULL");
        }

        await uow.ExecuteAsync(
            $"UPDATE files SET {string.Join(", ", sets)} WHERE library_id = @lib AND relative_path = @path",
            [.. parameters]).ConfigureAwait(false);
    }

    /// <summary>Every library's name, keyed by id (for the Files list's <c>library_name</c> field).</summary>
    public static Task<Dictionary<long, string>> LibraryNamesAsync(UnitOfWork uow) =>
        uow.QueryAsync("SELECT id, name FROM libraries", reader => (Id: reader.GetInt64(0), Name: reader.GetString(1)))
           .ContinueWith(t => t.Result.ToDictionary(x => x.Id, x => x.Name), TaskScheduler.Default);

    private static ProcessingFileRecord Read(SqliteDataReader reader) => new()
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
