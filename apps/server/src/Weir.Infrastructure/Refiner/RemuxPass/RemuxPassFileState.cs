using System.Globalization;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// The Files-row and processing-record writes a pass makes (ports of <c>mark_file_status</c>, <c>record_failure</c>,
/// <c>record_measured_media_facts</c>, <c>record_output_collision</c> and <c>record_file_log</c>), each inside the caller's
/// unit of work.
/// </summary>
public static class RemuxPassFileState
{
    private sealed record FileRow(long Id, string StatusReason, string? FailureClass, long FailureAttempts);

    private static Task<FileRow?> FindAsync(UnitOfWork uow, long libraryId, string relativePath) =>
        uow.QuerySingleAsync(
            "SELECT id, status_reason, failure_class, failure_attempts FROM refiner_files WHERE library_id = $library AND relative_path = $path LIMIT 1",
            reader => new FileRow(reader.GetInt64(0), SqliteValues.GetString(reader, 1), SqliteValues.GetStringOrNull(reader, 2), SqliteValues.GetInt64(reader, 3)),
            ("$library", libraryId),
            ("$path", relativePath));

    /// <summary><c>mark_file_status</c>: move a file Weir has already seen into a new state. False when there is no row.</summary>
    public static async Task<bool> MarkFileStatusAsync(UnitOfWork uow, long libraryId, string relativePath, string status, string reason, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var row = await FindAsync(uow, libraryId, relativePath).ConfigureAwait(false);
        if (row is null)
        {
            return false;
        }

        var sets = new List<string> { "status = $status", "status_reason = $reason", "updated_at = CURRENT_TIMESTAMP" };
        if (status is RefinerFileStatuses.Processing or RefinerFileStatuses.Processed or RefinerFileStatuses.ProcessingFailed)
        {
            sets.Add("last_attempt_at = $now");
        }

        if (status != RefinerFileStatuses.BlockedUpstream)
        {
            sets.Add("blocked_by_connection = NULL");
        }

        if (status != RefinerFileStatuses.OnHold)
        {
            sets.Add("hold_until = NULL");
        }

        await uow.ExecuteAsync(
            $"UPDATE refiner_files SET {string.Join(", ", sets)} WHERE id = $id",
            ("$status", status),
            ("$reason", reason),
            ("$now", PythonTimestamps.Orm(now)),
            ("$id", row.Id)).ConfigureAwait(false);
        return true;
    }

