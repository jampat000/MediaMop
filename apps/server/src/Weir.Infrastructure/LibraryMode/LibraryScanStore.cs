using Microsoft.Data.Sqlite;
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

    /// <summary>
    /// The latest completed scan's snapshot (the file index / plan cache), or null when none has finished
    /// yet. The job payload only carries <c>generated_at</c>/<c>errors</c> now (#557 moved the file list to
    /// <c>library_files</c>); <see cref="LibraryScanSnapshot.FromPayload"/> reads those, and the files are
    /// read from the table separately.
    /// </summary>
    public static async Task<LibraryScanSnapshot?> LatestSnapshotAsync(UnitOfWork uow, long libraryId)
    {
        var latest = await LatestAsync(uow, libraryId).ConfigureAwait(false);
        if (latest is not { Status: RefinerJobStatus.Completed, PayloadJson: { } json } || string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        LibraryScanSnapshot? snapshot;
        try
        {
            snapshot = PyJsonParser.Parse(json) is PyDict dict ? LibraryScanSnapshot.FromPayload(dict, libraryId) : null;
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }

        return snapshot is null ? null : snapshot with { Files = await FilesForLibraryAsync(uow, libraryId).ConfigureAwait(false) };
    }

    /// <summary>
    /// The library's current file index, used to seed the next scan's ffprobe cache: since #557,
    /// <c>library_files</c> always holds whatever the previous scan recorded (a scan in progress has not
    /// written its own new rows yet), so this is simply the table's current contents for the library —
    /// no need to single out "the previous job" any more.
    /// </summary>
    public static async Task<IReadOnlyList<LibraryScanFileEntry>> PreviousFilesForCacheAsync(UnitOfWork uow, long libraryId) =>
        await FilesForLibraryAsync(uow, libraryId).ConfigureAwait(false);

    /// <summary>
    /// Records the job's own small outcome (<c>ok</c>/<c>reason</c>/<c>generated_at</c>/<c>errors</c>) on its
    /// payload, keeping every other key, and replaces the library's <c>library_files</c> rows with
    /// <paramref name="snapshot"/>'s file list (#557: the file list itself is no longer part of the job
    /// payload, so job-row retention can no longer delete it).
    /// </summary>
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

        payload.Set(LibraryScanSnapshot.PayloadKey, new PyDict()
            .Set("generated_at", snapshot.GeneratedAt.ToUnixTimeSeconds())
            .Set("errors", new PyList(snapshot.Errors.Select(e => (PyJson)new PyStr(e)))));
        await uow.ExecuteAsync(
            "UPDATE refiner_jobs SET payload_json = @payload, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
            ("@payload", PyJsonWriter.Dumps(payload, PyJsonFormat.Compact)),
            ("@id", jobId)).ConfigureAwait(false);

        await ReplaceFilesAsync(uow, snapshot.LibraryId, snapshot.Files).ConfigureAwait(false);
    }

    private static async Task<List<LibraryScanFileEntry>> FilesForLibraryAsync(UnitOfWork uow, long libraryId) =>
        await uow.QueryAsync(
            "SELECT path, size_bytes, mtime, classification, summary, reason, removed_audio_tracks, removed_subtitle_tracks, " +
            "manager_kind, manager_title, probe_json, estimated_bytes_saved, manager_connection_id, manager_title_id, " +
            "manager_file_id, manager_quality_profile_id FROM library_files WHERE library_id = @id ORDER BY path",
            ReadFile,
            ("@id", libraryId)).ConfigureAwait(false);

    private static async Task ReplaceFilesAsync(UnitOfWork uow, long libraryId, IReadOnlyList<LibraryScanFileEntry> files)
    {
        await uow.ExecuteAsync("DELETE FROM library_files WHERE library_id = @id", ("@id", libraryId)).ConfigureAwait(false);
        foreach (var file in files)
        {
            await uow.ExecuteAsync(
                "INSERT INTO library_files (library_id, path, size_bytes, mtime, classification, summary, reason, " +
                "removed_audio_tracks, removed_subtitle_tracks, estimated_bytes_saved, manager_kind, manager_title, " +
                "manager_connection_id, manager_title_id, manager_file_id, manager_quality_profile_id, probe_json) VALUES " +
                "(@library_id, @path, @size_bytes, @mtime, @classification, @summary, @reason, @removed_audio, @removed_subtitle, " +
                "@estimated_bytes_saved, @manager_kind, @manager_title, @manager_connection_id, @manager_title_id, @manager_file_id, " +
                "@manager_quality_profile_id, @probe_json)",
                ("@library_id", libraryId),
                ("@path", file.Path),
                ("@size_bytes", file.SizeBytes),
                ("@mtime", file.ModifiedTimeUnixSeconds),
                ("@classification", LibraryScanFileEntry.ClassificationName(file.Classification)),
                ("@summary", file.Summary),
                ("@reason", file.Reason),
                ("@removed_audio", file.RemovedAudioCount),
                ("@removed_subtitle", file.RemovedSubtitleCount),
                ("@estimated_bytes_saved", file.EstimatedBytesSaved),
                ("@manager_kind", file.ManagerKind),
                ("@manager_title", file.ManagerTitle),
                ("@manager_connection_id", file.ManagerConnectionId),
                ("@manager_title_id", file.ManagerTitleId),
                ("@manager_file_id", file.ManagerFileId),
                ("@manager_quality_profile_id", file.ManagerQualityProfileId),
                ("@probe_json", file.ProbeJson)).ConfigureAwait(false);
        }
    }

    private static LibraryScanFileEntry ReadFile(SqliteDataReader reader) => new(
        Path: SqliteValues.GetString(reader, 0),
        SizeBytes: SqliteValues.GetInt64(reader, 1),
        ModifiedTimeUnixSeconds: SqliteValues.GetInt64(reader, 2),
        Classification: ClassificationOf(SqliteValues.GetString(reader, 3)),
        Summary: SqliteValues.GetStringOrNull(reader, 4),
        Reason: SqliteValues.GetStringOrNull(reader, 5),
        RemovedAudioCount: (int)SqliteValues.GetInt64(reader, 6),
        RemovedSubtitleCount: (int)SqliteValues.GetInt64(reader, 7),
        ManagerKind: SqliteValues.GetStringOrNull(reader, 8),
        ManagerTitle: SqliteValues.GetStringOrNull(reader, 9),
        ProbeJson: SqliteValues.GetStringOrNull(reader, 10),
        EstimatedBytesSaved: SqliteValues.GetInt64(reader, 11),
        ManagerConnectionId: reader.IsDBNull(12) ? null : reader.GetInt64(12),
        ManagerTitleId: SqliteValues.GetStringOrNull(reader, 13),
        ManagerFileId: reader.IsDBNull(14) ? null : reader.GetInt64(14),
        ManagerQualityProfileId: reader.IsDBNull(15) ? null : reader.GetInt64(15));

    private static LibraryFileClassification ClassificationOf(string value) => value switch
    {
        "matches" => LibraryFileClassification.Matches,
        "would_change" => LibraryFileClassification.WouldChange,
        _ => LibraryFileClassification.CannotProcess,
    };

    private static string EscapeLike(string value) =>
        value.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);
}
