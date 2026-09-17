using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// Which job kinds a claim may lease. Python claims every kind; the .NET workers claim only kinds they
/// have a handler for, plus kinds no worker may run, which they claim only to refuse
/// (see <see cref="JobHandlerRegistry"/>).
/// </summary>
public sealed record ClaimableKinds(IReadOnlyList<string> HandledKinds, bool IncludeRefusedKinds)
{
    /// <summary>What the .NET workers claim for a registry.</summary>
    public static ClaimableKinds For(JobHandlerRegistry registry)
    {
        ArgumentNullException.ThrowIfNull(registry);
        return new ClaimableKinds(registry.JobKinds, IncludeRefusedKinds: true);
    }
}

/// <summary>Queue counters for the metrics port (Python's <c>record_module_job_event</c> and <c>set_module_queue_depth</c>).</summary>
public interface IJobQueueMetrics
{
    /// <summary><paramref name="jobEvent"/> is <c>started</c>, <c>completed</c> or <c>failed</c>.</summary>
    void RecordJobEvent(string moduleName, string jobEvent);

    void SetQueueDepth(string moduleName, int depth);
}

/// <summary>Discards queue counters until the metrics port supplies an implementation.</summary>
public sealed class NoJobQueueMetrics : IJobQueueMetrics
{
    public static NoJobQueueMetrics Instance { get; } = new();

    public void RecordJobEvent(string moduleName, string jobEvent)
    {
    }

    public void SetQueueDepth(string moduleName, int depth)
    {
    }
}

/// <summary>
/// The durable <c>refiner_jobs</c> queue (port of <c>weir.refiner.jobs_ops</c>): enqueue-or-get by dedupe
/// key, atomic claim with a lease, complete, fail with retry and backoff, and the operator actions.
/// </summary>
/// <remarks>
/// Every operation runs in one <c>BEGIN IMMEDIATE</c> transaction, so SQLite's single writer serialises
/// it against every other connection, including the Python backend's. The claim is Python's single
/// <c>UPDATE … WHERE id = (SELECT … LIMIT 1) RETURNING id</c> statement, with the same text comparisons
/// on the same timestamp strings.
/// </remarks>
public sealed class RefinerJobStore
{
    public const string MetricsModule = "refiner";

    private const string SelectColumns =
        "id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count, " +
        "max_attempts, last_error, not_before, runner_cost, priority, created_at, updated_at";

    private const string ClaimSqlTemplate = """
        UPDATE refiner_jobs
        SET
          status = @leased,
          lease_owner = @owner,
          lease_expires_at = @lease_exp,
          updated_at = CURRENT_TIMESTAMP,
          attempt_count = attempt_count + 1
        WHERE id = (
          SELECT id FROM refiner_jobs
          WHERE (
              (status = @pending AND (not_before IS NULL OR not_before <= @now))
              OR (
                status = @leased
                AND (lease_expires_at IS NULL OR lease_expires_at < @now)
              )
            )
            {admission}{kinds}
          ORDER BY priority DESC, id ASC
          LIMIT 1
        )
        RETURNING id
        """;

    private readonly SqliteDatabase _database;
    private readonly TimeProvider _time;
    private readonly IJobQueueMetrics _metrics;

