namespace Weir.Core.Library;

/// <summary>One title Weir asked a manager to redownload, still waiting for the new copy (#509, step 4).</summary>
public sealed record WaitingForRedownload(RemovedTrackFileKey File, string Reason, DateTimeOffset RequestedAt);

/// <summary>
/// Tracks titles marked "waiting for new download" after an explicit re-download request (#509, step 4):
/// "mark the titles waiting for new download; clear the mark when the download pipeline processes a file
/// for that title." The clearing half is a hook a future download-pipeline caller invokes (library mode,
/// #505, or the existing watched-folder intake) once it processes a file for the same title — this
/// interface only defines the mark/query/clear surface, not when the pipeline calls it.
/// </summary>
public interface IRedownloadTracker
{
    /// <summary>Mark one title as waiting for a new download, replacing any earlier mark for the same file.</summary>
    Task MarkWaitingAsync(RemovedTrackFileKey file, string reason, CancellationToken cancellationToken = default);

    /// <summary>
    /// The hook: called when the download pipeline (library mode's clean, or the ordinary watched-folder
    /// intake) processes a file for this title, however it now identifies the file. Does nothing if the
    /// title was not marked waiting. Returns true when a mark was actually cleared, so a caller can tell
    /// "this file completed a redownload" apart from "this file was never waiting".
    /// </summary>
    Task<bool> ClearAsync(RemovedTrackFileKey file, CancellationToken cancellationToken = default);

    Task<bool> IsWaitingAsync(RemovedTrackFileKey file, CancellationToken cancellationToken = default);

    /// <summary>Every title still waiting, oldest request first.</summary>
    Task<IReadOnlyList<WaitingForRedownload>> ListWaitingAsync(CancellationToken cancellationToken = default);
}
