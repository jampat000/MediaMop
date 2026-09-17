using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>
/// One file a library-mode swap changed in place, ready to tell every manager that owns it (#507). This is
/// the whole surface library mode (#505) needs: a scope, the path Weir itself sees, and — only when Weir's
/// path differs from a manager's own view of the same folder — the local library root to translate from.
/// Nothing here depends on the library-mode schema.
/// </summary>
/// <param name="MediaScope">"movie" or "tv" (<see cref="MediaManagerKinds.Movie"/>/<see cref="MediaManagerKinds.Tv"/>).</param>
/// <param name="FilePath">The changed file's absolute path, as Weir sees it after the swap committed.</param>
/// <param name="LocalLibraryRoot">
/// The library folder <paramref name="FilePath"/> lives under, as Weir sees it. Only needed when a manager
/// might see the same folder at a different path on its own host; omit it when every manager shares Weir's
/// own paths, and the file path is used unchanged.
/// </param>
/// <param name="Reason">What changed, in a sentence a manager's own activity log can show ("removed 2 audio tracks").</param>
public sealed record LibraryFileChange(string MediaScope, string FilePath, string? LocalLibraryRoot = null, string? Reason = null);

/// <summary>
/// Tells every media manager that owns a library-mode file to re-read it after Weir swapped it in place
/// (#507). Library mode (#505) calls this once per changed file; batching, retrying and de-duplicating
/// belong entirely to the implementation.
/// </summary>
public interface ILibraryFileChangeNotifier
{
    Task NotifyAsync(LibraryFileChange change, CancellationToken cancellationToken = default);
}

/// <summary>The pure rules behind the notifier: path comparison and its de-dupe/backoff policy (#507).</summary>
public static class LibraryFileChangeRules
{
    /// <summary>
    /// Activity <c>event_type</c>s for this area. Kept here rather than in <see cref="Weir.Core.Activity.ActivityEventTypes"/>,
    /// which was pinned to the retired Python backend's constants when this was written; they can move there now.
    /// </summary>
    public const string NotifiedEventType = "library.file_change_notified";

    public const string NotifySkippedEventType = "library.file_change_notify_skipped";

    public const string NotifyWarningEventType = "library.file_change_notify_warning";

    /// <summary>One rescan/re-read call per matched title per manager, at most this often, for a batch of files.</summary>
    public static readonly TimeSpan CoalesceWindow = TimeSpan.FromMinutes(1);

    /// <summary>Case- and separator-insensitive, matching <c>HandoffPaths</c>' own comparison.</summary>
    public static string ComparablePath(string? path) =>
        PyStrings.Strip((path ?? string.Empty).Replace('\\', '/')).TrimEnd('/').ToLowerInvariant();

    /// <summary>Whether two paths name the same file, ignoring separator style and case; two empty paths never match.</summary>
    public static bool PathsEqual(string? left, string? right)
    {
        var comparableLeft = ComparablePath(left);
        return comparableLeft.Length > 0 && comparableLeft == ComparablePath(right);
    }

    /// <summary>What Activity records when every retry failed — a warning, not a failure: the swap already kept the file.</summary>
    public static string CouldNotTellWarning(ManagerConnection connection)
    {
        ArgumentNullException.ThrowIfNull(connection);
        return $"Weir cleaned the file but couldn't tell {connection.Label}; it will catch up at its next disk scan.";
    }
}
