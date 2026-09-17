namespace Weir.Core.Jobs;

/// <summary>
/// Immutable view passed to a job handler after a successful claim, outside the claim transaction
/// (port of <c>RefinerJobWorkContext</c>).
/// </summary>
public sealed record JobWorkContext(
    long Id,
    string JobKind,
    string? PayloadJson,
    string LeaseOwner,
    int AttemptCount = 1,
    int MaxAttempts = 1);

/// <summary>
/// Runs one job kind. Throw to fail the attempt (the worker retries or marks it failed and writes
/// the Activity entry); throw <see cref="AlreadyRecordedFailureException"/> when the handler has
/// already written its own Activity entry.
/// </summary>
/// <remarks>
/// The cancellation token fires only when Weir is shutting down. A handler that stops because of it
/// leaves its row leased, and startup recovery requeues it on the next start, exactly as when the
/// Python process is stopped mid-job.
/// </remarks>
public interface IJobHandler
{
    /// <summary>The <c>refiner.*</c> job kind this handler runs.</summary>
    string JobKind { get; }

    Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken);
}

/// <summary>
/// The job handlers this server can run, keyed by job kind.
/// </summary>
/// <remarks>
/// <para>
/// <b>Unported kinds are never claimed.</b> While the port is in progress (#514), the .NET server has
/// handlers for only some kinds. Python claims every eligible row and fails the ones it has no handler
/// for; doing that here would fail real work queued by, or meant for, the Python backend. So a .NET
/// worker only claims rows whose kind is registered here, plus rows no worker may ever run (retired or
/// unprefixed kinds), which it claims only to refuse with Python's exact wording. Every other row stays
/// <c>pending</c>, untouched, for a backend that can run it. When the last handler lands (#522, #523)
/// the registry covers every live kind and the behaviour is Python's again.
/// </para>
/// </remarks>
public sealed class JobHandlerRegistry
{
    private readonly Dictionary<string, IJobHandler> _handlers;

    public JobHandlerRegistry(IEnumerable<IJobHandler> handlers)
    {
        ArgumentNullException.ThrowIfNull(handlers);
        _handlers = new Dictionary<string, IJobHandler>(StringComparer.Ordinal);
        foreach (var handler in handlers)
        {
            if (!_handlers.TryAdd(handler.JobKind, handler))
            {
                throw new ArgumentException($"Two job handlers are registered for job_kind {JobKindGuard.PythonRepr(handler.JobKind)}.", nameof(handlers));
            }
        }

        JobKindGuard.ValidateHandlerRegistry(_handlers.Keys);
    }

    public static JobHandlerRegistry Empty { get; } = new([]);

    /// <summary>The registered kinds, in ordinal order.</summary>
    public IReadOnlyList<string> JobKinds => [.. _handlers.Keys.Order(StringComparer.Ordinal)];

    public bool Contains(string jobKind) => _handlers.ContainsKey(jobKind);

    public IJobHandler? Find(string jobKind) => _handlers.GetValueOrDefault(jobKind);
}

/// <summary>Timing rules shared by the periodic enqueue loops.</summary>
public static class PeriodicSchedule
{
    /// <summary>How long a periodic enqueuer waits after a failed tick before trying again.</summary>
    public static readonly TimeSpan FailureCooldown = TimeSpan.FromSeconds(2);

    /// <summary><c>_missed_due_run_count</c>: how many intervals elapsed after the next due time.</summary>
    public static int MissedDueRunCount(double nowSeconds, double nextRunSeconds, double intervalSeconds)
    {
        var interval = Math.Max(1.0, intervalSeconds);
        if (nowSeconds <= nextRunSeconds)
        {
            return 0;
        }

        return (int)Math.Floor((nowSeconds - nextRunSeconds) / interval);
    }

    /// <summary><c>_next_scheduler_sleep_seconds</c>: until the nearest due scope, capped by the polling cadence.</summary>
    public static double NextSchedulerSleepSeconds(double nowSeconds, double nextRunMovie, double nextRunTv, double pollSeconds)
    {
        var nextDue = Math.Min(nextRunMovie, nextRunTv);
        var untilDue = Math.Max(0.25, nextDue - nowSeconds);
        return Math.Max(0.25, Math.Min(pollSeconds, untilDue));
    }

    /// <summary><c>_watched_folder_scan_interval_seconds</c>: a library's scan cadence, 10 s .. 7 days.</summary>
    public static double WatchedFolderScanIntervalSeconds(long? scanIntervalSeconds) =>
        Math.Max(10.0, Math.Min(scanIntervalSeconds ?? 300, 7 * 24 * 3600));
}
