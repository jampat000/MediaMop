using System.Globalization;

namespace Weir.Core.Jobs;

/// <summary>The pure rules behind <c>weir.refiner.jobs_ops</c>: retry backoff, dedupe tombstones and audit wording.</summary>
public static class JobQueueRules
{
    public const int DedupeKeyMaxLength = 512;

    /// <summary>Terminal error text is bounded to this many characters.</summary>
    public const int LastErrorLimit = 10_000;

    public const int DefaultMaxAttempts = 3;

    /// <summary>What an operator cancel writes to <c>last_error</c>.</summary>
    public const string CancelledByOperatorError = "Cancelled by operator before a worker claimed this job.";

    /// <summary>
    /// Seconds before a failed attempt may be claimed again: <c>min(30 * 2 ** (attempt_count - 1), 1800)</c>.
    /// </summary>
    /// <remarks>
    /// Python raises on a negative exponent only through float maths it never reaches (the claim has
    /// already incremented <c>attempt_count</c> to at least one); a zero or negative count yields 15 s
    /// and less there, which is reproduced exactly.
    /// </remarks>
    public static double RetryBackoffSeconds(int attemptCount)
    {
        var exponent = attemptCount - 1;
        if (exponent >= 6)
        {
            return 1800;
        }

        return Math.Min(30 * Math.Pow(2, exponent), 1800);
    }

    /// <summary><c>_tombstone_cancelled_dedupe_key</c>: frees the original key for a new enqueue.</summary>
    public static string TombstoneCancelledDedupeKey(string original, long jobId)
    {
        var suffix = $":cancelled:{jobId.ToString(CultureInfo.InvariantCulture)}";
        var text = original ?? string.Empty;
        var keep = Math.Max(0, DedupeKeyMaxLength - suffix.Length);
        var baseText = OperatorFailures.PythonSlice(text, keep);
        return OperatorFailures.PythonSlice(baseText + suffix, DedupeKeyMaxLength);
    }

    /// <summary>The <c>last_error</c> that <c>recover_handler_ok_finalize_failed_to_completed</c> writes.</summary>
    public static string RecoveredFinalizeFailureError(string? previousError, DateTimeOffset when, string recoveredByLabel)
    {
        var previous = (previousError ?? string.Empty).Trim();
        var iso = PythonIsoFormat(when, 'T').Replace("+00:00", "Z", StringComparison.Ordinal);
        var note =
            $"manual_recover_finalize_failure: marked completed at {iso} by {recoveredByLabel} " +
            "(handler was not re-run; row was handler_ok_finalize_failed).";
        var text = previous.Length > 0 ? $"{previous}\n--- {note}" : note;
        return OperatorFailures.PythonSlice(text, LastErrorLimit);
    }

    /// <summary>
    /// Python's <c>datetime.isoformat(sep)</c> for an aware value: microseconds only when non-zero,
    /// then the UTC offset as <c>+HH:MM</c>.
    /// </summary>
    public static string PythonIsoFormat(DateTimeOffset value, char separator)
    {
        var microseconds = (value.Ticks % TimeSpan.TicksPerSecond) / 10;
        var text = value.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) + separator +
                   value.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
        if (microseconds != 0)
        {
            text += "." + microseconds.ToString("D6", CultureInfo.InvariantCulture);
        }

        var offset = value.Offset;
        var sign = offset < TimeSpan.Zero ? '-' : '+';
        var absolute = offset.Duration();
        return text + sign + absolute.Hours.ToString("D2", CultureInfo.InvariantCulture) + ":" +
               absolute.Minutes.ToString("D2", CultureInfo.InvariantCulture);
    }

    /// <summary>Truncate to whole microseconds, the resolution Python and the database keep.</summary>
    public static DateTimeOffset ToMicroseconds(DateTimeOffset value) =>
        new(value.Ticks - (value.Ticks % 10), value.Offset);
}

/// <summary>What startup recovery did (port of <c>StartupJobRecoveryResult</c>).</summary>
public sealed record StartupJobRecoveryResult(int RefinerRequeued, int RefinerFailed)
{
    public int TotalRecovered => RefinerRequeued + RefinerFailed;
}

/// <summary>The status and error a leased row gets when a restart finds it (port of <c>_recover_table</c>).</summary>
public sealed record StartupRecoveryDecision(string Status, string LastError, bool Requeued);

/// <summary>Pure rules of <c>recover_incomplete_jobs_after_startup</c>.</summary>
public static class StartupJobRecovery
{
    public const string ModuleName = "Refiner";

    /// <summary>
    /// A leased row at startup belongs to a dead worker: requeue it when attempts remain, or mark it
    /// failed when the lease already consumed the final attempt.
    /// </summary>
    public static StartupRecoveryDecision Decide(int attemptCount, int maxAttempts, DateTimeOffset now)
    {
        var attempts = attemptCount;
        var max = Math.Max(1, maxAttempts);
        var iso = JobQueueRules.PythonIsoFormat(now, 'T');
        return attempts >= max
            ? new StartupRecoveryDecision(
                RefinerJobStatus.Failed,
                $"{ModuleName} job was interrupted by a Weir restart after its final attempt. " +
                $"Recovered at {iso} and marked failed so the operator can inspect it.",
                Requeued: false)
            : new StartupRecoveryDecision(
                RefinerJobStatus.Pending,
                $"{ModuleName} job was interrupted by a Weir restart. " +
                $"Recovered at {iso} and queued for another safe attempt.",
                Requeued: true);
    }
}
