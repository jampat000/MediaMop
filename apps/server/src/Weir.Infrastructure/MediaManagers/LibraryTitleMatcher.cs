using Weir.Core.MediaManagers;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>
/// Matches a library-mode scan's walked files to the title a Sonarr/Radarr connection already knows them under
/// (issue #551), using #507's <see cref="IMediaManagerPort.ListLibraryFilesAsync"/> and the reverse of
/// <see cref="HandoffCompletionReporter.TranslateOutputPath"/>: that helper rebuilds a local path under a
/// manager's own root (local -&gt; manager, as <c>LibraryFileChangeNotifier.ResolveManagerPath</c> already uses
/// it for #507's notify step); here the same substitution runs the other way — a manager's own file path
/// rebuilt under one of Weir's local library folders — since it is symmetric in which root is "from" and
/// which is "to".
/// </summary>
public static class LibraryTitleMatcher
{
    /// <summary>Issue #551 point 1: case-insensitive on Windows, exact elsewhere. Separator style is always ignored.</summary>
    private static readonly StringComparison PathComparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

    public static bool PathsEqual(string? left, string? right)
    {
        var normalizedLeft = Normalize(left);
        var normalizedRight = Normalize(right);
        return normalizedLeft.Length > 0 && string.Equals(normalizedLeft, normalizedRight, PathComparison);
    }

    private static string Normalize(string? path) => (path ?? string.Empty).Replace('\\', '/').TrimEnd('/');

    /// <summary>
    /// The path in <paramref name="localPaths"/> that <paramref name="managerFilePath"/> names, or null when
    /// none does. Tried directly first (Weir and the manager share paths — the common case, and also what
    /// covers a manager whose own library roots could not be read), then through every pairing of one of the
    /// manager's own library roots and one of the library's local folders the reverse translation could apply.
    /// </summary>
    public static string? MatchLocalPath(
        string managerFilePath,
        IReadOnlyCollection<string> localPaths,
        IReadOnlyList<ManagerLibraryDescriptor> managerLibraries,
        IReadOnlyList<string> localFolders)
    {
        ArgumentNullException.ThrowIfNull(managerFilePath);
        ArgumentNullException.ThrowIfNull(localPaths);
        ArgumentNullException.ThrowIfNull(managerLibraries);
        ArgumentNullException.ThrowIfNull(localFolders);

        foreach (var candidate in localPaths)
        {
            if (PathsEqual(candidate, managerFilePath))
            {
                return candidate;
            }
        }

        foreach (var library in managerLibraries)
        {
            if (string.IsNullOrEmpty(library.RootPath))
            {
                continue;
            }

            foreach (var folder in localFolders)
            {
                if (HandoffCompletionReporter.TranslateOutputPath(managerFilePath, library.RootPath, folder) is not { } translated)
                {
                    continue;
                }

                foreach (var candidate in localPaths)
                {
                    if (PathsEqual(candidate, translated))
                    {
                        return candidate;
                    }
                }
            }
        }

        return null;
    }
}
