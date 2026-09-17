using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>What a watched-folder walk found, and what it decided not to look at (<c>WatchedFolderScanCandidates</c>).</summary>
public sealed record WatchedFolderScanCandidates(
    IReadOnlyList<string> Files,
    int IgnoredUnsupportedType,
    IReadOnlyList<string> IgnoredUnsupportedExtensions);

/// <summary>
/// Filesystem scan helpers and duplicate guards for watched-folder remux scan dispatch (port of the
/// disk-touching parts of <c>refiner_watched_folder_remux_scan_dispatch_ops.py</c> — the parts the rules
/// port (#537) deliberately deferred: <c>is_refiner_media_candidate</c>'s own file check, and walking a
/// real directory tree for <c>collect_media_files_under_path</c>/<c>iter_watched_folder_media_candidates</c>).
/// </summary>
public static class WatchedFolderScanOps
{
    /// <summary>Files that legitimately sit beside media and are not a failed attempt at it.</summary>
    private static readonly HashSet<string> NonMediaCompanionSuffixes = new(StringComparer.Ordinal)
    {
        ".srt", ".sub", ".idx", ".ass", ".ssa", ".vtt", ".sup", ".nfo", ".txt", ".md", ".log", ".xml", ".json",
        ".yml", ".yaml", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tbn", ".bmp", ".par2", ".sfv", ".nzb",
        ".torrent", ".url", ".db", ".ini", ".bak", ".mp3", ".flac", ".m4a", ".aac", ".ac3", ".dts", ".ogg", ".wav",
        ".part", ".partial", ".crdownload", ".downloading", ".tmp", ".!ut", ".!qb",
    };

    private static readonly HashSet<string> DefaultTransientDownloadDirMarkers = new(StringComparer.Ordinal)
    {
        ".sabnzbd", "__admin__", "_failed_", "_unpack_", "_repair_", "incomplete",
    };

    /// <summary><c>is_refiner_media_candidate</c>: the disk-touching half (the extension allowlist itself
    /// is <see cref="RemuxRules.MediaExtensions"/>, already ported by the rules engine).</summary>
    public static bool IsRefinerMediaCandidate(string path)
    {
        try
        {
            return File.Exists(path) && RemuxRules.MediaExtensions.Contains(Path.GetExtension(path).ToLowerInvariant());
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }

    /// <summary><c>is_transient_download_artifact_media_path</c>.</summary>
    public static bool IsTransientDownloadArtifactMediaPath(string path, IReadOnlyCollection<string>? excludeMarkers)
    {
        var stem = Path.GetFileNameWithoutExtension(path).Trim();
        if (stem.Length is >= 32 and <= 64 && stem.All(Uri.IsHexDigit))
        {
            return true;
        }

        var parts = path.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries)
            .Select(p => p.Trim().ToLowerInvariant()).ToHashSet(StringComparer.Ordinal);
        var markers = excludeMarkers is { Count: > 0 }
            ? excludeMarkers.Select(m => m.Trim().ToLowerInvariant()).Where(m => m.Length > 0).ToHashSet(StringComparer.Ordinal)
            : DefaultTransientDownloadDirMarkers;
        return parts.Overlaps(markers);
    }

