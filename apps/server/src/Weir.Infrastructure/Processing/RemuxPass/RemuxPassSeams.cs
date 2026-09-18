using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Rules;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>
/// What a pass measured about the source, for the scheduler and the Files screen (<c>record_measured_media_facts</c>).
/// <c>LibraryId</c> (issue #545 item 5) says which library's row to update; null only when a pass ran with no library
/// resolved (which the handler never does in practice), and the write is then skipped rather than touching every
/// library's row for the path.
/// </summary>
public sealed record MeasuredMediaFacts(
    string RelativePath,
    long? VideoWidth,
    long? VideoHeight,
    string? VideoCodec,
    long? AudioTrackCount,
    long? SubtitleTrackCount,
    double? DurationSeconds,
    IReadOnlyList<string>? AudioCodecs,
    long? VideoBitDepth,
    long? LibraryId = null);

/// <summary>The optional metadata a pass keeps on the file row while it works. Implementations never throw.</summary>
public interface IRemuxPassFileFacts
{
    Task RecordMeasuredMediaFactsAsync(MeasuredMediaFacts facts, CancellationToken cancellationToken);

    /// <summary><paramref name="libraryId"/>: issue #545 item 5 — scopes the write to this library's row for the path.</summary>
    Task RecordOutputCollisionAsync(string relativePath, CollisionDecision decision, long? libraryId, CancellationToken cancellationToken);
}

/// <summary>Everything the TV season-folder cleanup (<c>handle_tv_cleanup_after_success</c>) is handed.</summary>
public sealed record TvSeasonCleanupContext(
    PyDict Output,
    ProcessingPathRuntime Runtime,
    string Source,
    string WatchedRoot,
    long MinFileAgeSeconds,
    long? CurrentJobId,
    PyDict RemuxContext,
    string? FinalOutputFile);

/// <summary>
/// Seam: the TV watched-folder season cleanup after a successful pass (<c>processing_tv_season_folder_cleanup.py</c>), ported
/// as <see cref="TvSeasonFolderCleanup"/> using the manager queue-row mapping (<c>queue_adapter.py</c> /
/// <see cref="Weir.Core.Processing.ManagerQueueSignals"/>) that the watched-folder scan port brought.
/// </summary>
public interface ITvSeasonFolderCleanup
{
    Task RunAsync(TvSeasonCleanupContext context, CancellationToken cancellationToken);
}

/// <summary>
/// A no-op double for tests that exercise other remux-pass behaviour without the TV season cleanup's own gates: records
/// the season-cleanup fields as a skip and removes nothing, which is the outcome Python reaches whenever one of its gates
/// cannot be checked.
/// </summary>
public sealed class SkippedTvSeasonFolderCleanup : ITvSeasonFolderCleanup
{
    public const string SkipReason =
        "TV season cleanup is not available on this server yet, so Weir left the season folder in the TV watched folder untouched.";

    public Task RunAsync(TvSeasonCleanupContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        InitFields(context.Output);
        context.Output.Set("tv_season_folder_skip_reason", SkipReason);
        context.Output.Set("tv_episode_check_summary", new PyList([new PyStr(SkipReason)]));
        return Task.CompletedTask;
    }

    /// <summary><c>init_tv_season_cleanup_activity_fields</c>.</summary>
    public static void InitFields(PyDict output)
    {
        OutputFolderCleanup.SetDefault(output, "tv_season_folder_deleted", PyBool.False);
        OutputFolderCleanup.SetDefault(output, "tv_season_folder_path", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "tv_season_folder_skip_reason", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "tv_episode_check_summary", new PyList());
        OutputFolderCleanup.SetDefault(output, "tv_output_completeness_check", new PyDict());
        OutputFolderCleanup.SetDefault(output, "tv_cascade_folders_deleted", new PyList());
        OutputFolderCleanup.SetDefault(output, "tv_manager_queue_unavailable", PyBool.False);
        OutputFolderCleanup.SetDefault(output, "source_deleted_after_success", PyBool.False);
    }
}

/// <summary>
/// Issue #537 item 4: where a pass learns a title's original language. The metadata provider (TMDb) answers for movies;
/// every failure is a <see cref="LookupResult"/> status, never an exception.
/// </summary>
public interface IOriginalLanguageLookup
{
    Task<LookupResult> LookupAsync(string mediaScope, string relativeMediaPath, HandoffOrigin? origin, CancellationToken cancellationToken);
}
