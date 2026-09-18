using Weir.Core.Processing;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>One media file a library-folder walk found, before it is probed.</summary>
public sealed record LibraryWalkedFile(string Path, long SizeBytes, long ModifiedTimeUnixSeconds);

/// <summary>
/// Walks a library's #505 library folders for media files, read-only. Reuses the library's existing media-extension and
/// exclude-marker filters (the same CSVs the download-pipeline watched-folder scan uses) so "which files count" agrees with
/// the rest of the library's settings; a dedicated watched-folder-style scan port is out of scope here (see
/// <c>apps/server/README.md</c>'s "known rules-engine gaps"/"seams" sections for the pattern this follows).
/// </summary>
public static class LibraryFileWalker
{
    public static IReadOnlyList<LibraryWalkedFile> Walk(ProcessingLibraryRecord library, IReadOnlyList<string> folders)
    {
        ArgumentNullException.ThrowIfNull(library);
        ArgumentNullException.ThrowIfNull(folders);
        var extensions = SplitCsv(library.MediaExtensionsCsv).Select(NormalizeExtension).Where(e => e.Length > 0).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var excludeMarkers = SplitCsv(library.ExcludeMarkersCsv);
        var found = new List<LibraryWalkedFile>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var folder in folders)
        {
            if (string.IsNullOrWhiteSpace(folder) || !Directory.Exists(folder))
            {
                continue;
            }

            var option = library.TopLevelOnly ? SearchOption.TopDirectoryOnly : SearchOption.AllDirectories;
            IEnumerable<string> files;
            try
            {
                files = Directory.EnumerateFiles(folder, "*", option);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                continue;
            }

            foreach (var path in files)
            {
                if (!seen.Add(path))
                {
                    continue;
                }

                var name = Path.GetFileName(path);
                if (library.ExcludeHidden && name.StartsWith('.'))
                {
                    continue;
                }

                if (extensions.Count > 0 && !extensions.Contains(NormalizeExtension(Path.GetExtension(name))))
                {
                    continue;
                }

                if (excludeMarkers.Any(marker => marker.Length > 0 && name.Contains(marker, StringComparison.OrdinalIgnoreCase)))
                {
                    continue;
                }

                FileInfo info;
                try
                {
                    info = new FileInfo(path);
                    if (!info.Exists)
                    {
                        continue;
                    }
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    continue;
                }

                found.Add(new LibraryWalkedFile(path, info.Length, new DateTimeOffset(info.LastWriteTimeUtc, TimeSpan.Zero).ToUnixTimeSeconds()));
            }
        }

        return found;
    }

    private static string NormalizeExtension(string extension) => extension.Trim().TrimStart('.').ToLowerInvariant();

    private static List<string> SplitCsv(string? csv) =>
        (csv ?? string.Empty).Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
}
