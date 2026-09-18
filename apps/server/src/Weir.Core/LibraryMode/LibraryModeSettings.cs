using Weir.Core.Json;
using Weir.Core.Processing;

namespace Weir.Core.LibraryMode;

/// <summary>
/// Library mode's job kinds (#505) and where they sort against the download pipeline's jobs.
/// </summary>
/// <remarks>
/// Built while ADR-0017 froze the SQLite schema, so #505's state originally lived on job rows rather than
/// new tables. Issue #557 (after the freeze ended with #523) moved the per-library settings
/// (<see cref="LibrarySettings"/>) onto real <c>libraries</c> columns and the <c>library_folders</c>
/// table, and the scan index onto <c>library_files</c> — see <c>Weir.Infrastructure.LibraryMode.LibrarySettingsStore</c>/
/// <c>LibraryScanStore</c> and <c>apps/server/README.md</c>, "Library mode" for the current storage.
/// <see cref="ScanKind"/> is still an ordinary <c>jobs</c> row (a scan is real, visible work with a
/// lifecycle); only its bulky per-file payload moved to <c>library_files</c>.
/// </remarks>
public static class LibraryModeJobKinds
{
    /// <summary>
    /// One row per requested scan, an ordinary job. Its completed payload keeps only a small
    /// <c>ok</c>/<c>generated_at</c>/<c>errors</c> outcome; the file list itself lives in
    /// <c>library_files</c> (see <c>LibraryScanStore</c>). The latest completed row for a library is read
    /// as that library's current scan status.
    /// </summary>
    public const string ScanKind = "processing.library.scan.v1";

    /// <summary>One row per file Weir is asked to clean in place. Runs the remux pass in <c>mode: library</c>, then the #506 safe swap.</summary>
    public const string CleanKind = "processing.library.clean.v1";

    public static string ScanDedupeKey(long libraryId) => $"{ScanKind}:{libraryId}:{Guid.NewGuid():N}";

    /// <summary>The dedupe-key prefix every scan row for a library shares, for "find the latest one".</summary>
    public static string ScanDedupeKeyPrefix(long libraryId) => $"{ScanKind}:{libraryId}:";

    public static string CleanDedupeKey(long libraryId, string path)
    {
        // Bounded and filesystem-agnostic: jobs.dedupe_key is VARCHAR(512), and a path can contain
        // anything. The hash keeps one row per (library, path) without ever running long or needing escaping.
        var hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(path)));
        return $"{CleanKind}:{libraryId}:{hash}";
    }
}

/// <summary>
/// Library jobs (scan and clean) always sort after every download-pipeline job: #505 says "library jobs queue behind download
/// jobs". <c>jobs.priority</c> is claimed highest-first (<c>ORDER BY priority DESC, id ASC</c>), and a stuck job's
/// priority is only ever bumped upward to <c>max(pending) + 1</c>, so a library job at this very low, fixed priority is always
/// claimed after any real download-pipeline job, however long those have waited.
/// </summary>
public static class LibraryModePriority
{
    public const int Low = -1_000_000;
}

/// <summary>
/// One library's #505 settings: where it looks, whether the off-by-default schedule runs, and #508's two
/// preflight settings — whether cleaning touches a file still shared with a download (default false, since
/// cleaning one doubles disk use instead of reducing it) and whether a clean that would make a manager
/// re-download the title is skipped rather than performed (default true, the safer default).
/// </summary>
public sealed record LibrarySettings(
    IReadOnlyList<string> Folders,
    bool ScheduleEnabled,
    bool CleanHardlinkedFiles = false,
    bool SkipIfManagerWouldRedownload = true)
{
    public static LibrarySettings Empty { get; } = new([], false);

    public PyDict ToPayload(long libraryId) => new PyDict()
        .Set("library_id", libraryId)
        .Set("library_folders", new PyList(Folders.Select(f => (PyJson)new PyStr(f))))
        .Set("library_schedule_enabled", ScheduleEnabled)
        .Set("clean_hardlinked_files", CleanHardlinkedFiles)
        .Set("skip_if_manager_would_redownload", SkipIfManagerWouldRedownload);

    public static LibrarySettings FromPayload(PyDict? payload)
    {
        if (payload is null)
        {
            return Empty;
        }

        var folders = payload.Get("library_folders") is PyList list
            ? list.Items.OfType<PyStr>().Select(s => s.Value).Where(s => s.Length > 0).ToList()
            : [];
        var scheduleEnabled = payload.Get("library_schedule_enabled") is PyBool { Value: true };
        // Absent on a settings row written before #508 (or a brand-new library): the documented defaults.
        var cleanHardlinkedFiles = payload.Get("clean_hardlinked_files") is PyBool { Value: true };
        var skipIfManagerWouldRedownload = payload.Get("skip_if_manager_would_redownload") is not PyBool { Value: false };
        return new LibrarySettings(folders, scheduleEnabled, cleanHardlinkedFiles, skipIfManagerWouldRedownload);
    }
}

/// <summary>A library folder failed validation (mirrors <see cref="ProcessingLibraryException"/> for the same family of checks).</summary>
public sealed class LibraryModeException : Exception
{
    public LibraryModeException(string message)
        : base(message)
    {
    }
}

/// <summary>
/// Library folders (#505 point 1): one or more folders Weir cleans in place, separate from a library's watched/work/output
/// folders and validated the same way (<see cref="LibraryRules.ValidateFolders"/>'s overlap check, reused rather than
/// duplicated).
/// </summary>
public static class LibraryFolderRules
{
    /// <summary>
    /// Normalizes, de-duplicates and validates that none of <paramref name="folders"/> overlaps the library's own
    /// watched/work/output folders or each other. Overlap with another library's folders is not checked here: library folders
    /// may deliberately be the same folders a media manager (or another Weir library) already watches — #505 says so
    /// explicitly ("These may be the same folders a manager uses, or not").
    /// </summary>
    public static IReadOnlyList<string> Validate(IReadOnlyList<string> folders, ProcessingLibraryRecord library)
    {
        ArgumentNullException.ThrowIfNull(folders);
        ArgumentNullException.ThrowIfNull(library);
        var trimmed = folders.Select(f => (f ?? string.Empty).Trim()).Where(f => f.Length > 0).ToList();
        var normalizedSeen = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<string>();
        foreach (var folder in trimmed)
        {
            var normalized = LibraryRules.NormalizeFolder(folder);
            if (normalized is null || !normalizedSeen.Add(normalized))
            {
                continue;
            }

            foreach (var (label, other) in new[] { ("watched", library.WatchedFolder), ("work", library.WorkFolder), ("output", library.OutputFolder) })
            {
                var otherNormalized = LibraryRules.NormalizeFolder(other);
                if (otherNormalized is not null && LibraryRules.FoldersOverlap(normalized, otherNormalized))
                {
                    throw new LibraryModeException(
                        $"Library folder '{folder}' overlaps this library's {label} folder. Library folders must be separate from the folders the download pipeline uses.");
                }
            }

            result.Add(folder);
        }

        return result;
    }
}
