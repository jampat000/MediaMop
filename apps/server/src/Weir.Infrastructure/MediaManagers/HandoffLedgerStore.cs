using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>One <c>media_manager_handoffs</c> row.</summary>
public sealed record HandoffLedgerRow(
    long Id,
    string SourceKey,
    string HandoffId,
    long? LibraryId,
    string RelativePath,
    string State,
    string? OutputPath,
    string? Message,
    DateTimeOffset? LastChangedAt);

/// <summary>The <c>refiner_files</c> columns the ledger reads.</summary>
public sealed record HandoffFileRow(long Id, string RelativePath, string Status, string StatusReason, long FailureAttempts, DateTimeOffset? NextRetryAt, DateTimeOffset? UpdatedAt);

/// <summary>
/// The hand-off ledger (port of <c>handoff_ledger</c>): state is worked out live from the job queue and the Files rows
/// while they exist, and the row keeps the last answer so it survives job-row pruning.
/// </summary>
public sealed class HandoffLedgerStore
{
    private const string LedgerColumns = "id, source_key, handoff_id, library_id, relative_path, state, output_path, message, last_changed_at";

    private const string JobColumns =
        "id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count, " +
        "max_attempts, last_error, not_before, runner_cost, priority, created_at, updated_at";

    private readonly TimeProvider _time;

    public HandoffLedgerStore(TimeProvider time)
    {
        _time = time ?? throw new ArgumentNullException(nameof(time));
    }

    /// <summary><c>find_handoff</c>.</summary>
    public static Task<HandoffLedgerRow?> FindAsync(UnitOfWork uow, string sourceKey, string handoffId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QuerySingleAsync(
            $"SELECT {LedgerColumns} FROM media_manager_handoffs WHERE source_key = $source AND handoff_id = $id LIMIT 1",
            ReadLedger,
            ("$source", sourceKey),
            ("$id", handoffId));
    }