    /// <summary>The four failure fields cleared, after a success, a wait or a content rejection.</summary>
    public static Task ClearFailureFieldsAsync(UnitOfWork uow, long libraryId, string relativePath)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.ExecuteAsync(
            "UPDATE refiner_files SET failure_class = NULL, failure_attempts = 0, next_retry_at = NULL, hold_until = NULL, updated_at = CURRENT_TIMESTAMP " +
            "WHERE library_id = $library AND relative_path = $path",
            ("$library", libraryId),
            ("$path", relativePath));
    }

    /// <summary>
    /// <c>record_failure</c>: mark a file failed, classify it and apply the retry policy. The decision's sentence becomes the
    /// reason on the record, so the screen says whether a retry is coming.
    /// </summary>
    public static async Task<RetryDecision> RecordFailureAsync(UnitOfWork uow, RefinerLibraryRecord library, string relativePath, string failureClass, string reason, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(library);
        var row = await FindAsync(uow, library.Id, relativePath).ConfigureAwait(false);
        if (row is null)
        {
            await uow.ExecuteAsync(
                "INSERT INTO refiner_files (library_id, relative_path) VALUES ($library, $path)",
                ("$library", library.Id),
                ("$path", relativePath)).ConfigureAwait(false);
            row = (await FindAsync(uow, library.Id, relativePath).ConfigureAwait(false))!;
        }

        var value = PyStrings.Strip(failureClass).ToLowerInvariant();
        var decision = RetryPolicy.DecideForRecordedFailure(library, value, row.FailureAttempts, row.FailureClass, now);
        await uow.ExecuteAsync(
            "UPDATE refiner_files SET status = $status, status_reason = $reason, failure_class = $class, failure_attempts = $attempts, " +
            "next_retry_at = $next, last_attempt_at = $now, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
            ("$status", decision.Quarantined ? RefinerFileStatuses.OnHold : RefinerFileStatuses.ProcessingFailed),
            ("$reason", PyStrings.Slice(PyStrings.Strip($"{reason} {decision.Reason}"), 10000)),
            ("$class", value),
            ("$attempts", row.FailureAttempts + 1),
            ("$next", decision.NextRetryAt is { } next ? PythonTimestamps.Orm(next) : null),
            ("$now", PythonTimestamps.Orm(now)),
            ("$id", row.Id)).ConfigureAwait(false);
        return decision;
    }

    /// <summary>The row's reason, or null when there is no row.</summary>
    public static async Task<string?> StatusReasonAsync(UnitOfWork uow, long libraryId, string relativePath) =>
        (await FindAsync(uow, libraryId, relativePath).ConfigureAwait(false))?.StatusReason;

    /// <summary><c>row.status_reason = f"{row.status_reason} {sentence}".strip()[:10000]</c>.</summary>
    public static async Task AppendStatusReasonAsync(UnitOfWork uow, long libraryId, string relativePath, string sentence)
    {
        var row = await FindAsync(uow, libraryId, relativePath).ConfigureAwait(false);
        if (row is null)
        {
            return;
        }

        await uow.ExecuteAsync(
            "UPDATE refiner_files SET status_reason = $reason, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
            ("$reason", PyStrings.Slice(PyStrings.Strip($"{row.StatusReason} {sentence}"), 10000)),
            ("$id", row.Id)).ConfigureAwait(false);
    }

    /// <summary>
    /// <c>record_measured_media_facts</c>: matched on the path alone, on every row carrying it; a value not measured leaves the
    /// column alone.
    /// </summary>
    public static Task RecordMeasuredMediaFactsAsync(UnitOfWork uow, MeasuredMediaFacts facts)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(facts);
        var sets = new List<string>();
        var parameters = new List<(string, object?)> { ("$path", facts.RelativePath) };
        void Add(string column, object? value)
        {
            if (value is null)
            {
                return;
            }

            sets.Add($"{column} = ${column}");
            parameters.Add(($"${column}", value));
        }

        Add("video_width", facts.VideoWidth);
        Add("video_height", facts.VideoHeight);
        Add("video_codec", facts.VideoCodec is null ? null : PyStrings.Slice(facts.VideoCodec, 64));
        Add("audio_track_count", facts.AudioTrackCount);
        Add("subtitle_track_count", facts.SubtitleTrackCount);
        Add("duration_seconds", facts.DurationSeconds);
        Add("audio_codecs", facts.AudioCodecs is null
            ? null
            : PyStrings.Slice(string.Join(",", facts.AudioCodecs.Where(c => PyStrings.Strip(c).Length > 0).Select(c => PyStrings.Strip(c).ToLowerInvariant())), 1000));
        Add("video_bit_depth", facts.VideoBitDepth);
        if (sets.Count == 0)
        {
            return Task.CompletedTask;
        }

        sets.Add("updated_at = CURRENT_TIMESTAMP");
        return uow.ExecuteAsync($"UPDATE refiner_files SET {string.Join(", ", sets)} WHERE relative_path = $path", [.. parameters]);
    }

    /// <summary><c>record_output_collision</c>: the decision kept on every row for the path.</summary>
    public static Task RecordOutputCollisionAsync(UnitOfWork uow, string relativePath, CollisionDecision decision)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(decision);
        return uow.ExecuteAsync(
            "UPDATE refiner_files SET output_collision_policy = $policy, output_collision_action = $action, output_collision_reason = $reason, " +
            "updated_at = CURRENT_TIMESTAMP WHERE relative_path = $path",
            ("$policy", decision.Policy),
            ("$action", decision.Action),
            ("$reason", decision.Reason),
            ("$path", relativePath));
    }

    /// <summary><c>record_file_log</c>: one completed pass, bounded, beside the file and library it belongs to.</summary>
    public static async Task RecordFileLogAsync(UnitOfWork uow, string relativePath, string title, PyDict detail, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(detail);
        PyJson payload = detail;
        var text = PyJsonWriter.Dumps(payload, PyJsonFormat.Response);
        if (PyStrings.Length(text) > FileLogStore.MaxDetailChars)
        {
            payload = new PyDict()
                .Set("truncated", true)
                .Set("truncated_note", $"This record was longer than {FileLogStore.MaxDetailChars.ToString(CultureInfo.InvariantCulture)} characters and was shortened when it was saved.")
                .Set("outcome", detail.Get("outcome") ?? PyNull.Instance)
                .Set("detail_excerpt", PyStrings.Slice(text, FileLogStore.MaxDetailChars / 2));
            text = PyJsonWriter.Dumps(payload, PyJsonFormat.Response);
        }

        var file = await uow.QuerySingleAsync(
            "SELECT f.id, l.id, l.name FROM refiner_files f LEFT JOIN refiner_libraries l ON l.id = f.library_id WHERE f.relative_path = $path ORDER BY f.id LIMIT 1",
            reader => new object?[] { reader.GetInt64(0), reader.IsDBNull(1) ? null : reader.GetInt64(1), reader.IsDBNull(2) ? null : reader.GetString(2) },
            ("$path", relativePath)).ConfigureAwait(false);
        var outcome = detail.Get("outcome") is { IsTruthy: true } value ? PyConvert.Str(value) : string.Empty;
        await uow.ExecuteAsync(
            "INSERT INTO refiner_file_logs (file_id, library_id, relative_path, library_name, outcome, title, detail_json, recorded_at) " +
            "VALUES ($file, $library, $path, $name, $outcome, $title, $detail, $recorded)",
            ("$file", file?[0]),
            ("$library", file?[1]),
            ("$path", relativePath),
            ("$name", file?[2] as string ?? string.Empty),
            ("$outcome", outcome),
            ("$title", title),
            ("$detail", text),
            ("$recorded", PythonTimestamps.Orm(now))).ConfigureAwait(false);
    }
}
