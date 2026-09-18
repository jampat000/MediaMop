using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Processing;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>
/// Seam: what happens once Weir gives up processing a file (<c>apply_failure_policy</c> and <c>reject_bad_release</c> in
/// <c>processing_pass_through.py</c>). Both run inside the caller's unit of work and may only queue follow-up work; the copy,
/// the report and any deletion belong to the pass-through and reject handlers.
/// </summary>
public interface IFailurePolicy
{
    /// <summary>
    /// <c>reject_bad_release</c>: under <c>reject</c>, queue a reject for a file whose content was found unusable. True when
    /// one was queued.
    /// </summary>
    Task<bool> RejectBadReleaseAsync(UnitOfWork uow, ProcessingLibraryRecord library, string relativePath, string reason, PyDict? origin);

    /// <summary>
    /// <c>apply_failure_policy</c>: act on a recorded failure once no retry is coming. Returns the follow-up queued,
    /// <c>pass_through</c> or <c>reject</c>, or null.
    /// </summary>
    Task<string?> ApplyFailurePolicyAsync(UnitOfWork uow, ProcessingLibraryRecord library, string relativePath, bool willRetry, PyDict? origin, bool badRelease);
}

/// <summary>
/// The reference's policy (the default): <c>hold</c> does nothing, a content rejection under <c>reject</c> queues
/// <c>processing.file.reject.v1</c>, and anything else queues <c>processing.file.pass_through.v1</c>, each carrying the hand-off
/// origin. The handlers for those two kinds (<see cref="ProcessingRejectHandler"/>, <see cref="ProcessingPassThroughHandler"/>)
/// are registered by <c>AddWeirProcessingFailureFollowUps</c> (#522 part 4).
/// </summary>
public sealed class QueueingFailurePolicy : IFailurePolicy
{
    public const string PassThroughJobKind = IntakeRules.PassThroughJobKind;
    public const string RejectJobKind = IntakeRules.RejectJobKind;

    private readonly ProcessingJobStore _jobs;

    public QueueingFailurePolicy(ProcessingJobStore jobs)
    {
        _jobs = jobs ?? throw new ArgumentNullException(nameof(jobs));
    }

    public Task<bool> RejectBadReleaseAsync(UnitOfWork uow, ProcessingLibraryRecord library, string relativePath, string reason, PyDict? origin)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(library);
        if (ProcessingFailurePolicies.Normalize(library.FailurePolicy) != ProcessingFailurePolicies.Reject)
        {
            return Task.FromResult(false);
        }

        var body = Body(library, relativePath, origin);
        if (reason.Length > 0)
        {
            body.Set("reason", PyStrings.Slice(reason, 1200));
        }

        body.Set("failure_class", "preflight");
        Enqueue(uow, $"{RejectJobKind}:{library.Id}:{relativePath}:{FingerprintTag(library, relativePath)}", RejectJobKind, body, library);
        return Task.FromResult(true);
    }

    public async Task<string?> ApplyFailurePolicyAsync(UnitOfWork uow, ProcessingLibraryRecord library, string relativePath, bool willRetry, PyDict? origin, bool badRelease)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(library);
        if (willRetry)
        {
            return null;
        }

        var policy = ProcessingFailurePolicies.Normalize(library.FailurePolicy);
        if (policy == ProcessingFailurePolicies.Hold)
        {
            return null;
        }

        var currentReason = await RemuxPassFileState.StatusReasonAsync(uow, library.Id, relativePath).ConfigureAwait(false);
        if (badRelease && await RejectBadReleaseAsync(uow, library, relativePath, currentReason ?? "Weir could not read this file's contents.", origin).ConfigureAwait(false))
        {
            await RemuxPassFileState.AppendStatusReasonAsync(uow, library.Id, relativePath,
                "Weir is telling your media manager this release is bad so it can find a different one.").ConfigureAwait(false);
            return ProcessingFailurePolicies.Reject;
        }

        // Any other failure is not evidence the release is bad, so under reject it is handed back like pass_through.
        Enqueue(uow, $"{PassThroughJobKind}:{library.Id}:{relativePath}:{FingerprintTag(library, relativePath)}", PassThroughJobKind, Body(library, relativePath, origin), library);
        await RemuxPassFileState.AppendStatusReasonAsync(uow, library.Id, relativePath,
            "Weir could not process this file, so it is handing the original back to the output folder unchanged.").ConfigureAwait(false);
        return ProcessingFailurePolicies.PassThrough;
    }

    private static PyDict Body(ProcessingLibraryRecord library, string relativePath, PyDict? origin)
    {
        var body = new PyDict().Set("relative_media_path", relativePath).Set("library_id", library.Id).Set("trigger", "worker");
        if (origin is { IsTruthy: true })
        {
            body.Set("origin", origin);
        }

        return body;
    }

    private void Enqueue(UnitOfWork uow, string dedupeKey, string jobKind, PyDict body, ProcessingLibraryRecord library) =>
        _jobs.EnqueueOrGet(
            uow.Connection,
            uow.WriteTransaction(),
            dedupeKey,
            jobKind,
            PyJsonWriter.Dumps(body, PyJsonFormat.Compact),
            JobQueueRules.DefaultMaxAttempts,
            0,
            (int)Math.Clamp(library.Priority, int.MinValue, int.MaxValue));

    /// <summary>
    /// Issue #545 item 2: the source's own fingerprint, folded into the dedupe key so a later failure of a since-replaced
    /// file (same relative path, different content) queues a fresh pass-through or reject instead of being absorbed by a
    /// row still sitting under the old key — while a repeat enqueue for the very same, unchanged file still dedupes.
    /// </summary>
    internal static string FingerprintTag(ProcessingLibraryRecord library, string relativePath)
    {
        try
        {
            var absolute = RemuxPassPaths.Resolve(Path.Combine(library.WatchedFolder, relativePath));
            return SourceFiles.DedupeFingerprintTag(absolute);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException or System.Security.SecurityException)
        {
            return "unreadable";
        }
    }
}

/// <summary>A policy that never queues a follow-up: every failure is left held where it is. For tests and diagnostics.</summary>
public sealed class HoldingFailurePolicy : IFailurePolicy
{
    public Task<bool> RejectBadReleaseAsync(UnitOfWork uow, ProcessingLibraryRecord library, string relativePath, string reason, PyDict? origin) =>
        Task.FromResult(false);

    public Task<string?> ApplyFailurePolicyAsync(UnitOfWork uow, ProcessingLibraryRecord library, string relativePath, bool willRetry, PyDict? origin, bool badRelease) =>
        Task.FromResult<string?>(null);
}
