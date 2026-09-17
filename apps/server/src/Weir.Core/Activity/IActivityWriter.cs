namespace Weir.Core.Activity;

/// <summary>One Activity entry to write (the arguments of Python's <c>record_activity_event</c>).</summary>
public sealed record ActivityEventDraft(string EventType, string Module, string Title, string? Detail);

/// <summary>
/// Appends Activity entries in their own transaction. Writers that already hold a transaction
/// (sign-in, the job queue's claim) use the SQLite writer's in-transaction overloads instead. Every
/// write tells the live Activity stream after its transaction commits.
/// </summary>
public interface IActivityWriter
{
    /// <summary>Append one event in its own transaction and return its id.</summary>
    Task<long> RecordAsync(ActivityEventDraft draft, CancellationToken cancellationToken = default);
}
