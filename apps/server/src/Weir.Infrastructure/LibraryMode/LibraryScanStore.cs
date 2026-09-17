using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>What a scan request or lookup answers.</summary>
public sealed record LibraryScanJobView(long JobId, string Status, string? LastError);

/// <summary>The most recently created scan row for a library, whatever its status.</summary>
public sealed record LibraryScanJobRow(long JobId, string Status, string? PayloadJson);

/// <summary>
/// Requests a #505 library scan and reads back the latest one's result. Each request is an ordinary
/// <see cref="LibraryModeJobKinds.ScanKind"/> job row; the newest completed row for a library is the file index / plan cache
/// (see <c>apps/server/README.md</c>, "Library mode").
/// </summary>
public static class LibraryScanStore
{
    /// <summary>
    /// Enqueues the scan on <paramref name="uow"/>'s own connection and transaction (<see cref="RefinerJobStore.EnqueueOrGet"/>),
    /// not <see cref="RefinerJobStore.EnqueueOrGetAsync"/>: that opens its own connection, which — called while an API
    /// endpoint's write <see cref="UnitOfWork"/> is still open, as here — can deadlock against it, exactly the trap
    /// <see cref="Weir.Infrastructure.Refiner.RequeueStore"/> already documents for the same reason.
    /// </summary>
    public static Task<RefinerJob> RequestScanAsync(UnitOfWork uow, RefinerJobStore jobs, long libraryId, string trigger)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(jobs);
        var payload = new PyDict().Set("library_id", libraryId).Set("trigger", trigger);
        var job = jobs.EnqueueOrGet(
            uow.Connection,
            uow.WriteTransaction(),
            LibraryModeJobKinds.ScanDedupeKey(libraryId),
            LibraryModeJobKinds.ScanKind,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact),
            JobQueueRules.DefaultMaxAttempts,
            0,
            LibraryModePriority.Low);
        return Task.FromResult(job);
    }

    /// <summary>
    /// Enqueues one <see cref="LibraryModeJobKinds.CleanKind"/> job, on <paramref name="uow"/>'s own connection and
    /// transaction for the same reason <see cref="RequestScanAsync"/> does. Public so the API layer (a different assembly)
    /// can request a clean without risking the same-connection deadlock.
    /// </summary>
    public static Task<RefinerJob> EnqueueCleanAsync(UnitOfWork uow, RefinerJobStore jobs, long libraryId, string path, string trigger, bool confirmFinalRemoval)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(jobs);
        var payload = new PyDict()
            .Set("library_id", libraryId)
            .Set("path", path)
            .Set("trigger", trigger)
            .Set("confirm_final_removal", confirmFinalRemoval);
        var job = jobs.EnqueueOrGet(
            uow.Connection,
            uow.WriteTransaction(),
            LibraryModeJobKinds.CleanDedupeKey(libraryId, path),
            LibraryModeJobKinds.CleanKind,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact),
            JobQueueRules.DefaultMaxAttempts,
            0,
            LibraryModePriority.Low);
        return Task.FromResult(job);
    }

    /// <summary>Whether a scan for this library is already queued or running, so callers do not pile up duplicate requests.</summary>
    public static async Task<LibraryScanJobView?> ActiveScanAsync(UnitOfWork uow, long libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return await uow.QuerySingleAsync(
            "SELECT id, status, last_error FROM refiner_jobs WHERE job_kind = @kind AND dedupe_key LIKE @prefix ESCAPE '\\' " +
            "AND status IN ('pending', 'leased') ORDER BY id DESC LIMIT 1",
            reader => new LibraryScanJobView(reader.GetInt64(0), reader.GetString(1), reader.IsDBNull(2) ? null : reader.GetString(2)),
            ("@kind", LibraryModeJobKinds.ScanKind),
            ("@prefix", EscapeLike(LibraryModeJobKinds.ScanDedupeKeyPrefix(libraryId)) + "%")).ConfigureAwait(false);
    }

    /// <summary>The most recently created scan row for a library, whatever its status, for "what did the last scan say / do".</summary>
    public static async Task<LibraryScanJobRow?> LatestAsync(UnitOfWork uow, long libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return await uow.QuerySingleAsync(
            "SELECT id, status, payload_json FROM refiner_jobs WHERE job_kind = @kind AND dedupe_key LIKE @prefix ESCAPE '\\' " +
            "ORDER BY id DESC LIMIT 1",
            reader => new LibraryScanJobRow(reader.GetInt64(0), reader.GetString(1), reader.IsDBNull(2) ? null : reader.GetString(2)),
            ("@kind", LibraryModeJobKinds.ScanKind),
            ("@prefix", EscapeLike(LibraryModeJobKinds.ScanDedupeKeyPrefix(libraryId)) + "%")).ConfigureAwait(false);
    }

    /// <summary>The latest completed scan's snapshot (the file index / plan cache), or null when none has finished yet.</summary>
    public static async Task<LibraryScanSnapshot?> LatestSnapshotAsync(UnitOfWork uow, long libraryId)
    {
        var latest = await LatestAsync(uow, libraryId).ConfigureAwait(false);
        if (latest is not { Status: RefinerJobStatus.Completed, PayloadJson: { } json } || string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        try
        {
            return PyJsonParser.Parse(json) is PyDict dict ? LibraryScanSnapshot.FromPayload(dict, libraryId) : null;
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }
    }

    /// <summary>The most recent completed scan for any library, used to seed the next scan's ffprobe cache.</summary>
    public static async Task<LibraryScanSnapshot?> PreviousSnapshotForCacheAsync(UnitOfWork uow, long libraryId, long excludingJobId)
    {
        var rows = await uow.QueryAsync(
            "SELECT payload_json FROM refiner_jobs WHERE job_kind = @kind AND dedupe_key LIKE @prefix ESCAPE '\\' " +
            "AND status = @completed AND id != @excluding ORDER BY id DESC LIMIT 1",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@kind", LibraryModeJobKinds.ScanKind),
            ("@prefix", EscapeLike(LibraryModeJobKinds.ScanDedupeKeyPrefix(libraryId)) + "%"),
            ("@completed", RefinerJobStatus.Completed),
            ("@excluding", excludingJobId)).ConfigureAwait(false);
        var json = rows.FirstOrDefault();
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        try
        {
            return PyJsonParser.Parse(json) is PyDict dict ? LibraryScanSnapshot.FromPayload(dict, libraryId) : null;
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }
    }

    /// <summary>Merges <paramref name="snapshot"/> into job <paramref name="jobId"/>'s payload, keeping every other key.</summary>
    public static async Task RecordResultAsync(UnitOfWork uow, long jobId, LibraryScanSnapshot snapshot, bool ok, string? reason)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(snapshot);
        var existingJson = await uow.ScalarAsync("SELECT payload_json FROM refiner_jobs WHERE id = @id", ("@id", jobId)).ConfigureAwait(false);
        PyDict payload;
        try
        {
            payload = existingJson is string text && text.Length > 0 && PyJsonParser.Parse(text) is PyDict dict ? dict : new PyDict();
        }
        catch (PyJsonDecodeException)
        {
            payload = new PyDict();
        }

        payload.Set("ok", ok);
        if (reason is not null)
        {
            payload.Set("reason", reason);
        }

        payload.Set(LibraryScanSnapshot.PayloadKey, snapshot.ToPyDict());
        await uow.ExecuteAsync(
            "UPDATE refiner_jobs SET payload_json = @payload, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
            ("@payload", PyJsonWriter.Dumps(payload, PyJsonFormat.Compact)),
            ("@id", jobId)).ConfigureAwait(false);
    }

    private static string EscapeLike(string value) =>
        value.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);
}