    /// <summary><c>iter_watched_folder_media_candidates</c>: candidate files under <paramref name="watchedRoot"/>,
    /// plus a count of what the allowlist rejected. Files only; directories are never returned.</summary>
    public static WatchedFolderScanCandidates IterWatchedFolderMediaCandidates(
        string watchedRoot,
        IReadOnlyCollection<string>? mediaExtensions,
        IReadOnlyCollection<string>? excludeMarkers,
        bool excludeHidden,
        bool topLevelOnly)
    {
        var root = Path.GetFullPath(watchedRoot);
        var found = new List<string>();
        var rejected = 0;
        var rejectedSuffixes = new SortedSet<string>(StringComparer.Ordinal);
        HashSet<string>? configuredExtensions = null;
        if (mediaExtensions is { Count: > 0 })
        {
            configuredExtensions = mediaExtensions
                .Select(v => v.Trim())
                .Where(v => v.Length > 0)
                .Select(v => v.StartsWith('.') ? v.ToLowerInvariant() : "." + v.ToLowerInvariant())
                .ToHashSet(StringComparer.Ordinal);
        }

        IEnumerable<string> Walk()
        {
            var option = topLevelOnly ? SearchOption.TopDirectoryOnly : SearchOption.AllDirectories;
            try
            {
                return Directory.EnumerateFileSystemEntries(root, "*", option);
            }
            catch (IOException)
            {
                return [];
            }
            catch (UnauthorizedAccessException)
            {
                return [];
            }
        }

        foreach (var p in Walk().OrderBy(p => p, StringComparer.Ordinal))
        {
            if (!File.Exists(p))
            {
                continue;
            }

            string relative;
            try
            {
                relative = Path.GetRelativePath(root, Path.GetFullPath(p));
            }
            catch (ArgumentException)
            {
                continue;
            }

            if (relative.StartsWith("..", StringComparison.Ordinal))
            {
                continue;
            }

            var relativeParts = relative.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries);
            if (excludeHidden && relativeParts.Any(part => part.StartsWith('.')))
            {
                continue;
            }

            if (IsTransientDownloadArtifactMediaPath(p, excludeMarkers))
            {
                continue;
            }

            var suffix = Path.GetExtension(p).ToLowerInvariant();
            var accepted = configuredExtensions is not null ? configuredExtensions.Contains(suffix) : IsRefinerMediaCandidate(p);
            if (!accepted)
            {
                if (suffix.Length > 0 && !NonMediaCompanionSuffixes.Contains(suffix))
                {
                    rejected++;
                    rejectedSuffixes.Add(suffix);
                }

                continue;
            }

            found.Add(p);
        }

