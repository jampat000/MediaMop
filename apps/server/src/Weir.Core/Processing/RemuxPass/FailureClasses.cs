using System.Globalization;
using Weir.Core.Json;

namespace Weir.Core.Processing.RemuxPass;

/// <summary>
/// Why a file failed, in the terms a retry policy can act on (port of <c>processing_failure_classes.py</c>).
/// </summary>
public static class ProcessingFailureClasses
{
    /// <summary>Rejected before any work started. Retrying reaches the same conclusion.</summary>
    public const string Preflight = "preflight";

    /// <summary>Work started and the process failed. Retrying is reasonable.</summary>
    public const string Execution = "execution";

    /// <summary>A guardrail deliberately stopped the file. Never retried automatically.</summary>
    public const string Guardrail = "guardrail";

    /// <summary>Something Weir could not attribute. Terminal.</summary>
    public const string Unknown = "unknown";

    /// <summary><c>classify_failure</c>: a pass outcome onto the retry vocabulary.</summary>
    public static string Classify(string? outcome) => PyStrings.Strip(outcome ?? string.Empty).ToLowerInvariant() switch
    {
        RemuxPassOutcomes.FailedBeforeExecution => Preflight,
        RemuxPassOutcomes.FailedDuringExecution => Execution,
        RemuxPassOutcomes.SkippedGuardrail => Guardrail,
        _ => Unknown,
    };

    /// <summary><c>is_retryable</c>: guardrail and unknown never are.</summary>
    public static bool IsRetryable(string failureClass, bool retryPreflightFailures, bool retryExecutionFailures)
    {
        var value = PyStrings.Strip(failureClass ?? string.Empty).ToLowerInvariant();
        return value switch
        {
            Preflight => retryPreflightFailures,
            Execution => retryExecutionFailures,
            _ => false,
        };
    }

    /// <summary><c>backoff_seconds_for_attempt</c>: doubling from the base, capped at an hour.</summary>
    public static long BackoffSecondsForAttempt(long attempt, long baseSeconds)
    {
        var @base = Math.Max(1, baseSeconds);
        var exponent = Math.Max(0, attempt - 1);
        if (exponent >= 16)
        {
            return 3600;
        }

        return Math.Min(3600, @base * (1L << (int)exponent));
    }
}

/// <summary>Whether this failure will be retried, and the sentence explaining it (<c>RetryDecision</c>).</summary>
public sealed record RetryDecision(bool WillRetry, DateTimeOffset? NextRetryAt, string Reason, bool Quarantined = false);

/// <summary>The automatic half of <c>processing_requeue_service.py</c>: the library's retry policy applied to one failure.</summary>
public static class RetryPolicy
{
    /// <summary><c>PROCESSING_QUARANTINE_AFTER_FAILURES</c>.</summary>
    public const int QuarantineAfterFailures = 3;

    /// <summary><c>decide_retry</c>.</summary>
    public static RetryDecision DecideRetry(ProcessingLibraryRecord library, string failureClass, long attemptsSoFar, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(library);
        var value = PyStrings.Strip(failureClass ?? string.Empty).ToLowerInvariant();
        if (!ProcessingFailureClasses.IsRetryable(value, library.RetryPreflightFailures, library.RetryExecutionFailures))
        {
            return new RetryDecision(false, null, NotRetryableReason(value, library));
        }

        var maxAttempts = Math.Max(1, library.MaxAttempts);
        if (attemptsSoFar >= maxAttempts)
        {
            return new RetryDecision(
                false,
                null,
                $"Weir tried this file {attemptsSoFar.ToString(CultureInfo.InvariantCulture)} times and stopped, because the {library.Name} " +
                $"library allows {maxAttempts.ToString(CultureInfo.InvariantCulture)}. You can still start it again by hand.");
        }

        // Indexed by failures so far, not by the attempt about to happen.
        var delay = ProcessingFailureClasses.BackoffSecondsForAttempt(attemptsSoFar, library.RetryBackoffSeconds);
        var minutes = delay / 60;
        return new RetryDecision(
            true,
            now + TimeSpan.FromSeconds(delay),
            $"This failed and Weir will try again in about {(minutes == 0 ? 1 : minutes).ToString(CultureInfo.InvariantCulture)} minute(s) " +
            $"(attempt {(attemptsSoFar + 1).ToString(CultureInfo.InvariantCulture)} of {maxAttempts.ToString(CultureInfo.InvariantCulture)}).");
    }

    /// <summary>
    /// The part of <c>record_failure</c> after the row is found: the decision, with a quarantine after repeated failures of
    /// the same class.
    /// </summary>
    public static RetryDecision DecideForRecordedFailure(ProcessingLibraryRecord library, string failureClass, long previousAttempts, string? previousFailureClass, DateTimeOffset now)
    {
        var value = PyStrings.Strip(failureClass ?? string.Empty).ToLowerInvariant();
        var attempts = previousAttempts + 1;
        var decision = DecideRetry(library, value, attempts, now);
        var consecutive = previousFailureClass == value ? attempts : 1;
        if (consecutive >= QuarantineAfterFailures)
        {
            decision = new RetryDecision(
                false,
                null,
                $"Weir held this file after {consecutive.ToString(CultureInfo.InvariantCulture)} repeated {value} failures. " +
                "Review the failure detail and use Start again after fixing the cause.",
                Quarantined: true);
        }

        return decision;
    }

    private static string NotRetryableReason(string failureClass, ProcessingLibraryRecord library) => failureClass switch
    {
        ProcessingFailureClasses.Preflight =>
            "This file was rejected before any work started, so trying again would reach the same " +
            "conclusion. Fix what the reason describes, then start it again by hand.",
        ProcessingFailureClasses.Guardrail =>
            "A safety check stopped this file. Weir does not retry those automatically — the check " +
            "is the answer, not something to get past.",
        ProcessingFailureClasses.Execution =>
            $"This failed while being processed, and the {library.Name} library is set not to retry those. " +
            "You can start it again by hand.",
        _ => "Weir could not work out why this failed, so it is not retrying automatically. You can start it again by hand.",
    };
}
