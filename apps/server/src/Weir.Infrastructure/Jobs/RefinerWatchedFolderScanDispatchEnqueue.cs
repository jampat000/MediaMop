using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// Enqueue <c>refiner.watched_folder.remux_scan_dispatch.v1</c> (port of
/// <c>refiner_watched_folder_remux_scan_dispatch_enqueue.py</c>): manual HTTP and the periodic scheduler
/// share these checks and the exact payload/dedupe-key shape.
/// </summary>
public static class RefinerWatchedFolderScanDispatchEnqueue
{
    private static string ScanJobMediaScope(string? payloadJson)
    {
        var raw = (payloadJson ?? string.Empty).Trim();
        if (raw.Length == 0)
        {
            return RefinerMediaScopes.Movie;
        }

        PyJson data;
        try
        {
            data = PyJsonParser.Parse(raw);
        }
        catch (PyJsonDecodeException)
        {
            return RefinerMediaScopes.Movie;
        }

        if (data is not PyDict dict || dict.Get("media_scope") is not PyStr scope || scope.Value is not ("movie" or "tv"))
        {
            return RefinerMediaScopes.Movie;
        }

        return scope.Value;
    }

    private static long? ScanJobLibraryId(string? payloadJson)
    {
        var raw = (payloadJson ?? string.Empty).Trim();
        if (raw.Length == 0)
        {
            return null;
        }

        PyJson data;
        try
        {
            data = PyJsonParser.Parse(raw);
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }

        if (data is not PyDict dict || dict.Get("library_id") is not PyInt value || value.Value <= 0)
        {
            return null;
        }

        return (long)value.Value;
    }

    /// <summary>
    /// <c>refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan</c>: true when a pending/leased
    /// scan already covers this exact library. A legacy job with no library id still occupies its whole
    /// Movies/TV scope.
    /// </summary>
    public static async Task<bool> QueueHasActiveScanAsync(UnitOfWork uow, string mediaScope, long? libraryId)
    {
        var want = RefinerMediaScopes.Normalize(mediaScope);
        var rows = await uow.QueryAsync(
            "SELECT payload_json FROM refiner_jobs WHERE job_kind = @kind AND status IN ('pending', 'leased')",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@kind", RefinerWatchedFolderScanDispatchJobKinds.ScanDispatch)).ConfigureAwait(false);

        foreach (var payloadJson in rows)
        {
            var jobLibraryId = ScanJobLibraryId(payloadJson);
            if (libraryId is { } wantLibrary)
            {
                if (jobLibraryId == wantLibrary)
                {
                    return true;
                }

                if (jobLibraryId is null && ScanJobMediaScope(payloadJson) == want)
                {
                    return true;
                }

                continue;
            }

            if (ScanJobMediaScope(payloadJson) == want)
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// <c>validate_watched_folder_scan_dispatch_prerequisites</c>: shared checks for manual HTTP and
    /// periodic enqueue (library found; watched folder saved; output folder saved when live remux is on).
    /// </summary>
    public static async Task<(bool Ok, ScanDispatchPrerequisiteError? Error)> ValidatePrerequisitesAsync(
        UnitOfWork uow, bool enqueueRemuxJobs, string mediaScope, long? libraryId)
    {
        var library = libraryId is { } id ? await LibraryStore.GetAsync(uow, id).ConfigureAwait(false) : null;
        library ??= await LibraryStore.SeededForScopeAsync(uow, mediaScope).ConfigureAwait(false);
        if (library is null)
        {
            // One store now (#363): a database with no library covering this scope is one an operator
            // emptied, not an unmigrated one.
            return (false, ScanDispatchPrerequisiteError.NoSavedWatchedFolder);
        }

        var error = ScanDispatchPrerequisites.Validate(library.WatchedFolder, library.OutputFolder, enqueueRemuxJobs);
        return (error is null, error);
    }

    /// <summary><c>enqueue_watched_folder_remux_scan_dispatch_job</c>: insert one scan job with a unique
    /// dedupe key. Caller commits.</summary>
    public static Task<RefinerJob> EnqueueScanDispatchJobAsync(
        UnitOfWork uow, RefinerJobStore jobStore, bool enqueueRemuxJobs, string scanTrigger, string mediaScope, long? libraryId)
    {
        ArgumentNullException.ThrowIfNull(jobStore);
        var payload = new PyDict()
            .Set("enqueue_remux_jobs", enqueueRemuxJobs)
            .Set("scan_trigger", ScanDispatchJobPayload.NormalizeTrigger(scanTrigger))
            .Set("media_scope", RefinerMediaScopes.Normalize(mediaScope));
        if (libraryId is { } id)
        {
            payload.Set("library_id", id);
        }

        var dedupe = $"{RefinerWatchedFolderScanDispatchJobKinds.ScanDispatch}:{Guid.NewGuid():N}";
        return jobStore.EnqueueOrGetAsync(
            dedupe,
            RefinerWatchedFolderScanDispatchJobKinds.ScanDispatch,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));
    }

    /// <summary>
    /// <c>try_enqueue_periodic_watched_folder_remux_scan_dispatch</c>: one library's periodic tick. The
    /// #533 fix (whether this scope is scheduled at all) is decided by the caller — see
    /// <see cref="RefinerWatchedFolderScanDispatchScheduleTask"/> — exactly as Python decides it from the
    /// per-scope <c>movie_schedule_enabled</c>/<c>tv_schedule_enabled</c> rows before ever reaching here.
    /// <paramref name="enqueueRemuxJobs"/> is the operator's <c>..._periodic_enqueue_remux_jobs</c> setting.
    /// </summary>
    public static async Task<(bool Inserted, string? Skip)> TryEnqueuePeriodicAsync(
        UnitOfWork uow, RefinerJobStore jobStore, RefinerLibraryRecord library, bool enqueueRemuxJobs)
    {
        ArgumentNullException.ThrowIfNull(library);
        var scope = RefinerMediaScopes.Normalize(library.MediaType);
        if (await QueueHasActiveScanAsync(uow, scope, library.Id).ConfigureAwait(false))
        {
            return (false, $"active_scan_already_queued_library_{library.Id}");
        }

        var (ok, error) = await ValidatePrerequisitesAsync(uow, enqueueRemuxJobs, scope, library.Id).ConfigureAwait(false);
        if (!ok)
        {
            return (false, error switch
            {
                ScanDispatchPrerequisiteError.MissingOutputForLiveRemux => "missing_output_for_live_remux",
                _ => "no_saved_watched_folder",
            });
        }

        await EnqueueScanDispatchJobAsync(uow, jobStore, enqueueRemuxJobs, "periodic", scope, library.Id).ConfigureAwait(false);
        return (true, null);
    }
}
