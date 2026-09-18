using Weir.Core.Time;

namespace Weir.Core.Processing;

/// <summary>
/// The vocabulary an operator sees on the Files screen (<c>ProcessingFileStatus</c>).
/// Fixes #530: <see cref="PassedThrough"/> and <see cref="Rejected"/> are valid statuses in both
/// responses and filters, matching the Python enum in full — the earlier response/query schema
/// omitted them, which turned a file in either state into a 500 on read and a 422 on filter.
/// </summary>
public static class ProcessingFileStatuses
{
    public const string Unprocessed = "unprocessed";
    public const string Processing = "processing";
    public const string Processed = "processed";
    public const string ProcessingFailed = "processing_failed";
    public const string Skipped = "skipped";
    public const string Disabled = "disabled";
    public const string OnHold = "on_hold";
    public const string OutOfSchedule = "out_of_schedule";
    public const string BlockedUpstream = "blocked_upstream";

    /// <summary>Terminal, and deliberately distinct from <see cref="Processed"/>: Weir handed the original
    /// back unmodified rather than keep it (#465).</summary>
    public const string PassedThrough = "passed_through";

    /// <summary>Terminal: under the opt-in <c>reject</c> policy, the manager accepted that the release is bad.</summary>
    public const string Rejected = "rejected";

    /// <summary>Every persisted status value, in the same order as the Python <c>StrEnum</c>.</summary>
    public static readonly IReadOnlyList<string> All =
    [
        Unprocessed, Processing, Processed, ProcessingFailed, Skipped, Disabled, OnHold,
        OutOfSchedule, BlockedUpstream, PassedThrough, Rejected,
    ];

    /// <summary>States where Weir has decided not to act, as opposed to not having acted yet.</summary>
    public static readonly IReadOnlySet<string> Withheld = new HashSet<string>(StringComparer.Ordinal)
    {
        Disabled, OnHold, OutOfSchedule, BlockedUpstream, Skipped,
    };
}

/// <summary>One <c>files</c> row.</summary>
public sealed record ProcessingFileRecord
{
    public long Id { get; init; }
    public long LibraryId { get; init; }
    public required string RelativePath { get; init; }

    public string Status { get; init; } = ProcessingFileStatuses.Unprocessed;
    public string StatusReason { get; init; } = string.Empty;
    public string? BlockedByConnection { get; init; }

    public long SizeBytes { get; init; }
    public long? VideoWidth { get; init; }
    public long? VideoHeight { get; init; }
    public string? VideoCodec { get; init; }
    public long? AudioTrackCount { get; init; }
    public long? SubtitleTrackCount { get; init; }
    public double? DurationSeconds { get; init; }
    public string? AudioCodecs { get; init; }
    public long? VideoBitDepth { get; init; }
    public PyDateTime? SizeChangedAt { get; init; }
    public PyDateTime? HoldUntil { get; init; }
    public string? FailureClass { get; init; }
    public long FailureAttempts { get; init; }
    public PyDateTime? NextRetryAt { get; init; }

    public string? OutputCollisionPolicy { get; init; }
    public string? OutputCollisionAction { get; init; }
    public string? OutputCollisionReason { get; init; }

    public string? HardwareMethod { get; init; }
    public bool HardwareFellBackToSoftware { get; init; }
    public string? HardwareReason { get; init; }

    public PyDateTime? LastSeenAt { get; init; }
    public PyDateTime? LastAttemptAt { get; init; }

    public PyDateTime CreatedAt { get; init; }
    public PyDateTime UpdatedAt { get; init; }
}

/// <summary>Filters for <c>list_files</c>.</summary>
public sealed record ProcessingFileListFilter
{
    public long? LibraryId { get; init; }
    public string? Status { get; init; }
    public string? PathContains { get; init; }
    public PyDateTime? Since { get; init; }
    public int Limit { get; init; } = 200;

    /// <summary><c>max(1, min(limit, 1000))</c>.</summary>
    public int ClampedLimit => Math.Max(1, Math.Min(Limit, 1000));
}