    /// <summary><c>record_handoff_received</c>: at intake. A repeat of a finished hand-off starts it over.</summary>
    public async Task RecordReceivedAsync(UnitOfWork uow, string sourceKey, string handoffId, long? libraryId, string relativePath)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var now = PythonTimestamps.Orm(_time.GetUtcNow());
        var row = await FindAsync(uow, sourceKey, handoffId).ConfigureAwait(false);
        if (row is null)
        {
            await uow.ExecuteAsync(
                "INSERT INTO media_manager_handoffs (source_key, handoff_id, library_id, relative_path, state, output_path, message, created_at, last_changed_at) " +
                "VALUES ($source, $id, $library, $path, $state, NULL, NULL, $now, $now)",
                ("$source", sourceKey),
                ("$id", handoffId),
                ("$library", libraryId),
                ("$path", relativePath),
                ("$state", HandoffLedgerRules.Queued),
                ("$now", now)).ConfigureAwait(false);
        }
        else if (HandoffLedgerRules.TerminalStates.Contains(row.State))
        {
            await uow.ExecuteAsync(
                "UPDATE media_manager_handoffs SET library_id = $library, relative_path = $path, state = $state, output_path = NULL, " +
                "message = NULL, last_changed_at = $now WHERE id = $row",
                ("$library", libraryId),
                ("$path", relativePath),
                ("$state", HandoffLedgerRules.Queued),
                ("$now", now),
                ("$row", row.Id)).ConfigureAwait(false);
        }
    }

    /// <summary><c>record_handoff_outcome</c>: a result Weir reached. Unknown and cancelled hand-offs are left alone.</summary>
    public async Task RecordOutcomeAsync(UnitOfWork uow, string sourceKey, string? handoffId, string state, string? outputPath = null, string? message = null)
    {
        ArgumentNullException.ThrowIfNull(uow);
        if (string.IsNullOrEmpty(handoffId))
        {
            return;
        }

        var row = await FindAsync(uow, sourceKey, handoffId).ConfigureAwait(false);
        if (row is null || row.State == HandoffLedgerRules.Cancelled)
        {
            return;
        }

        if (row.State != state || row.OutputPath != outputPath)
        {
            await uow.ExecuteAsync(
                "UPDATE media_manager_handoffs SET state = $state, output_path = $output, message = $message, last_changed_at = $now WHERE id = $row",
                ("$state", state),
                ("$output", outputPath),
                ("$message", string.IsNullOrEmpty(message) ? null : PyStrings.Slice(message, 2000)),
                ("$now", PythonTimestamps.Orm(_time.GetUtcNow())),
                ("$row", row.Id)).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// <c>_file_rows</c>: the file, or every file under the folder, this hand-off covers.
    /// #544 item 5: Python's SQLAlchemy <c>.startswith()</c> (and the SQL <c>LIKE</c> it ported to here) treats an
    /// unescaped <c>_</c> or <c>%</c> in the hand-off's path as a wildcard, so a sibling folder whose name merely
    /// resembles this one (<c>Foo_Bar</c> matching a folder literally named <c>FooXBar</c>) is wrongly folded into
    /// this hand-off's status, and SQLite's default <c>LIKE</c> also ignores case regardless of platform. Matching
    /// is exact prefix comparison instead — a plain string compare, so no character needs escaping — with case
    /// handled per OS path semantics, the same decision already used for filesystem-path comparisons elsewhere in
    /// this codebase (<see cref="ReconciliationService.SafeUnlinkUnderRoots"/>,
    /// <see cref="HandoffCompletionReporter.TranslateOutputPath"/>): case-insensitive on Windows, case-sensitive
    /// everywhere else. Filtering happens in .NET rather than in SQL so no escaping scheme is needed at all.
    /// </summary>
    public static async Task<List<HandoffFileRow>> FileRowsAsync(UnitOfWork uow, HandoffLedgerRow row)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(row);
        if (row.LibraryId is not { } libraryId)
        {
            return [];
        }

        var path = row.RelativePath.TrimEnd('/');
        var rows = await uow.QueryAsync(
            "SELECT id, relative_path, status, status_reason, failure_attempts, next_retry_at, updated_at FROM refiner_files " +
            "WHERE library_id = $library",
            reader => new HandoffFileRow(
                SqliteValues.GetInt64(reader, 0),
                SqliteValues.GetString(reader, 1),
                SqliteValues.GetString(reader, 2),
                SqliteValues.GetString(reader, 3),
                SqliteValues.GetInt64(reader, 4),
                PythonTimestamps.Parse(reader.GetValue(5)),
                PythonTimestamps.Parse(reader.GetValue(6))),
            ("$library", libraryId)).ConfigureAwait(false);

        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var prefix = path + "/";
        return [.. rows.Where(file => string.Equals(file.RelativePath, path, comparison) || file.RelativePath.StartsWith(prefix, comparison))];
    }

    /// <summary>
    /// <c>_jobs_for</c>: pending or leased jobs keyed to this hand-off, or the failure-policy jobs for its files.
    /// #544 item 5: the same <c>LIKE</c>-as-prefix-match defect as <see cref="FileRowsAsync"/>, here over
    /// <c>dedupe_key</c> — a hand-off id containing <c>_</c> or <c>%</c> could match another hand-off's jobs. A job
    /// dedupe key is an opaque identifier rather than a filesystem path, so unlike the file-path comparison this
    /// one is always case-sensitive (ordinal), matching Python's own <c>str.startswith</c> semantics; the exact
    /// comparison is still done in SQL (<c>substr(...) =</c>, SQLite's default <c>BINARY</c>/case-sensitive
    /// collation for <c>=</c>) since it can stay parameterised alongside this query's other conditions.
    /// </summary>
    public static async Task<List<RefinerJob>> JobsForAsync(UnitOfWork uow, HandoffLedgerRow row)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(row);
        var baseKey = IntakeRules.RemuxDedupeKey(row.SourceKey, row.HandoffId);
        var conditions = new List<string> { "dedupe_key = $base", "substr(dedupe_key, 1, length($base_prefix)) = $base_prefix" };
        var parameters = new List<(string, object?)> { ("$base", baseKey), ("$base_prefix", baseKey + ":") };
        if (row.LibraryId is { } libraryId)
        {
            var paths = new HashSet<string>(StringComparer.Ordinal) { row.RelativePath };
            foreach (var file in await FileRowsAsync(uow, row).ConfigureAwait(false))
            {
                paths.Add(file.RelativePath);
            }

            var index = 0;
            foreach (var path in paths)
            {
                // #545 item 2: pass-through and reject dedupe keys now carry the source's fingerprint as a trailing
                // segment (so a later failure of a since-replaced file queues again), so the ledger matches the base
                // "{kind}:{library}:{path}" either exactly (older rows written before the fix) or as a prefix.
                var passBase = $"{IntakeRules.PassThroughJobKind}:{libraryId.ToString(CultureInfo.InvariantCulture)}:{path}";
                var rejectBase = $"{IntakeRules.RejectJobKind}:{libraryId.ToString(CultureInfo.InvariantCulture)}:{path}";
                conditions.Add($"(dedupe_key = $pass_{index} OR dedupe_key LIKE $pass_{index} || ':%')");
                parameters.Add(($"$pass_{index}", passBase));
                conditions.Add($"(dedupe_key = $reject_{index} OR dedupe_key LIKE $reject_{index} || ':%')");
                parameters.Add(($"$reject_{index}", rejectBase));
                index++;
            }
        }

        parameters.Add(("$pending", RefinerJobStatus.Pending));
        parameters.Add(("$leased", RefinerJobStatus.Leased));
        parameters.Add(("$failed", RefinerJobStatus.Failed));
        parameters.Add(("$pass_kind", IntakeRules.PassThroughJobKind));
        parameters.Add(("$reject_kind", IntakeRules.RejectJobKind));
        // #545 item 3: a pass-through or reject job that exhausted its own retries drops out of pending/leased, but it
        // is still an undelivered outcome the manager needs to hear about (as failed, with the reason) rather than
        // silently vanishing from the ledger's view.
        return await uow.QueryAsync(
            $"SELECT {JobColumns} FROM refiner_jobs WHERE ({string.Join(" OR ", conditions)}) AND " +
            "(status IN ($pending, $leased) OR (status = $failed AND job_kind IN ($pass_kind, $reject_kind)))",
            ReadJob,
            [.. parameters]).ConfigureAwait(false);
    }

    /// <summary><c>_queue_position</c>: pending jobs ahead of this one, plus one.</summary>
    public static async Task<long> QueuePositionAsync(UnitOfWork uow, RefinerJob job)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(job);
        var ahead = await uow.CountAsync(
            "SELECT count(id) FROM refiner_jobs WHERE status = $pending AND (priority > $priority OR (priority = $priority AND id < $id))",
            ("$pending", RefinerJobStatus.Pending),
            ("$priority", job.Priority),
            ("$id", job.Id)).ConfigureAwait(false);
        return ahead + 1;
    }

    /// <summary><c>current_status</c>: work the state out from what exists now, and keep the ledger row in step with it.</summary>
    public async Task<HandoffStatus> CurrentStatusAsync(UnitOfWork uow, HandoffLedgerRow row)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(row);
        var now = PyDateTimeNow();
        string? liveState = null;
        DateTimeOffset? changedAt = null;
        long? queuePosition = null;
        DateTimeOffset? scheduledFor = null;
        string? message = null;

        if (row.State != HandoffLedgerRules.Cancelled)
        {
            var jobs = await JobsForAsync(uow, row).ConfigureAwait(false);
            var files = await FileRowsAsync(uow, row).ConfigureAwait(false);
            var states = new List<string>();
            var stamps = new List<DateTimeOffset>();
            var busyPaths = new HashSet<string>(StringComparer.Ordinal);

            foreach (var job in jobs)
            {
                stamps.Add(job.UpdatedAt);
                if (PayloadRelativePath(job.PayloadJson) is { } busyPath)
                {
                    busyPaths.Add(busyPath);
                }

                var isOutcomeJob = job.JobKind is IntakeRules.PassThroughJobKind or IntakeRules.RejectJobKind;

                // #545 item 3: a pass-through or reject job that exhausted its own retries is a final, undelivered
                // outcome — report it as failed, with the reason the job itself recorded, rather than let it vanish
                // once it drops out of pending/leased (JobsForAsync still returns it for exactly this reason).
                if (job.Status == RefinerJobStatus.Failed)
                {
                    states.Add(HandoffLedgerRules.Failed);
                    message ??= string.IsNullOrEmpty(job.LastError) ? "Weir could not hand this file back to your media manager." : job.LastError;
                    continue;
                }

                if (job.Status == RefinerJobStatus.Leased)
                {
                    states.Add(HandoffLedgerRules.Working);
                    continue;
                }

                if (isOutcomeJob)
                {
                    // A pending pass-through or reject job is a decided disposition about to run, not a normal place
                    // in the remux queue, so it is reported as scheduled rather than queued (and carries no queue
                    // position — that field means something only for the remux queue itself).
                    states.Add(HandoffLedgerRules.Scheduled);
                    if (job.NotBefore is { } outcomeNotBefore && outcomeNotBefore > now)
                    {
                        scheduledFor = scheduledFor is { } currentOutcome ? Min(currentOutcome, outcomeNotBefore) : outcomeNotBefore;
                    }

                    continue;
                }

                if (job.NotBefore is { } notBefore && notBefore > now)
                {
                    states.Add(HandoffLedgerRules.Scheduled);
                    scheduledFor = scheduledFor is { } current ? Min(current, notBefore) : notBefore;
                }
                else
                {
                    states.Add(HandoffLedgerRules.Queued);
                    var position = await QueuePositionAsync(uow, job).ConfigureAwait(false);
                    queuePosition = queuePosition is { } currentPosition && currentPosition != 0 ? Math.Min(currentPosition, position) : position;
                }
            }

            foreach (var file in files)
            {
                if (file.UpdatedAt is { } stamp)
                {
                    stamps.Add(stamp);
                }

                if (busyPaths.Contains(file.RelativePath))
                {
                    if (file.StatusReason.Length > 0 && message is null)
                    {
                        message = file.StatusReason;
                    }

                    continue;
                }

                var (state, when) = HandoffLedgerRules.FileState(file.Status, file.NextRetryAt, file.FailureAttempts);
                states.Add(state);
                if (when is { } whenValue)
                {
                    scheduledFor = scheduledFor is { } current ? Min(current, whenValue) : whenValue;
                }

                if (file.StatusReason.Length > 0 && (message is null || !HandoffLedgerRules.TerminalStates.Contains(state)))
                {
                    message = file.StatusReason;
                }
            }

            if (states.Count > 0)
            {
                liveState = HandoffLedgerRules.Combine(states);
                changedAt = stamps.Count > 0 ? stamps.Max() : null;
                if (liveState != HandoffLedgerRules.Queued)
                {
                    queuePosition = null;
                }

                if (liveState != HandoffLedgerRules.Scheduled)
                {
                    scheduledFor = null;
                }
            }
        }

        var answerState = row.State;
        var lastChanged = row.LastChangedAt;
        var storedMessage = row.Message;
        if (liveState is not null)
        {
            var changes = new List<(string, object?)>();
            var previous = row.LastChangedAt;
            if (liveState != row.State)
            {
                answerState = liveState;
                lastChanged = changedAt is { } changed && (previous is null || changed > previous) ? changedAt : now;
                changes.Add(("state", answerState));
                changes.Add(("last_changed_at", PythonTimestamps.Orm(lastChanged!.Value)));
            }
            else if (changedAt is { } newer && previous is { } before && newer > before)
            {
                lastChanged = newer;
                changes.Add(("last_changed_at", PythonTimestamps.Orm(newer)));
            }

            if (message is not null && !HandoffLedgerRules.TerminalStates.Contains(liveState))
            {
                var sliced = PyStrings.Slice(message, 2000);
                if (sliced != row.Message)
                {
                    storedMessage = sliced;
                    changes.Add(("message", sliced));
                }
            }

            if (changes.Count > 0)
            {
                var sets = changes.Select((change, index) => $"{change.Item1} = $v{index}");
                await uow.ExecuteAsync(
                    $"UPDATE media_manager_handoffs SET {string.Join(", ", sets)} WHERE id = $row",
                    [.. changes.Select((change, index) => ($"$v{index}", change.Item2)), ("$row", row.Id)]).ConfigureAwait(false);
            }
        }

        return new HandoffStatus(
            row.HandoffId,
            answerState,
            lastChanged ?? now,
            queuePosition,
            scheduledFor,
            answerState is HandoffLedgerRules.Completed or HandoffLedgerRules.PassedThrough ? row.OutputPath : null,
            message ?? storedMessage);
    }

    /// <summary>
    /// <c>cancel_handoff</c>: drop a hand-off that has not started. Never touches a file and never stops running work.
    /// </summary>
    public async Task<(bool Cancelled, string Sentence)> CancelAsync(UnitOfWork uow, RefinerJobStore jobs, HandoffLedgerRow row)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(jobs);
        ArgumentNullException.ThrowIfNull(row);
        var status = await CurrentStatusAsync(uow, row).ConfigureAwait(false);
        if (status.State is not (HandoffLedgerRules.Queued or HandoffLedgerRules.Scheduled))
        {
            return (false, IntakeRules.RefusedCancelSentence(status.State));
        }

        foreach (var job in await JobsForAsync(uow, row).ConfigureAwait(false))
        {
            if (job.Status != RefinerJobStatus.Pending)
            {
                continue;
            }

            await uow.ExecuteAsync(
                "UPDATE refiner_jobs SET dedupe_key = $dedupe, status = $status, lease_owner = NULL, lease_expires_at = NULL, " +
                "last_error = $error, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
                ("$dedupe", JobQueueRules.TombstoneCancelledDedupeKey(job.DedupeKey, job.Id)),
                ("$status", RefinerJobStatus.Cancelled),
                ("$error", JobQueueRules.CancelledByOperatorError),
                ("$id", job.Id)).ConfigureAwait(false);
        }

        foreach (var file in await FileRowsAsync(uow, row).ConfigureAwait(false))
        {
            if (file.NextRetryAt is not null)
            {
                await uow.ExecuteAsync(
                    "UPDATE refiner_files SET next_retry_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
                    ("$id", file.Id)).ConfigureAwait(false);
            }
        }

        await uow.ExecuteAsync(
            "UPDATE media_manager_handoffs SET state = $state, message = $message, last_changed_at = $now WHERE id = $row",
            ("$state", HandoffLedgerRules.Cancelled),
            ("$message", HandoffLedgerRules.CancelledMessage),
            ("$now", PythonTimestamps.Orm(_time.GetUtcNow())),
            ("$row", row.Id)).ConfigureAwait(false);
        return (true, HandoffLedgerRules.CancelledMessage);
    }

    /// <summary>
    /// The <c>relative_media_path</c> a job payload names, as <c>str(... or "")</c>; null for unreadable JSON (suppressed in
    /// Python). A payload that is not an object fails as in Python.
    /// </summary>
    private static string? PayloadRelativePath(string? payloadJson)
    {
        PyJson parsed;
        try
        {
            parsed = PyJsonParser.Parse(string.IsNullOrEmpty(payloadJson) ? "{}" : payloadJson);
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }

        if (parsed is not PyDict dict)
        {
            throw new InvalidOperationException($"'{parsed.PythonTypeName}' object has no attribute 'get'");
        }

        return dict.Get("relative_media_path") is { IsTruthy: true } value ? PyConvert.Str(value) : string.Empty;
    }

    private DateTimeOffset PyDateTimeNow() => Weir.Core.Time.PyDateTime.TruncateToMicroseconds(_time.GetUtcNow());

    private static DateTimeOffset Min(DateTimeOffset a, DateTimeOffset b) => a <= b ? a : b;

    private static HandoffLedgerRow ReadLedger(SqliteDataReader reader) => new(
        SqliteValues.GetInt64(reader, 0),
        SqliteValues.GetString(reader, 1),
        SqliteValues.GetString(reader, 2),
        reader.IsDBNull(3) ? null : SqliteValues.GetInt64(reader, 3),
        SqliteValues.GetString(reader, 4),
        SqliteValues.GetString(reader, 5),
        SqliteValues.GetStringOrNull(reader, 6),
        SqliteValues.GetStringOrNull(reader, 7),
        PythonTimestamps.Parse(reader.GetValue(8)));

    internal static RefinerJob ReadJob(SqliteDataReader reader) => new(
        reader.GetInt64(0),
        reader.GetString(1),
        reader.GetString(2),
        reader.IsDBNull(3) ? null : reader.GetString(3),
        reader.GetString(4),
        reader.IsDBNull(5) ? null : reader.GetString(5),
        PythonTimestamps.Parse(reader.GetValue(6)),
        (int)reader.GetInt64(7),
        (int)reader.GetInt64(8),
        reader.IsDBNull(9) ? null : reader.GetString(9),
        PythonTimestamps.Parse(reader.GetValue(10)),
        (int)reader.GetInt64(11),
        (int)reader.GetInt64(12),
        PythonTimestamps.Parse(reader.GetValue(13)) ?? DateTimeOffset.MinValue,
        PythonTimestamps.Parse(reader.GetValue(14)) ?? DateTimeOffset.MinValue);
}
