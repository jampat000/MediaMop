using Weir.Core.Json;
using Weir.Core.Observability;

namespace Weir.Core.Jobs;

/// <summary>
/// The handler already wrote this failure to Activity; the worker still fails the job but does not
/// write a second entry (port of <c>AlreadyRecordedFailure</c>, #488).
/// </summary>
public sealed class AlreadyRecordedFailureException : Exception
{
    /// <summary>The Python class name, which appears in the stored technical detail.</summary>
    public const string PythonTypeName = "AlreadyRecordedFailure";

    public AlreadyRecordedFailureException()
    {
    }

    public AlreadyRecordedFailureException(string message)
        : base(message)
    {
    }

    public AlreadyRecordedFailureException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// What a worker says when a job fails (port of <c>weir.platform.jobs.worker_failures</c>, #488).
/// </summary>
/// <remarks>
/// The words match what happens next: a failed attempt is put back in the queue until it has used
/// its attempts, so "marked failed" is only said when it is true. Queue kinds and raw exception text
/// go in the technical part of <c>last_error</c>, after the sentence a person reads.
/// </remarks>
public static class WorkerFailures
{
    public const int ErrorLimit = 10_000;

    public const string WillRetryContinuation = "Weir will try this job again shortly.";
    public const string MarkedFailedContinuation = "This job is marked failed so it does not look successful.";

    /// <summary><c>retry_coming</c>: another attempt follows this one.</summary>
    public static bool RetryComing(int attemptCount, int maxAttempts) => attemptCount < maxAttempts;

    /// <summary><c>job_failure</c>.</summary>
    public static OperatorFailure JobFailure(string module, FailureSubject cause, bool willRetry) =>
        FailureMessages.FromException(
            module,
            "job",
            cause,
            continuation: willRetry ? WillRetryContinuation : MarkedFailedContinuation);

    /// <summary><c>stored_error</c>: the sentence a person reads first, then what to do, then the technical detail.</summary>
    public static string StoredError(OperatorFailure failure)
    {
        ArgumentNullException.ThrowIfNull(failure);
        var text = failure.Message;
        if (!string.IsNullOrEmpty(failure.NextAction))
        {
            text += $" Next action: {failure.NextAction}";
        }

        if (!string.IsNullOrEmpty(failure.TechnicalDetail))
        {
            text += $" Technical detail: {failure.TechnicalDetail}";
        }

        return PyStrings.Slice(text, ErrorLimit);
    }

    /// <summary><c>refused_job_error</c>: a job this worker cannot run.</summary>
    public static string RefusedJobError(string module, string technicalReason, bool willRetry) =>
        StoredError(JobFailure(module, FailureMessages.RuntimeError(technicalReason), willRetry));

    /// <summary>The worker's refusal of a retired kind, worded as <c>process_one_refiner_job</c> words it.</summary>
    public static string RetiredKindReason(string jobKind, long jobId) =>
        "refiner worker refused a retired job_kind: " +
        $"{PyStrings.Repr(jobKind)} (row id={jobId}); nothing runs this kind any more";

    /// <summary>The worker's refusal of a kind without the <c>refiner.</c> prefix.</summary>
    public static string UnprefixedKindReason(string jobKind, long jobId) =>
        "refiner worker refused job_kind missing required refiner.* prefix: " +
        $"{PyStrings.Repr(jobKind)} (row id={jobId}); enqueue only refiner-owned kinds";

    /// <summary><c>RefinerNoHandlerForJobKind</c> as a failure cause.</summary>
    public static FailureSubject NoHandler(string jobKind) =>
        new("RefinerNoHandlerForJobKind", $"no Refiner job handler registered for job_kind={PyStrings.Repr(jobKind)}", ExceptionCategory.Other);
}
