namespace Weir.Core.Jobs;

/// <summary>
/// Values persisted in <c>jobs.status</c> (port of <c>weir.processing.jobs_model.ProcessingJobStatus</c>).
/// </summary>
/// <remarks>
/// <see cref="Failed"/> means the handler (or the refusal path) failed or exhausted its attempts.
/// <see cref="HandlerOkFinalizeFailed"/> means the handler ran without error but recording
/// <see cref="Completed"/> failed; it is not re-runnable. <see cref="Cancelled"/> means the operator
/// removed a still-pending row before a worker claimed it.
/// </remarks>
public static class ProcessingJobStatus
{
    public const string Pending = "pending";
    public const string Leased = "leased";
    public const string Completed = "completed";
    public const string Failed = "failed";
    public const string HandlerOkFinalizeFailed = "handler_ok_finalize_failed";
    public const string Cancelled = "cancelled";

    /// <summary>Statuses the job-row retention prune deletes once old enough.</summary>
    public static readonly IReadOnlyList<string> Terminal = [Completed, Failed, HandlerOkFinalizeFailed, Cancelled];
}

/// <summary>One <c>jobs</c> row as read from the database.</summary>
public sealed record ProcessingJob(
    long Id,
    string DedupeKey,
    string JobKind,
    string? PayloadJson,
    string Status,
    string? LeaseOwner,
    DateTimeOffset? LeaseExpiresAt,
    int AttemptCount,
    int MaxAttempts,
    string? LastError,
    DateTimeOffset? NotBefore,
    int RunnerCost,
    int Priority,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

/// <summary>What an operator action on one job row came to (Python's <c>"ok" | "not_found" | "wrong_status"</c>).</summary>
public enum JobActionOutcome
{
    Ok,
    NotFound,
    WrongStatus,
}
