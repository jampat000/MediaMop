namespace Weir.Core.Activity;

/// <summary>One Activity entry to write (the arguments of Python's <c>record_activity_event</c>).</summary>
public sealed record ActivityEventDraft(string EventType, string Module, string Title, string? Detail);

/// <summary>
/// Writes Activity entries. Deliberately small: the job queue only appends events. The Activity port
/// (#519) owns reading, streaming and live notification, and can replace the implementation.
/// </summary>
public interface IActivityWriter
{
    /// <summary>Append one event in its own transaction and return its id.</summary>
    Task<long> RecordAsync(ActivityEventDraft draft, CancellationToken cancellationToken = default);
}

/// <summary>Activity event types the job queue writes (<c>weir.platform.activity.constants</c>).</summary>
public static class ActivityEventTypes
{
    public const string RefinerWorkerFailure = "refiner.worker_failure";
    public const string RefinerFailureCleanupSweepCompleted = "refiner.failure_cleanup_sweep_completed";
}
