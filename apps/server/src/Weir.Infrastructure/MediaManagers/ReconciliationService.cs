using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>A guarded filesystem mutation could not complete safely (<c>FileLifecycleError</c>).</summary>
public sealed class FileLifecycleException : Exception
{
    public FileLifecycleException()
    {
    }

    public FileLifecycleException(string message)
        : base(message)
    {
    }

    public FileLifecycleException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>Safe filesystem/database reconciliation checks and repairs (port of <c>weir.platform.reconciliation.service</c>).</summary>
public static class ReconciliationService
{
    private sealed record LibraryFolders(long Id, string Name, string WatchedFolder, string OutputFolder, string WorkFolder);

    /// <summary><c>build_reconciliation_report</c>.</summary>
    public static async Task<PyDict> BuildReportAsync(UnitOfWork uow) =>
        ReconciliationRules.Report(await ScanProcessingPathsAsync(uow).ConfigureAwait(false));

    /// <summary><c>repair_reconciliation_issue</c>. Throws <see cref="PyValueErrorException"/> with the operator's sentence.</summary>
    public static async Task<PyDict> RepairAsync(UnitOfWork uow, string action, long? dbId, string? path, bool confirm)
    {
        _ = dbId;
        if (action == ReconciliationRules.RemoveTempArtifactAction)
        {
            if (!confirm)
            {
                throw new PyValueErrorException("confirm=true is required before removing a temp artifact.");
            }

            if (path is null || PyStrings.Strip(path).Length == 0)
            {
                throw new PyValueErrorException("path is required for this repair action.");
            }

            var roots = WorkRoots(await ListLibrariesAsync(uow).ConfigureAwait(false));
            if (!ReconciliationRules.IsTempArtifactName(PurePathName(path)))
            {
                throw new PyValueErrorException("Refusing to remove a file that does not look like a temp artifact.");
            }

            var removed = SafeUnlinkUnderRoots(path, roots);
            return new PyDict()
                .Set("applied", removed)
                .Set("message", removed ? "Removed the temp artifact." : "Temp artifact is already gone.");
        }

        throw new PyValueErrorException($"Unknown reconciliation repair action: {action}");
    }

    /// <summary><c>safe_unlink_under_roots</c>: delete only a path that normalises under one of the roots.</summary>
    public static bool SafeUnlinkUnderRoots(string path, IReadOnlyList<string> allowedRoots)
    {
        ArgumentNullException.ThrowIfNull(allowedRoots);
        var target = Path.GetFullPath(path);
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        foreach (var rawRoot in allowedRoots)
        {
            var root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(rawRoot));
            if (string.Equals(target, root, comparison) || target.StartsWith(root + Path.DirectorySeparatorChar, comparison))
            {
                try
                {
                    if (!File.Exists(target) && !Directory.Exists(target))
                    {
                        return false;
                    }

                    File.Delete(target);
                    return true;
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    throw new FileLifecycleException($"Could not remove {path}: {exception.Message}", exception);
                }
            }
        }

        throw new FileLifecycleException("Refusing to remove a file outside the authorized folder roots.");
    }

    private static async Task<List<ReconciliationIssue>> ScanProcessingPathsAsync(UnitOfWork uow)
    {
        var libraries = await ListLibrariesAsync(uow).ConfigureAwait(false);
        if (libraries.Count == 0)
        {
            return [];
        }

        var issues = new List<ReconciliationIssue>();
        foreach (var library in libraries)
        {
            foreach (var (role, raw) in new[] { ("watched", library.WatchedFolder), ("output", library.OutputFolder), ("work", library.WorkFolder) })
            {
                if (PyStrings.Strip(raw).Length > 0 && !PathExists(raw))
                {
                    issues.Add(new ReconciliationIssue(
                        "configured_folder_missing",
                        "processing",
                        "warning",
                        $"{library.Name} {role} folder is configured but is not currently reachable on disk.",
                        raw,
                        "libraries",
                        library.Id));
                }
            }
        }

        foreach (var root in WorkRoots(libraries))
        {
            IEnumerable<string> entries;
            try
            {
                entries = Directory.EnumerateFileSystemEntries(root, "*", new EnumerationOptions { RecurseSubdirectories = true, AttributesToSkip = 0, IgnoreInaccessible = true });
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                continue;
            }

            foreach (var entry in entries)
            {
                if (issues.Count >= ReconciliationRules.MaxIssuesPerCategory)
                {
                    return issues;
                }

                if (File.Exists(entry) && ReconciliationRules.IsTempArtifactName(Path.GetFileName(entry)))
                {
                    issues.Add(new ReconciliationIssue(
                        "partial_temp_artifact",
                        "processing",
                        "info",
                        "The work folder contains a temporary artifact from an interrupted operation.",
                        entry,
                        RepairAction: ReconciliationRules.RemoveTempArtifactAction,
                        RequiresConfirmation: true));
                }
            }
        }

        return issues;
    }

    /// <summary><c>_configured_processing_work_roots</c>: every library's work folder that exists, resolved.</summary>
    private static List<string> WorkRoots(IEnumerable<LibraryFolders> libraries)
    {
        var roots = new List<string>();
        foreach (var library in libraries)
        {
            if (PyStrings.Strip(library.WorkFolder).Length == 0)
            {
                continue;
            }

            try
            {
                var root = Path.GetFullPath(library.WorkFolder);
                if (Directory.Exists(root))
                {
                    roots.Add(root);
                }
            }
            catch (Exception exception) when (exception is ArgumentException or IOException or NotSupportedException)
            {
                // Python: OSError from resolve() skips the folder.
            }
        }

        return roots;
    }

    private static bool PathExists(string raw)
    {
        try
        {
            return File.Exists(raw) || Directory.Exists(raw);
        }
        catch (Exception exception) when (exception is ArgumentException or IOException)
        {
            return false;
        }
    }

    private static string PurePathName(string path) => Weir.Core.Media.MediaPathNames.Name(path, OperatingSystem.IsWindows());

    private static Task<List<LibraryFolders>> ListLibrariesAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QueryAsync(
            "SELECT id, name, watched_folder, output_folder, work_folder FROM libraries ORDER BY display_order, id",
            reader => new LibraryFolders(
                SqliteValues.GetInt64(reader, 0),
                SqliteValues.GetString(reader, 1),
                SqliteValues.GetString(reader, 2),
                SqliteValues.GetString(reader, 3),
                SqliteValues.GetString(reader, 4)));
    }
}
