using Weir.Core.Json;
using Weir.Core.Processing;
using Weir.Core.Text;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing;

/// <summary>What a requeue attempt did (<c>RequeueResult</c>).</summary>
public sealed record RequeueResult(int Requeued, int Skipped, string Detail);

/// <summary>
/// Putting a failed file back to work by hand (port of the manual half of <c>processing_requeue_service.py</c>).
/// The automatic, policy-governed half (<c>decide_retry</c>, <c>record_failure</c>) is only ever reached from
/// the remux-pass failure handler, which is out of scope here.
/// </summary>
public sealed class RequeueStore(ProcessingJobStore jobStore)
{
    /// <summary>Job kind of a manual remux requeue (<c>PROCESSING_FILE_REMUX_PASS_JOB_KIND</c>), run by
    /// <see cref="RemuxPass.RemuxPassHandler"/>.</summary>
    public const string RemuxPassJobKind = "processing.file.remux_pass.v1";

    /// <summary><c>requeue_file</c>: manual reset — attempt count cleared, backoff ignored.</summary>
    public async Task<RequeueResult> RequeueFileAsync(UnitOfWork uow, ProcessingFileRecord row)
    {
        var library = await LibraryStore.GetAsync(uow, row.LibraryId).ConfigureAwait(false);
        if (library is null)
        {
            return new RequeueResult(0, 1, "The library this file belonged to no longer exists, so there is nowhere to queue it.");
        }

        var payload = new PyDict()
            .Set("relative_media_path", row.RelativePath)
            .Set("media_scope", library.MediaType == "tv" ? "tv" : "movie")
            .Set("library_id", library.Id)
            .Set("trigger", "manual");
        // Deliberate fix (#531 item 2): a requeued hand-off keeps its origin, so its outcome still reaches the manager.
        if (await RemuxPass.HandoffOriginCarry.FindAsync(uow, library.Id, row.RelativePath).ConfigureAwait(false) is { } origin)
        {
            payload.Set("origin", origin);
        }

        // The commit at the end of this method releases uow's write lock for every later file in a bulk
        // requeue, but not for the first one: an API request arrives with the lock already taken whenever
        // RequireUserAsync refreshed user_sessions.last_seen_at on its way in, and EnqueueOrGetAsync below
        // opens its own connection and BEGIN IMMEDIATEs on it. Committing here makes the first call behave
        // exactly like the second and every one after it, rather than introducing a new ordering.
        await uow.CommitAsync().ConfigureAwait(false);
        await jobStore.EnqueueOrGetAsync(
            $"{RemuxPassJobKind}:requeue:{Guid.NewGuid():N}",
            RemuxPassJobKind,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact),
            priority: (int)library.Priority).ConfigureAwait(false);

        const string detail = "Queued again by hand. It starts as soon as there is capacity for it.";
        await uow.ExecuteAsync(
            "UPDATE files SET status = @status, status_reason = @reason, failure_attempts = 0, failure_class = NULL, " +
            "next_retry_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
            ("@status", ProcessingFileStatuses.Unprocessed), ("@reason", detail), ("@id", row.Id)).ConfigureAwait(false);

        // ProcessingJobStore writes through its own connection, outside uow's. Committing here (rather than
        // leaving it to the caller) releases uow's write lock before the next file's EnqueueOrGetAsync call
        // in a bulk requeue needs one — otherwise the two connections deadlock against each other's
        // uncommitted BEGIN IMMEDIATE / deferred-write locks until SQLite's busy timeout.
        await uow.CommitAsync().ConfigureAwait(false);
        return new RequeueResult(1, 0, detail);
    }

    /// <summary><c>requeue_files</c>: bulk-by-hand, reporting a total rather than stopping at the first problem.</summary>
    public async Task<RequeueResult> RequeueFilesAsync(UnitOfWork uow, IReadOnlyList<ProcessingFileRecord> rows)
    {
        var requeued = 0;
        var skipped = 0;
        foreach (var row in rows)
        {
            var result = await RequeueFileAsync(uow, row).ConfigureAwait(false);
            requeued += result.Requeued;
            skipped += result.Skipped;
        }

        return new RequeueResult(requeued, skipped, BulkDetail(requeued, skipped));
    }

    /// <summary>The sentence a bulk requeue reports, counted in English.</summary>
    internal static string BulkDetail(int requeued, int skipped) => (requeued, skipped) switch
    {
        (> 0, 0) => $"Queued {Plural.Of(requeued, "file")} again. {(requeued == 1 ? "It starts" : "They start")} as capacity frees up.",
        (> 0, _) => $"Queued {Plural.Of(requeued, "file")} again. {skipped} could not be queued because {(skipped == 1 ? "its" : "their")} library is gone.",
        (0, > 0) => $"Nothing was queued: {Plural.Of(skipped, "file")} {Plural.Noun(skipped, "belongs", "belong")} to a library that no longer exists.",
        _ => "Nothing matched, so nothing was queued.",
    };
}
