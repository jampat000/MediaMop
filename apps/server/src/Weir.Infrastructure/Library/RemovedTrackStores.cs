using System.Collections.Concurrent;
using Weir.Core.Library;
using Weir.Core.Rules;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Library;

/// <summary>
/// In-memory <see cref="IRemovedTrackStore"/> (#509 step 1): keeps the most recently recorded removed
/// tracks for each file for the life of the process. This is the store registered by default — nothing in
/// this build yet needs the records to outlive a restart, since the library-mode job that would call
/// <see cref="RecordAsync"/> for real (#505) has not landed. Safe as a DI singleton.
/// </summary>
public sealed class InMemoryRemovedTrackStore : IRemovedTrackStore
{
    private readonly ConcurrentDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>> _byFile = new();

    public Task RecordAsync(RemovedTrackFileKey key, IReadOnlyList<RemovedTrackRecord> tracks, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(tracks);
        _byFile[key] = [.. tracks];
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<RemovedTrackRecord>> GetAsync(RemovedTrackFileKey key, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        return Task.FromResult(_byFile.TryGetValue(key, out var tracks) ? tracks : (IReadOnlyList<RemovedTrackRecord>)[]);
    }

    public Task<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>> GetAllAsync(CancellationToken cancellationToken = default) =>
        Task.FromResult<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>>(
            new Dictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>(_byFile));
}

/// <summary>
/// The durable <see cref="IRemovedTrackStore"/> (#509 step 1): a real <c>removed_tracks</c> table, one row
/// per removed track, added by #557's migration (0041_removed_tracks). Before #557 this reused
/// <c>refiner_file_logs.detail_json</c> (an existing JSON-capable column) since the schema was frozen; that
/// column has no retention exemption (<see cref="Weir.Infrastructure.Refiner.FileLogStore.PruneAsync"/> deletes any row past its
/// window regardless of outcome), so a removed-track record could disappear from under #509's "titles
/// missing tracks your new rules keep" list. The dedicated table has no such exposure.
/// </summary>
public sealed class FileLogRemovedTrackStore : IRemovedTrackStore
{
    private readonly SqliteDatabase _database;
    private readonly TimeProvider _time;

    public FileLogRemovedTrackStore(SqliteDatabase database, TimeProvider? time = null)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _time = time ?? TimeProvider.System;
    }

    public async Task RecordAsync(RemovedTrackFileKey key, IReadOnlyList<RemovedTrackRecord> tracks, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(tracks);
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "DELETE FROM removed_tracks WHERE relative_path = @relative_path AND library_id IS @library_id",
            ("@relative_path", key.RelativePath), ("@library_id", key.LibraryId)).ConfigureAwait(false);

        var recordedAt = SqliteValues.ToSqlite(PyDateTime.FromUtc(_time.GetUtcNow().UtcDateTime));
        foreach (var track in tracks)
        {
            await uow.ExecuteAsync(
                "INSERT INTO removed_tracks (library_id, relative_path, language, track_type, codec, variant, reason, recorded_at) " +
                "VALUES (@library_id, @relative_path, @language, @track_type, @codec, @variant, @reason, @recorded_at)",
                ("@library_id", key.LibraryId),
                ("@relative_path", key.RelativePath),
                ("@language", track.Language),
                ("@track_type", track.Type == RemovedTrackType.Subtitle ? "subtitle" : "audio"),
                ("@codec", track.Codec),
                ("@variant", track.Variant),
                ("@reason", track.Reason),
                ("@recorded_at", recordedAt)).ConfigureAwait(false);
        }

        await uow.CommitAsync().ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<RemovedTrackRecord>> GetAsync(RemovedTrackFileKey key, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        var rows = await uow.QueryAsync(
            "SELECT language, track_type, codec, variant, reason FROM removed_tracks " +
            "WHERE relative_path = @relative_path AND library_id IS @library_id ORDER BY id",
            reader => ReadFrom(reader, offset: 0),
            ("@relative_path", key.RelativePath), ("@library_id", key.LibraryId)).ConfigureAwait(false);
        return rows;
    }

    public async Task<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>> GetAllAsync(CancellationToken cancellationToken = default)
    {
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        var rows = await uow.QueryAsync(
            "SELECT library_id, relative_path, language, track_type, codec, variant, reason FROM removed_tracks ORDER BY library_id, relative_path, id",
            reader => (
                LibraryId: reader.IsDBNull(0) ? (long?)null : reader.GetInt64(0),
                RelativePath: SqliteValues.GetString(reader, 1),
                Track: ReadFrom(reader, offset: 2)),
            []).ConfigureAwait(false);

        var result = new Dictionary<RemovedTrackFileKey, List<RemovedTrackRecord>>();
        foreach (var row in rows)
        {
            var key = new RemovedTrackFileKey(row.LibraryId, row.RelativePath);
            if (!result.TryGetValue(key, out var list))
            {
                result[key] = list = [];
            }

            list.Add(row.Track);
        }

        return result.ToDictionary(pair => pair.Key, pair => (IReadOnlyList<RemovedTrackRecord>)pair.Value);
    }

    private static RemovedTrackRecord ReadFrom(Microsoft.Data.Sqlite.SqliteDataReader reader, int offset) => new()
    {
        Language = SqliteValues.GetString(reader, offset),
        Type = SqliteValues.GetString(reader, offset + 1) == "subtitle" ? RemovedTrackType.Subtitle : RemovedTrackType.Audio,
        Codec = SqliteValues.GetString(reader, offset + 2),
        Variant = SqliteValues.GetStringOrNull(reader, offset + 3),
        Reason = SqliteValues.GetString(reader, offset + 4),
    };
}
