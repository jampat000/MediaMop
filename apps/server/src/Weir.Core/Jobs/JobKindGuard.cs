using Weir.Core.Json;

namespace Weir.Core.Jobs;

/// <summary>
/// Which <c>job_kind</c> strings may sit in <c>refiner_jobs</c> and be run by its workers
/// (port of <c>weir.refiner.job_kind_guard</c>).
/// </summary>
/// <remarks>
/// Every durable job is a <c>refiner.*</c> kind. Retired prefixes are listed by name so a queue row
/// left by an older install is refused instead of being claimed by a worker that no longer knows
/// what it is. Matching is ordinal and case-sensitive, like Python's <c>str.startswith</c>.
/// </remarks>
public static class JobKindGuard
{
    public const string JobKindPrefix = "refiner.";

    /// <summary>Trimmer was removed long ago; its rows are refused.</summary>
    public const string RetiredTrimmerPrefix = "trimmer.";

    /// <summary>Subber moved to Deluno.</summary>
    public const string RetiredSubberPrefix = "subber.";

    /// <summary>Pruner moved to Deluno too (#473).</summary>
    public const string RetiredPrunerPrefix = "pruner.";

    /// <summary>Refiner's supplied-payload evaluation family, removed in #339.</summary>
    public const string RetiredSuppliedPayloadEvaluationPrefix = "refiner.supplied_payload_evaluation.";

    /// <summary>Refiner's candidate gate, reshaped into a synchronous endpoint in #339.</summary>
    public const string RetiredCandidateGatePrefix = "refiner.candidate_gate.";

    public static readonly IReadOnlyList<string> RetiredPrefixes =
    [
        RetiredTrimmerPrefix,
        RetiredSubberPrefix,
        RetiredPrunerPrefix,
        RetiredSuppliedPayloadEvaluationPrefix,
        RetiredCandidateGatePrefix,
    ];

    /// <summary><c>job_kind_is_retired</c>: the kind belongs to a retired family and must never run.</summary>
    public static bool IsRetired(string jobKind)
    {
        ArgumentNullException.ThrowIfNull(jobKind);
        return RetiredPrefixes.Any(prefix => jobKind.StartsWith(prefix, StringComparison.Ordinal));
    }

    public static bool HasRefinerPrefix(string jobKind)
    {
        ArgumentNullException.ThrowIfNull(jobKind);
        return jobKind.StartsWith(JobKindPrefix, StringComparison.Ordinal);
    }

    /// <summary>
    /// A kind no worker may run: retired, or missing the <c>refiner.</c> prefix. Workers claim these
    /// only to refuse them, exactly as the Python worker does.
    /// </summary>
    public static bool IsRefused(string jobKind) => IsRetired(jobKind) || !HasRefinerPrefix(jobKind);

    /// <summary><c>validate_refiner_enqueue_job_kind</c>: queue rows must be live <c>refiner.*</c> kinds.</summary>
    /// <exception cref="ArgumentException">The kind is retired or not a <c>refiner.*</c> kind.</exception>
    public static void ValidateEnqueueJobKind(string jobKind)
    {
        ArgumentNullException.ThrowIfNull(jobKind);
        if (IsRetired(jobKind))
        {
            throw new ArgumentException(
                $"refiner_enqueue_or_get_job refuses a retired job_kind (got {PyStrings.Repr(jobKind)})");
        }

        if (!HasRefinerPrefix(jobKind))
        {
            throw new ArgumentException(
                $"refiner_enqueue_or_get_job requires job_kind to start with {PyStrings.Repr(JobKindPrefix)} (got {PyStrings.Repr(jobKind)})");
        }
    }

    /// <summary><c>validate_refiner_worker_handler_registry</c>: handlers only for live <c>refiner.*</c> kinds.</summary>
    /// <exception cref="ArgumentException">A key is retired or not a <c>refiner.*</c> kind.</exception>
    public static void ValidateHandlerRegistry(IEnumerable<string> jobKinds)
    {
        ArgumentNullException.ThrowIfNull(jobKinds);
        var bad = jobKinds.Where(IsRefused).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToList();
        if (bad.Count > 0)
        {
            throw new ArgumentException(
                "Worker handler registry keys must start with " +
                $"{PyStrings.Repr(JobKindPrefix)} and must not use a retired prefix (offending keys: [{string.Join(", ", bad.Select(PyStrings.Repr))}])");
        }
    }
}