        return new WatchedFolderScanCandidates(found, rejected, [.. rejectedSuffixes]);
    }

    /// <summary><c>relative_posix_path_under_watched</c>.</summary>
    public static string RelativePosixPathUnderWatched(string watchedRoot, string filePath) =>
        Path.GetRelativePath(Path.GetFullPath(watchedRoot), Path.GetFullPath(filePath)).Replace('\\', '/');

    /// <summary><c>refiner_active_remux_pass_exists_for_relative_path</c>.</summary>
    public static async Task<bool> ActiveRemuxPassExistsForRelativePathAsync(
        UnitOfWork uow, string relativePosix, string mediaScope, long? libraryId, long? excludeJobId = null)
    {
        var wantScope = RefinerMediaScopes.Normalize(mediaScope);
        var rows = await uow.QueryAsync(
            "SELECT id, payload_json FROM refiner_jobs WHERE job_kind = @kind AND status IN ('pending', 'leased')",
            reader => (Id: reader.GetInt64(0), PayloadJson: reader.IsDBNull(1) ? null : reader.GetString(1)),
            ("@kind", RequeueStore.RemuxPassJobKind)).ConfigureAwait(false);

        foreach (var (id, payloadJson) in rows)
        {
            if (excludeJobId is { } exclude && id == exclude)
            {
                continue;
            }

            var raw = (payloadJson ?? string.Empty).Trim();
            if (raw.Length == 0)
            {
                continue;
            }

            PyJson data;
            try
            {
                data = PyJsonParser.Parse(raw);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (data is not PyDict dict)
            {
                continue;
            }

            var rel = dict.Get("relative_media_path") is PyStr relStr ? relStr.Value : null;
            long? jobLibraryId = dict.Get("library_id") is PyInt libInt ? (long)libInt.Value : null;
            var jobScope = dict.Get("media_scope") is PyStr scopeStr ? RefinerMediaScopes.Normalize(scopeStr.Value) : RefinerMediaScopes.Movie;
            var sameLibrary = libraryId is null || jobLibraryId == libraryId;
            if (rel is not null && rel.Trim() == relativePosix && jobScope == wantScope && sameLibrary)
            {
                return true;
            }
        }

        return false;
    }

    private static bool ExistingCompletedOutputPathIsSafe(string path)
    {
        try
        {
            var info = new FileInfo(path);
            return info.Exists && info.Length > 0;
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static string? ExpectedOutputFileForRelativePath(string outputRoot, string relativePosix)
    {
        var root = Path.GetFullPath(outputRoot);
        var parts = relativePosix.Split('/').Where(p => p.Length > 0 && p is not ("." or "..")).ToArray();
        if (parts.Length == 0)
        {
            return null;
        }

        var candidate = Path.GetFullPath(Path.Combine([root, .. parts]));
        var relative = Path.GetRelativePath(root, candidate);
        return relative.StartsWith("..", StringComparison.Ordinal) ? null : candidate;
    }

    /// <summary><c>refiner_completed_remux_output_exists_for_relative_path</c>.</summary>
    public static async Task<bool> CompletedRemuxOutputExistsForRelativePathAsync(
        UnitOfWork uow,
        string relativePosix,
        string mediaScope,
        long? libraryId,
        string? outputRoot,
        string? sourcePath)
    {
        var wantScope = RefinerMediaScopes.Normalize(mediaScope);
        var rows = await uow.QueryAsync(
            "SELECT detail FROM activity_events WHERE module = @module AND event_type = @type AND instr(detail, @needle) > 0 " +
            "ORDER BY id DESC LIMIT 50",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@module", "refiner"),
            ("@type", Weir.Core.Activity.ActivityEventTypes.RefinerFileRemuxPassCompleted),
            ("@needle", relativePosix)).ConfigureAwait(false);

        foreach (var raw in rows)
        {
            var trimmed = (raw ?? string.Empty).Trim();
            if (trimmed.Length == 0)
            {
                continue;
            }

            PyJson data;
            try
            {
                data = PyJsonParser.Parse(trimmed);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (data is not PyDict dict)
            {
                continue;
            }

            if (dict.Get("ok") is not PyBool { Value: true } || dict.Get("source_deleted_after_success") is not PyBool { Value: false })
            {
                continue;
            }

            if (dict.Get("relative_media_path") is not PyStr relStr || relStr.Value != relativePosix)
            {
                continue;
            }

            if (libraryId is { } wantLib && dict.Get("library_id") is PyInt eventLib && (long)eventLib.Value != wantLib)
            {
                continue;
            }

            var jobScope = dict.Get("media_scope") is PyStr scopeStr ? RefinerMediaScopes.Normalize(scopeStr.Value) : RefinerMediaScopes.Movie;
            if (jobScope != wantScope)
            {
                continue;
            }

            if (sourcePath is not null && !CompletedEventMatchesCurrentSource(dict, sourcePath))
            {
                continue;
            }

            if (dict.Get("output_file") is not PyStr outputStr || outputStr.Value.Trim().Length == 0)
            {
                continue;
            }

            if (ExistingCompletedOutputPathIsSafe(outputStr.Value))
            {
                return true;
            }
        }

        // An output file by itself is enough to prevent an accidental duplicate remux, but not enough
        // evidence to delete a source that may have been replaced since the history row expired.
        // Cleanup callers provide sourcePath and therefore require a matching completion record above.
        if (outputRoot is not null && sourcePath is null)
        {
            var expected = ExpectedOutputFileForRelativePath(outputRoot, relativePosix);
            if (expected is not null && ExistingCompletedOutputPathIsSafe(expected))
            {
                return true;
            }
        }

        return false;
    }

    private static bool CompletedEventMatchesCurrentSource(PyDict data, string sourcePath)
    {
        FileInfo stat;
        try
        {
            stat = new FileInfo(sourcePath);
            if (!stat.Exists)
            {
                return false;
            }
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }

        // Weir's port does not have a POSIX inode/device fingerprint on Windows; fall back to the
        // path+size check every build (including private builds before fingerprints existed) recorded.
        if (data.Get("inspected_source_path") is PyStr inspected && data.Get("source_size_bytes") is PyInt recordedSize)
        {
            try
            {
                var samePath = string.Equals(Path.GetFullPath(inspected.Value), Path.GetFullPath(sourcePath), StringComparison.OrdinalIgnoreCase);
                return samePath && recordedSize.Value == stat.Length;
            }
            catch (ArgumentException)
            {
                return false;
            }
        }

        return false;
    }

    /// <summary><c>retry_completed_movie_source_cleanup</c>: conservative — only the immediate parent
    /// folder of a candidate file under the watched root, never the watched root itself.</summary>
    public static (bool Ok, string? Reason) RetryCompletedMovieSourceCleanup(string watchedRoot, string filePath)
    {
        string root, src;
        try
        {
            root = Path.GetFullPath(watchedRoot);
            src = Path.GetFullPath(filePath);
        }
        catch (ArgumentException exception)
        {
            return (false, $"Source cleanup retry skipped because the path was not safely under the watched folder ({exception.Message}).");
        }

        if (!src.StartsWith(root, StringComparison.OrdinalIgnoreCase))
        {
            return (false, "Source cleanup retry skipped because the path was not safely under the watched folder.");
        }

        var movieFolder = Path.GetDirectoryName(src);
        if (movieFolder is null || string.Equals(movieFolder, root, StringComparison.OrdinalIgnoreCase))
        {
            return (false, "Source cleanup retry skipped because the file sits directly in the watched folder root.");
        }

        if (!movieFolder.StartsWith(root, StringComparison.OrdinalIgnoreCase))
        {
            return (false, "Source cleanup retry skipped because the release folder is outside the watched folder.");
        }

        try
        {
            if (Directory.Exists(movieFolder))
            {
                Directory.Delete(movieFolder, recursive: true);
            }

            return (true, null);
        }
        catch (DirectoryNotFoundException)
        {
            return (true, null);
        }
        catch (IOException exception)
        {
            return (false, $"Source cleanup retry could not remove the release folder because this path is still locked or blocked ({exception.Message}).");
        }
        catch (UnauthorizedAccessException exception)
        {
            return (false, $"Source cleanup retry could not remove the release folder because this path is still locked or blocked ({exception.Message}).");
        }
    }

    /// <summary><c>cleanup_rejected_file</c>: apply the saved rejection policy without ever deleting a
    /// populated folder.</summary>
    public static (bool Deleted, string Detail) CleanupRejectedFile(string watchedRoot, string filePath, string action)
    {
        if (!string.Equals((action ?? "leave").Trim(), "delete_file", StringComparison.OrdinalIgnoreCase))
        {
            return (false, "Weir left the rejected file in place because this library's cleanup action is Leave in place.");
        }

        string root, source;
        try
        {
            root = Path.GetFullPath(watchedRoot);
            source = Path.GetFullPath(filePath);
        }
        catch (ArgumentException exception)
        {
            return (false, $"Weir did not delete the rejected file because it was not safely inside the watched folder ({exception.Message}).");
        }

        if (!source.StartsWith(root, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(source, root, StringComparison.OrdinalIgnoreCase) ||
            !File.Exists(source))
        {
            return (false, "Weir did not delete the rejected path because it is not a regular file inside the watched folder.");
        }

        try
        {
            File.Delete(source);
        }
        catch (IOException exception)
        {
            return (false, $"Weir could not delete the rejected file because it is locked or unavailable ({exception.Message}).");
        }
        catch (UnauthorizedAccessException exception)
        {
            return (false, $"Weir could not delete the rejected file because it is locked or unavailable ({exception.Message}).");
        }

        var parent = Path.GetDirectoryName(source);
        while (parent is not null && !string.Equals(parent, root, StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                Directory.Delete(parent);
            }
            catch (IOException)
            {
                break;
            }
            catch (UnauthorizedAccessException)
            {
                break;
            }

            parent = Path.GetDirectoryName(parent);
        }

        return (true, "Weir deleted the rejected file because this library's cleanup action is Delete rejected file.");
    }

    /// <summary>
    /// <c>check_file_access</c>: confirm the source opens for reading and the output folder accepts a
    /// write. Ported using .NET's own file-share enforcement (equivalent to the Win32
    /// <c>CreateFileW(FILE_SHARE_READ|FILE_SHARE_DELETE)</c> probe on Windows) rather than the raw P/Invoke
    /// Python uses; the POSIX advisory <c>flock</c> half is not reproduced; it is advisory in Python too
    /// and does not catch an unrelated writer that never calls <c>flock</c> itself.
    /// </summary>
    public static (bool Ok, string? Problem) CheckFileAccess(bool skipAccessTests, string filePath, string? outputFolder)
    {
        if (skipAccessTests)
        {
            return (true, null);
        }

        try
        {
            using var handle = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
            var buffer = new byte[1];
            _ = handle.Read(buffer, 0, 1);
        }
        catch (IOException exception)
        {
            return (false, $"Weir could not open this file for reading — it is usually locked by whatever is still writing it. The system reported: {exception.Message}.");
        }
        catch (UnauthorizedAccessException exception)
        {
            return (false, $"Weir could not open this file for reading — it is usually locked by whatever is still writing it. The system reported: {exception.Message}.");
        }

        if (outputFolder is not null)
        {
            var problem = OutputRootProblem(outputFolder);
            if (problem is not null)
            {
                return (false, problem);
            }
        }

        return (true, null);
    }

    /// <summary>Resolved folders for one scan (<c>RefinerPathRuntime</c>, the fields the scan itself reads).</summary>
    public sealed record RefinerScanPathRuntime(string WatchedFolder, string OutputFolder, string WorkFolderEffective);

    /// <summary>
    /// <c>resolve_refiner_path_runtime_for_library</c>: resolve one library's folders, or say why they
    /// cannot be used. Reads <c>refiner_libraries</c> directly (ADR-0014); no environment path fallback.
    /// </summary>
    public static (RefinerScanPathRuntime? Runtime, string? Error) ResolvePathRuntimeForLibrary(RefinerLibraryRecord library, string weirHome)
    {
        ArgumentNullException.ThrowIfNull(library);
        var label = library.Name.Trim().Length > 0 ? library.Name.Trim() : (library.MediaType == RefinerMediaScopes.Tv ? "TV" : "Movies");

        var watchedRaw = (library.WatchedFolder ?? string.Empty).Trim();
        if (watchedRaw.Length == 0)
        {
            return (null, $"The {label} library has no watched folder set. Manual remux and folder-scan jobs need a watched folder to resolve relative paths. Set it on Processing → Libraries before enqueueing or running those jobs.");
        }

        var watchedPath = RefinerLibraryFolders.ExpandForFilesystem(watchedRaw);
        if (!Directory.Exists(watchedPath))
        {
            return (null, $"The {label} library's watched folder must be an existing directory.");
        }

        var folderRow = new RefinerLibraryFolderRow(library.Id, library.MediaType, (int)library.DisplayOrder, library.WorkFolder, library.OutputFolder);
        var workRaw = (library.WorkFolder ?? string.Empty).Trim();
        var workEffectiveRaw = RefinerLibraryFolders.EffectiveWorkFolder(folderRow, weirHome);
        var workIsDefault = !string.Equals(workEffectiveRaw, workRaw, StringComparison.Ordinal);
        var workPath = RefinerLibraryFolders.ExpandForFilesystem(workEffectiveRaw);

        var outRaw = (library.OutputFolder ?? string.Empty).Trim();
        if (outRaw.Length == 0)
        {
            return (null, $"The {label} library has no output folder set. Set it on Processing → Libraries before running a live remux pass.");
        }

        var outputPath = RefinerLibraryFolders.ExpandForFilesystem(outRaw);
        if (!Directory.Exists(outputPath))
        {
            return (null, $"The {label} library's output folder must be an existing directory.");
        }

        var separationError = ValidatePathSeparation(watchedPath, workPath, outputPath);
        if (separationError is not null)
        {
            return (null, separationError);
        }

        if (!workIsDefault && !Directory.Exists(workPath))
        {
            return (null, $"The {label} library's work/temp folder must be an existing directory when set to a custom path.");
        }

        return (new RefinerScanPathRuntime(watchedPath, outputPath, workPath), null);
    }

    private static bool IsSameOrNested(string a, string b)
    {
        if (string.Equals(a, b, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        var aWithSep = a.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var bWithSep = b.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return b.StartsWith(aWithSep, StringComparison.OrdinalIgnoreCase) || a.StartsWith(bWithSep, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary><c>_validate_path_separation</c>.</summary>
    private static string? ValidatePathSeparation(string? watched, string work, string? output)
    {
        if (output is not null)
        {
            if (IsSameOrNested(work, output))
            {
                return "The work/temp folder and output folder must be separate (no overlap or containment).";
            }

            if (watched is not null && IsSameOrNested(watched, output))
            {
                return "The watched folder and output folder must be separate (no overlap or containment).";
            }
        }

        if (watched is not null && IsSameOrNested(watched, work))
        {
            return "The watched folder and work/temp folder must be separate (no overlap or containment).";
        }

        return null;
    }

    private static string? OutputRootProblem(string outputFolder)
    {
        var probe = Path.Combine(outputFolder, $".weir-write-test-{Environment.ProcessId}");
        try
        {
            Directory.CreateDirectory(outputFolder);
            File.WriteAllBytes(probe, [0]);
        }
        catch (IOException exception)
        {
            return $"Weir cannot write to the output folder ({outputFolder}), so it did not start work that would have nowhere to go. The system reported: {exception.Message}.";
        }
        catch (UnauthorizedAccessException exception)
        {
            return $"Weir cannot write to the output folder ({outputFolder}), so it did not start work that would have nowhere to go. The system reported: {exception.Message}.";
        }
        finally
        {
            try
            {
                File.Delete(probe);
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }

        return null;
    }
}
