using Weir.Core.Rules;

namespace Weir.Core.Library;

/// <summary>
/// Identifies one file's removed-track history the same way <c>refiner_files</c> identifies the file
/// itself: a library id (null when the file predates library tracking or came from the watched-folder
/// pipeline) plus the path relative to that library's root.
/// </summary>
public sealed record RemovedTrackFileKey(long? LibraryId, string RelativePath)
{
    public override string ToString() => LibraryId is { } id ? $"{id}:{RelativePath}" : RelativePath;
}

/// <summary>
/// Where the removed tracks a Refiner pass recorded for a file are kept (#509, step 1 — "store removed
/// tracks per file"). The schema is frozen until #523 (ADR-0017 — the .NET port keeps the Python-created
/// SQLite schema unchanged), so this is deliberately not a new table: an implementation either keeps the
/// records in memory (fine until the process restarts — see <c>InMemoryRemovedTrackStore</c>) or reads them
/// back out of a JSON-capable column a pass already writes into, such as <c>refiner_file_logs.detail_json</c>
/// (see <c>Weir.Infrastructure.Library.FileLogRemovedTrackStore</c>'s remarks for why that one was chosen
/// and what is still missing before it is real).
/// </summary>
public interface IRemovedTrackStore
{
    /// <summary>Record what one Refiner pass removed from one file, replacing whatever was recorded for it before.</summary>
    Task RecordAsync(RemovedTrackFileKey key, IReadOnlyList<RemovedTrackRecord> tracks, CancellationToken cancellationToken = default);

    /// <summary>The most recently recorded removed tracks for one file; empty when none are recorded.</summary>
    Task<IReadOnlyList<RemovedTrackRecord>> GetAsync(RemovedTrackFileKey key, CancellationToken cancellationToken = default);

    /// <summary>Every file this store currently has removed tracks recorded for, keyed the same way.</summary>
    Task<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>> GetAllAsync(CancellationToken cancellationToken = default);
}