    public RefinerJobStore(SqliteDatabase database, TimeProvider time, IJobQueueMetrics? metrics = null)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _metrics = metrics ?? NoJobQueueMetrics.Instance;
    }

    public SqliteDatabase Database => _database;

    /// <summary>
    /// <c>refiner_enqueue_or_get_job</c>: insert a pending job, or return the row already holding
    /// <paramref name="dedupeKey"/>.
    /// </summary>
    /// <exception cref="ArgumentException">The job kind is retired or not a <c>refiner.*</c> kind.</exception>
    public Task<RefinerJob> EnqueueOrGetAsync(
        string dedupeKey,
        string jobKind,
        string? payloadJson = null,
        int maxAttempts = JobQueueRules.DefaultMaxAttempts,
        int runnerCost = 0,
        int priority = 0,
        CancellationToken cancellationToken = default)
    {
        JobKindGuard.ValidateEnqueueJobKind(jobKind);
        ArgumentNullException.ThrowIfNull(dedupeKey);
        return InTransactionAsync(
            (connection, transaction) => EnqueueOrGet(connection, transaction, dedupeKey, jobKind, payloadJson, maxAttempts, runnerCost, priority),
            cancellationToken);
    }

    /// <summary>
    /// <c>claim_next_eligible_refiner_job</c>: atomically lease the next pending or expired-lease row.
    /// Increments <c>attempt_count</c> on every claim, including a reclaim.
    /// </summary>
    public Task<RefinerJob?> ClaimNextAsync(
        string leaseOwner,
        DateTimeOffset leaseExpiresAt,
        DateTimeOffset? now = null,
        WorkAdmission? admission = null,
        ClaimableKinds? kinds = null,
        CancellationToken cancellationToken = default)
    {
        var when = now ?? _time.GetUtcNow();
        return InTransactionAsync(
            (connection, transaction) => ClaimNext(connection, transaction, leaseOwner, leaseExpiresAt, when, admission, kinds),
            cancellationToken);
    }

    /// <summary>
    /// The worker's claim: evaluate admission (pause, schedules, budget) and claim in the same write
    /// transaction, so two workers cannot both see room for one more job.
    /// </summary>
    public Task<RefinerJob?> ClaimNextAdmittedAsync(
        string leaseOwner,
        DateTimeOffset leaseExpiresAt,
        DateTimeOffset now,
        ClaimableKinds? kinds,
        CancellationToken cancellationToken = default) =>
        InTransactionAsync(
            (connection, transaction) =>
            {
                var admission = WorkAdmissionReader.Evaluate(connection, transaction, now);
                return ClaimNext(connection, transaction, leaseOwner, leaseExpiresAt, now, admission, kinds);
            },
            cancellationToken);

    /// <summary><c>complete_claimed_refiner_job</c>: only for the owning, unexpired lease.</summary>
    public Task<bool> CompleteClaimedAsync(long jobId, string leaseOwner, DateTimeOffset? now = null, CancellationToken cancellationToken = default)
    {
        var when = now ?? _time.GetUtcNow();
        return InTransactionAsync(
            (connection, transaction) =>
            {
                var job = Get(connection, transaction, jobId);
                if (!HoldsLease(job, leaseOwner, when))
                {
                    return false;
                }

                Execute(
                    connection,
                    transaction,
                    "UPDATE refiner_jobs SET status = @status, lease_owner = NULL, lease_expires_at = NULL, last_error = NULL, " +
                    "updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                    ("@status", RefinerJobStatus.Completed),
                    ("@id", jobId));
                _metrics.RecordJobEvent(MetricsModule, "completed");
                RecordQueueDepth(connection, transaction);
                return true;
            },
            cancellationToken);
    }

    /// <summary>
    /// <c>fail_claimed_refiner_job</c>: after a failed attempt, requeue with backoff, or mark failed once
    /// the attempts are used.
    /// </summary>
    public Task<bool> FailClaimedAsync(long jobId, string leaseOwner, string errorMessage, DateTimeOffset? now = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(errorMessage);
        var when = now ?? _time.GetUtcNow();
        return InTransactionAsync(
            (connection, transaction) =>
            {
                var job = Get(connection, transaction, jobId);
                if (job is null || !HoldsLease(job, leaseOwner, when))
                {
                    return false;
                }

                if (job.AttemptCount >= job.MaxAttempts)
                {
                    Execute(
                        connection,
                        transaction,
                        "UPDATE refiner_jobs SET last_error = @error, lease_owner = NULL, lease_expires_at = NULL, status = @status, " +
                        "not_before = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                        ("@error", errorMessage),
                        ("@status", RefinerJobStatus.Failed),
                        ("@id", jobId));
                    _metrics.RecordJobEvent(MetricsModule, "failed");
                }
                else
                {
                    var delay = JobQueueRules.RetryBackoffSeconds(job.AttemptCount);
                    Execute(
                        connection,
                        transaction,
                        "UPDATE refiner_jobs SET last_error = @error, lease_owner = NULL, lease_expires_at = NULL, status = @status, " +
                        "not_before = @not_before, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                        ("@error", errorMessage),
                        ("@status", RefinerJobStatus.Pending),
                        ("@not_before", PythonTimestamps.Orm(when + TimeSpan.FromTicks((long)Math.Round(delay * TimeSpan.TicksPerSecond)))),
                        ("@id", jobId));
                }

                RecordQueueDepth(connection, transaction);
                return true;
            },
            cancellationToken);
    }

    /// <summary>
    /// <c>fail_leased_refiner_job_after_complete_failure</c>: the handler succeeded but recording it did
    /// not. Terminal and not claimable; <c>attempt_count</c> is unchanged.
    /// </summary>
    public Task<bool> FailLeasedAfterCompleteFailureAsync(long jobId, string leaseOwner, string errorMessage, DateTimeOffset? now = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(errorMessage);
        var when = now ?? _time.GetUtcNow();
        return InTransactionAsync(
            (connection, transaction) =>
            {
                var job = Get(connection, transaction, jobId);
                if (!HoldsLease(job, leaseOwner, when))
                {
                    return false;
                }

                Execute(
                    connection,
                    transaction,
                    "UPDATE refiner_jobs SET status = @status, lease_owner = NULL, lease_expires_at = NULL, last_error = @error, " +
                    "updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                    ("@status", RefinerJobStatus.HandlerOkFinalizeFailed),
                    ("@error", PyStrings.Slice(errorMessage, JobQueueRules.LastErrorLimit)),
                    ("@id", jobId));
                _metrics.RecordJobEvent(MetricsModule, "failed");
                RecordQueueDepth(connection, transaction);
                return true;
            },
            cancellationToken);
    }

    /// <summary>
    /// <c>recover_handler_ok_finalize_failed_to_completed</c>: operator recovery that marks the row
    /// completed without re-running the handler.
    /// </summary>
    public Task<JobActionOutcome> RecoverHandlerOkFinalizeFailedToCompletedAsync(
        long jobId,
        string recoveredByLabel,
        DateTimeOffset? now = null,
        CancellationToken cancellationToken = default)
    {
        var when = now ?? _time.GetUtcNow();
        return InTransactionAsync(
            (connection, transaction) =>
            {
                var job = Get(connection, transaction, jobId);
                if (job is null)
                {
                    return JobActionOutcome.NotFound;
                }

                if (job.Status != RefinerJobStatus.HandlerOkFinalizeFailed)
                {
                    return JobActionOutcome.WrongStatus;
                }

                Execute(
                    connection,
                    transaction,
                    "UPDATE refiner_jobs SET last_error = @error, status = @status, lease_owner = NULL, lease_expires_at = NULL, " +
                    "updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                    ("@error", JobQueueRules.RecoveredFinalizeFailureError(job.LastError, PyDateTime.TruncateToMicroseconds(when.ToUniversalTime()), recoveredByLabel)),
                    ("@status", RefinerJobStatus.Completed),
                    ("@id", jobId));
                _metrics.RecordJobEvent(MetricsModule, "completed");
                RecordQueueDepth(connection, transaction);
                return JobActionOutcome.Ok;
            },
            cancellationToken);
    }

    /// <summary>
    /// <c>cancel_pending_refiner_job</c>: only pending rows. The dedupe key becomes a tombstone so a later
    /// enqueue may reuse it.
    /// </summary>
    public Task<JobActionOutcome> CancelPendingAsync(long jobId, CancellationToken cancellationToken = default) =>
        InTransactionAsync(
            (connection, transaction) =>
            {
                var job = Get(connection, transaction, jobId);
                if (job is null)
                {
                    return JobActionOutcome.NotFound;
                }

                if (job.Status != RefinerJobStatus.Pending)
                {
                    return JobActionOutcome.WrongStatus;
                }

                Execute(
                    connection,
                    transaction,
                    "UPDATE refiner_jobs SET dedupe_key = @dedupe, status = @status, lease_owner = NULL, lease_expires_at = NULL, " +
                    "last_error = @error, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                    ("@dedupe", JobQueueRules.TombstoneCancelledDedupeKey(job.DedupeKey, job.Id)),
                    ("@status", RefinerJobStatus.Cancelled),
                    ("@error", JobQueueRules.CancelledByOperatorError),
                    ("@id", jobId));
                return JobActionOutcome.Ok;
            },
            cancellationToken);

    /// <summary><c>move_refiner_job_to_top</c>: raise one pending job above everything else waiting.</summary>
    public Task<JobActionOutcome> MoveToTopAsync(long jobId, CancellationToken cancellationToken = default) =>
        InTransactionAsync(
            (connection, transaction) =>
            {
                var job = Get(connection, transaction, jobId);
                if (job is null)
                {
                    return JobActionOutcome.NotFound;
                }

                if (job.Status != RefinerJobStatus.Pending)
                {
                    return JobActionOutcome.WrongStatus;
                }

                var highest = Scalar(connection, transaction, "SELECT max(priority) FROM refiner_jobs WHERE status = @pending", ("@pending", RefinerJobStatus.Pending));
                var priority = (highest is null or DBNull ? 0 : Convert.ToInt64(highest, CultureInfo.InvariantCulture)) + 1;
                if (priority != job.Priority)
                {
                    Execute(
                        connection,
                        transaction,
                        "UPDATE refiner_jobs SET priority = @priority, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                        ("@priority", priority),
                        ("@id", jobId));
                }

                return JobActionOutcome.Ok;
            },
            cancellationToken);

    public Task<RefinerJob?> GetAsync(long jobId, CancellationToken cancellationToken = default) =>
        InTransactionAsync((connection, transaction) => Get(connection, transaction, jobId), cancellationToken);

    public Task<IReadOnlyList<RefinerJob>> ListAsync(CancellationToken cancellationToken = default) =>
        InTransactionAsync<IReadOnlyList<RefinerJob>>(
            (connection, transaction) => Query(connection, transaction, $"SELECT {SelectColumns} FROM refiner_jobs ORDER BY id"),
            cancellationToken);

    /// <summary>Run <paramref name="work"/> in one <c>BEGIN IMMEDIATE</c> transaction and commit.</summary>
    public async Task<T> InTransactionAsync<T>(Func<SqliteConnection, SqliteTransaction, T> work, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(work);
        var connection = await _database.OpenAsync(cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            // Not deferred: Microsoft.Data.Sqlite issues BEGIN IMMEDIATE, taking the write lock up front.
            var transaction = connection.BeginTransaction(deferred: false);
            await using (transaction.ConfigureAwait(false))
            {
                var result = work(connection, transaction);
                await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
                return result;
            }
        }
    }

    internal RefinerJob EnqueueOrGet(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string dedupeKey,
        string jobKind,
        string? payloadJson,
        int maxAttempts,
        int runnerCost,
        int priority)
    {
        JobKindGuard.ValidateEnqueueJobKind(jobKind);
        var existing = GetByDedupeKey(connection, transaction, dedupeKey);
        if (existing is not null)
        {
            return existing;
        }

        var inserted = Scalar(
            connection,
            transaction,
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, max_attempts, runner_cost, priority) " +
            "VALUES (@dedupe, @kind, @payload, @status, @max_attempts, @runner_cost, @priority) " +
            "ON CONFLICT (dedupe_key) DO NOTHING RETURNING id",
            ("@dedupe", dedupeKey),
            ("@kind", jobKind),
            ("@payload", payloadJson),
            ("@status", RefinerJobStatus.Pending),
            ("@max_attempts", Math.Max(1, maxAttempts)),
            ("@runner_cost", Math.Max(0, runnerCost)),
            ("@priority", priority));
        if (inserted is not null and not DBNull)
        {
            RecordQueueDepth(connection, transaction);
        }

        return GetByDedupeKey(connection, transaction, dedupeKey)
               ?? throw new InvalidOperationException("refiner job dedupe race: row missing after IntegrityError");
    }

    internal RefinerJob? ClaimNext(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string leaseOwner,
        DateTimeOffset leaseExpiresAt,
        DateTimeOffset now,
        WorkAdmission? admission,
        ClaimableKinds? kinds)
    {
        ArgumentNullException.ThrowIfNull(leaseOwner);
        var parameters = new List<(string, object?)>
        {
            ("@leased", RefinerJobStatus.Leased),
            ("@pending", RefinerJobStatus.Pending),
            ("@owner", leaseOwner),
            ("@lease_exp", PythonTimestamps.Adapter(leaseExpiresAt)),
            ("@now", PythonTimestamps.Adapter(now)),
        };
        var predicate = AdmissionPredicate(admission, parameters);
        var kindsPredicate = KindsPredicate(kinds, parameters);
        var sql = ClaimSqlTemplate
            .Replace("{admission}", predicate, StringComparison.Ordinal)
            .Replace("{kinds}", kindsPredicate, StringComparison.Ordinal);
        var id = Scalar(connection, transaction, sql, [.. parameters]);
        if (id is null or DBNull)
        {
            return null;
        }

        var claimed = Get(connection, transaction, Convert.ToInt64(id, CultureInfo.InvariantCulture))!;
        _metrics.RecordJobEvent(MetricsModule, "started");
        RecordQueueDepth(connection, transaction);
        return claimed;
    }

    /// <summary>
    /// <c>_admission_predicate</c>: SQL narrowing the claim to work this pass may start. Library ids are
    /// integers formatted into the statement, as Python does, because a variable-length <c>IN</c> list
    /// cannot be one bound parameter.
    /// </summary>
    internal static string AdmissionPredicate(WorkAdmission? admission, List<(string Name, object? Value)> parameters)
    {
        if (admission is null)
        {
            return string.Empty;
        }

        var clauses = new List<string>();
        var ids = admission.BlockedLibraryIds.Distinct().Order().ToList();
        if (ids.Count > 0)
        {
            // A job with no library_id predates libraries or is suite-wide; COALESCE keeps it claimable.
            var rendered = string.Join(",", ids.Select(id => id.ToString(CultureInfo.InvariantCulture)));
            clauses.Add($"AND COALESCE(json_extract(payload_json, '$.library_id'), -1) NOT IN ({rendered})");
        }

        clauses.Add("AND runner_cost <= @available_units");
        parameters.Add(("@available_units", Math.Max(0, admission.AvailableUnits)));

        if (admission.Pause.Paused)
        {
            if (admission.Pause.ScanWhilePaused)
            {
                var likes = new List<string>();
                for (var index = 0; index < WorkAdmissionRules.DetectionJobKindPrefixes.Count; index++)
                {
                    var name = $"@detect_{index}";
                    likes.Add($"job_kind LIKE {name}");
                    parameters.Add((name, WorkAdmissionRules.DetectionJobKindPrefixes[index] + "%"));
                }

                clauses.Add($"AND ({string.Join(" OR ", likes)})");
            }
            else
            {
                clauses.Add("AND 1 = 0");
            }
        }

        return "\n    " + string.Join("\n    ", clauses);
    }

    /// <summary>The .NET-only narrowing to kinds this server can run or must refuse.</summary>
    internal static string KindsPredicate(ClaimableKinds? kinds, List<(string Name, object? Value)> parameters)
    {
        if (kinds is null)
        {
            return string.Empty;
        }

        var alternatives = new List<string>();
        var handled = kinds.HandledKinds.Distinct(StringComparer.Ordinal).ToList();
        if (handled.Count > 0)
        {
            var names = new List<string>();
            for (var index = 0; index < handled.Count; index++)
            {
                var name = $"@kind_{index}";
                names.Add(name);
                parameters.Add((name, handled[index]));
            }

            alternatives.Add($"job_kind IN ({string.Join(", ", names)})");
        }

        if (kinds.IncludeRefusedKinds)
        {
            // substr/= rather than LIKE: LIKE is case-insensitive and treats '_' as a wildcard, and
            // Python's str.startswith is neither.
            alternatives.Add(PrefixTest(JobKindGuard.JobKindPrefix, "@refused_prefix", parameters, negate: true));
            for (var index = 0; index < JobKindGuard.RetiredPrefixes.Count; index++)
            {
                alternatives.Add(PrefixTest(JobKindGuard.RetiredPrefixes[index], $"@retired_{index}", parameters, negate: false));
            }
        }

        return alternatives.Count == 0
            ? "\n    AND 1 = 0"
            : $"\n    AND ({string.Join(" OR ", alternatives)})";
    }

    internal static RefinerJob? Get(SqliteConnection connection, SqliteTransaction transaction, long jobId) =>
        Query(connection, transaction, $"SELECT {SelectColumns} FROM refiner_jobs WHERE id = @id", ("@id", jobId)).FirstOrDefault();

    internal static List<RefinerJob> Query(SqliteConnection connection, SqliteTransaction transaction, string sql, params (string Name, object? Value)[] parameters)
    {
        using var command = Command(connection, transaction, sql, parameters);
        using var reader = command.ExecuteReader();
        var rows = new List<RefinerJob>();
        while (reader.Read())
        {
            rows.Add(new RefinerJob(
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
                PythonTimestamps.Parse(reader.GetValue(14)) ?? DateTimeOffset.MinValue));
        }

        return rows;
    }

    internal static int Execute(SqliteConnection connection, SqliteTransaction transaction, string sql, params (string Name, object? Value)[] parameters)
    {
        using var command = Command(connection, transaction, sql, parameters);
        return command.ExecuteNonQuery();
    }

    internal static object? Scalar(SqliteConnection connection, SqliteTransaction transaction, string sql, params (string Name, object? Value)[] parameters)
    {
        using var command = Command(connection, transaction, sql, parameters);
        return command.ExecuteScalar();
    }

    private static string PrefixTest(string prefix, string name, List<(string Name, object? Value)> parameters, bool negate)
    {
        parameters.Add((name, prefix));
        return $"substr(job_kind, 1, {prefix.Length.ToString(CultureInfo.InvariantCulture)}) {(negate ? "<>" : "=")} {name}";
    }

    private static bool HoldsLease(RefinerJob? job, string leaseOwner, DateTimeOffset when) =>
        job is not null &&
        job.Status == RefinerJobStatus.Leased &&
        job.LeaseOwner == leaseOwner &&
        job.LeaseExpiresAt is { } expires &&
        expires >= when;

    private static RefinerJob? GetByDedupeKey(SqliteConnection connection, SqliteTransaction transaction, string dedupeKey) =>
        Query(connection, transaction, $"SELECT {SelectColumns} FROM refiner_jobs WHERE dedupe_key = @dedupe", ("@dedupe", dedupeKey)).FirstOrDefault();

    private static SqliteCommand Command(SqliteConnection connection, SqliteTransaction transaction, string sql, (string Name, object? Value)[] parameters)
    {
        var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        return command;
    }

    private void RecordQueueDepth(SqliteConnection connection, SqliteTransaction transaction)
    {
        if (ReferenceEquals(_metrics, NoJobQueueMetrics.Instance))
        {
            return;
        }

        var depth = Scalar(
            connection,
            transaction,
            "SELECT count(*) FROM refiner_jobs WHERE status = @pending OR status = @leased",
            ("@pending", RefinerJobStatus.Pending),
            ("@leased", RefinerJobStatus.Leased));
        _metrics.SetQueueDepth(MetricsModule, (int)Convert.ToInt64(depth, CultureInfo.InvariantCulture));
    }
}

