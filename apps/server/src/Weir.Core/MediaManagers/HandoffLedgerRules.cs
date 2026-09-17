using Weir.Core.Json;
using Weir.Core.Time;

namespace Weir.Core.MediaManagers;

/// <summary>What Weir tells a manager about one hand-off (<c>HandoffStatus</c>).</summary>
public sealed record HandoffStatus(
    string HandoffId,
    string State,
    DateTimeOffset LastChangedAt,
    long? QueuePosition = null,
    DateTimeOffset? ScheduledFor = null,
    string? OutputPath = null,
    string? Message = null)
{
    /// <summary><c>as_json</c>: timestamps in UTC with a <c>Z</c>.</summary>
    public PyDict AsJson() => new PyDict()
        .Set("handoffId", HandoffId)
        .Set("state", State)
        .Set("queuePosition", QueuePosition)
        .Set("scheduledFor", Iso(ScheduledFor))
        .Set("lastChangedUtc", Iso(LastChangedAt))
        .Set("outputPath", OutputPath)
        .Set("message", Message);

    private static string? Iso(DateTimeOffset? value) =>
        value is { } stamp ? PyDateTime.FromDateTimeOffset(stamp.ToUniversalTime()).IsoFormat().Replace("+00:00", "Z", StringComparison.Ordinal) : null;
}

/// <summary>The hand-off vocabulary agreed with Deluno and how a file's state maps onto it (port of <c>handoff_ledger</c>).</summary>
public static class HandoffLedgerRules
{
    public const string Queued = "queued";
    public const string Scheduled = "scheduled";
    public const string Working = "working";
    public const string Completed = "completed";
    public const string PassedThrough = "passed-through";
    public const string Failed = "failed";
    public const string Rejected = "rejected";
    public const string Cancelled = "cancelled";

    /// <summary><c>TERMINAL_STATES</c>.</summary>
    public static readonly IReadOnlySet<string> TerminalStates = new SortedSet<string>(StringComparer.Ordinal)
    {
        Completed, PassedThrough, Failed, Rejected, Cancelled,
    };

    /// <summary><c>LEDGER_RETENTION_DAYS</c>.</summary>
    public const int RetentionDays = 90;

    public const string CancelledMessage = "The media manager cancelled this hand-off before Weir started on it.";

    /// <summary>After this many consecutive failures a file is held for a person (<c>REFINER_QUARANTINE_AFTER_FAILURES</c>).</summary>
    public const int QuarantineAfterFailures = 3;

    /// <summary>
    /// <c>_file_state</c>: one file's state in the manager's words, and when it would next run if known.
    /// </summary>
    /// <remarks>
    /// Deliberate fix (#531): a failed file with a retry still owed reads <c>scheduled</c> until that retry is
    /// queued, including between the backoff ending and the next watched-folder scan. Python reported
    /// <c>failed</c> in that window, which a manager takes as final. A retry is owed exactly when the failure
    /// recorded a <c>next_retry_at</c>; <c>failed</c> means no retry remains.
    /// </remarks>
    public static (string State, DateTimeOffset? When) FileState(string status, DateTimeOffset? nextRetryAt, long failureAttempts)
    {
        return status switch
        {
            "processing" => (Working, null),
            "processed" => (Completed, null),
            "passed_through" => (PassedThrough, null),
            "rejected" => (Rejected, null),
            "processing_failed" => nextRetryAt is { } retryAt ? (Scheduled, retryAt) : (Failed, null),
            "skipped" => (Failed, null),
            "out_of_schedule" => (Scheduled, null),
            "on_hold" when failureAttempts >= QuarantineAfterFailures => (Failed, null),
            _ => (Queued, null),
        };
    }

    /// <summary><c>_combine</c>: a hand-off covering several files is as far along as its least finished file.</summary>
    public static string Combine(IReadOnlyCollection<string> states)
    {
        ArgumentNullException.ThrowIfNull(states);
        foreach (var waiting in new[] { Working, Queued, Scheduled })
        {
            if (states.Contains(waiting))
            {
                return waiting;
            }
        }

        foreach (var outcome in new[] { Failed, Rejected, PassedThrough })
        {
            if (states.Contains(outcome))
            {
                return outcome;
            }
        }

        return Completed;
    }
}
