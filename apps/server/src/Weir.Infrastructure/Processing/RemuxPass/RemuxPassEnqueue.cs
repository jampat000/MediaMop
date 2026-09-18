using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Processing.RemuxPass;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>The manual enqueue's refusals, with the status and detail the route answers.</summary>
public sealed class RemuxPassEnqueueException : Exception
{
    public RemuxPassEnqueueException()
    {
    }

    public RemuxPassEnqueueException(string message)
        : base(message)
    {
    }

    public RemuxPassEnqueueException(string message, Exception innerException)
        : base(message, innerException)
    {
    }

    public RemuxPassEnqueueException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; } = 400;
}

/// <summary>The work behind <c>POST /processing/jobs/file-remux-pass/enqueue</c> (port of <c>file_remux_pass/api.py</c>).</summary>
public static class RemuxPassEnqueue
{
    /// <summary>Enqueue one pass, or convert a pending one in place when the operator asks for pass-through. Commits nothing.</summary>
    public static async Task<ProcessingJob> EnqueueManualAsync(
        UnitOfWork uow,
        ProcessingJobStore jobs,
        string relativeMediaPath,
        string mediaScope,
        long? libraryId,
        bool passThroughUnchanged)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(jobs);
        var library = await RemuxPassHandler.ResolveLibraryAsync(uow, libraryId, mediaScope).ConfigureAwait(false);
        if (libraryId is not null && (library is null || library.Id != libraryId))
        {
            throw new RemuxPassEnqueueException(404, "The selected library no longer exists. Refresh Libraries and try again.");
        }

        if (library is null || PyStrings.Strip(library.WatchedFolder ?? string.Empty).Length == 0)
        {
            var label = mediaScope == "tv" ? "TV" : "Movies";
            throw new RemuxPassEnqueueException(
                400,
                $"{label} watched folder is not set in saved path settings. " +
                "Manual processing.file.remux_pass.v1 jobs require it to resolve relative_media_path and for bounded source cleanup. " +
                "Saving path settings does not require a watched folder, but you must configure it before enqueueing this job kind.");
        }

        var relative = PyStrings.Strip(relativeMediaPath);
        var effectiveLibraryId = library.Id;
        var payload = new PyDict()
            .Set("relative_media_path", relative)
            .Set("media_scope", mediaScope)
            .Set("library_id", effectiveLibraryId)
            .Set("pass_through_unchanged", passThroughUnchanged)
            // An operator asked for this, including when it replaces a queued job's choice below.
            .Set("trigger", "manual");
        if (passThroughUnchanged && await PendingJobForPathAsync(uow, relative, effectiveLibraryId).ConfigureAwait(false) is { } pending)
        {
            // Keep hand-off metadata and other additive fields already carried by the queued job.
            PyDict existing;
            try
            {
                existing = PyJsonParser.Parse(string.IsNullOrEmpty(pending.PayloadJson) ? "{}" : pending.PayloadJson) as PyDict ?? new PyDict();
            }
            catch (PyJsonDecodeException)
            {
                existing = new PyDict();
            }

            foreach (var (key, value) in payload.Items)
            {
                existing.Set(key, value);
            }

            var json = PyJsonWriter.Dumps(existing, PyJsonFormat.Compact);
            await uow.ExecuteAsync(
                "UPDATE jobs SET payload_json = $payload, not_before = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = $id",
                ("$payload", json),
                ("$id", pending.Id)).ConfigureAwait(false);
            return pending with { PayloadJson = json };
        }

        return jobs.EnqueueOrGet(
            uow.Connection,
            uow.WriteTransaction(),
            $"{RemuxPassOutcomes.JobKind}:{Guid.NewGuid():N}",
            RemuxPassOutcomes.JobKind,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact),
            JobQueueRules.DefaultMaxAttempts,
            0,
            0);
    }

    /// <summary><c>pending_remux_job_for_relative_path</c>: the oldest pending pass for this path.</summary>
    public static async Task<ProcessingJob?> PendingJobForPathAsync(UnitOfWork uow, string relativePath, long? libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var wanted = PyStrings.Strip(relativePath ?? string.Empty);
        if (wanted.Length == 0)
        {
            return null;
        }

        var rows = await uow.QueryAsync(
            "SELECT id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count, max_attempts, last_error, " +
            "not_before, runner_cost, priority, created_at, updated_at FROM jobs WHERE job_kind = $kind AND status = $pending ORDER BY id",
            MediaManagers.HandoffLedgerStore.ReadJob,
            ("$kind", RemuxPassOutcomes.JobKind),
            ("$pending", ProcessingJobStatus.Pending)).ConfigureAwait(false);
        foreach (var job in rows)
        {
            if (string.IsNullOrWhiteSpace(job.PayloadJson))
            {
                continue;
            }

            PyJson data;
            try
            {
                data = PyJsonParser.Parse(job.PayloadJson);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (data is not PyDict dict || dict.Get("relative_media_path") is not PyStr { } path || path.Value != wanted)
            {
                continue;
            }

            if (libraryId is { } id && dict.Get("library_id") is { } jobLibrary and not PyNull && !(jobLibrary is PyInt number && number.Value == id))
            {
                continue;
            }

            return job;
        }

        return null;
    }
}