/// <summary>Builds <see cref="WorkAdmission"/> from the database (the IO half of <c>evaluate_work_admission</c>).</summary>
public static class WorkAdmissionReader
{
    public static WorkAdmission Evaluate(SqliteConnection connection, SqliteTransaction transaction, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(connection);
        SuitePauseSettings? suite = null;
        using (var command = Command(connection, transaction,
                   "SELECT app_timezone, processing_paused, processing_paused_until, scan_while_paused FROM suite_settings WHERE id = 1"))
        using (var reader = command.ExecuteReader())
        {
            if (reader.Read())
            {
                suite = new SuitePauseSettings(
                    reader.IsDBNull(0) ? null : reader.GetString(0),
                    Bool(reader.GetValue(1)),
                    PythonTimestamps.Parse(reader.GetValue(2)) is { } until ? PyDateTime.FromUtc(until.UtcDateTime) : null,
                    Bool(reader.GetValue(3)));
            }
        }

        if (suite is null)
        {
            return WorkAdmissionRules.Evaluate(null, null, [], [], now);
        }

        RunnerBudget? budget = null;
        using (var command = Command(connection, transaction,
                   "SELECT runner_capacity, runner_cost_sd, runner_cost_720p, runner_cost_1080p, runner_cost_4k, runner_cost_undetermined " +
                   "FROM refiner_operator_settings WHERE id = 1"))
        using (var reader = command.ExecuteReader())
        {
            if (reader.Read())
            {
                budget = RunnerBudget.FromSettings(Long(reader.GetValue(0)), Long(reader.GetValue(1)), Long(reader.GetValue(2)),
                    Long(reader.GetValue(3)), Long(reader.GetValue(4)), Long(reader.GetValue(5)));
            }
        }

        var leased = new List<LeasedJobSnapshot>();
        using (var command = Command(connection, transaction, "SELECT runner_cost, payload_json FROM refiner_jobs WHERE status = 'leased'"))
        using (var reader = command.ExecuteReader())
        {
            while (reader.Read())
            {
                leased.Add(new LeasedJobSnapshot(Long(reader.GetValue(0)), reader.IsDBNull(1) ? null : reader.GetString(1)));
            }
        }

        var libraries = new List<LibraryAdmissionSnapshot>();
        using (var command = Command(connection, transaction,
                   "SELECT id, enabled, schedule_enabled, schedule_grid, schedule_hours_limited, schedule_days, schedule_start, " +
                   "schedule_end, max_concurrent_files FROM refiner_libraries ORDER BY id"))
        using (var reader = command.ExecuteReader())
        {
            while (reader.Read())
            {
                libraries.Add(new LibraryAdmissionSnapshot(
                    reader.GetInt64(0),
                    Bool(reader.GetValue(1)),
                    Bool(reader.GetValue(2)),
                    reader.IsDBNull(3) ? null : reader.GetString(3),
                    Bool(reader.GetValue(4)),
                    reader.IsDBNull(5) ? null : reader.GetString(5),
                    reader.IsDBNull(6) ? null : reader.GetString(6),
                    reader.IsDBNull(7) ? null : reader.GetString(7),
                    Long(reader.GetValue(8))));
            }
        }

        return WorkAdmissionRules.Evaluate(suite, budget, leased, libraries, now);
    }

    internal static bool Bool(object? value) => value switch
    {
        null or DBNull => false,
        long number => number != 0,
        string text => text.Trim() is not ("" or "0"),
        _ => Convert.ToInt64(value, CultureInfo.InvariantCulture) != 0,
    };

    internal static long Long(object? value) => value switch
    {
        null or DBNull => 0,
        long number => number,
        _ => Convert.ToInt64(value, CultureInfo.InvariantCulture),
    };

    private static SqliteCommand Command(SqliteConnection connection, SqliteTransaction transaction, string sql)
    {
        var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        return command;
    }
}
