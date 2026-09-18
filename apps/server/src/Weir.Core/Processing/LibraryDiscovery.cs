using System.Text.RegularExpressions;
using Weir.Core.Json;

namespace Weir.Core.Processing;

/// <summary>Discovery could not run, with an operator-readable reason (<c>ProcessingDiscoveryError</c>).</summary>
public sealed class ProcessingDiscoveryException : Exception
{
    public ProcessingDiscoveryException(string message)
        : base(message)
    {
    }
}

/// <summary>The four kinds of difference <see cref="LibraryDrift"/> can report (<c>DriftKind</c>).</summary>
public static class LibraryDriftKinds
{
    public const string RootMoved = "root_moved";
    public const string LibraryRemoved = "library_removed";
    public const string LibraryAdded = "library_added";
    public const string PathNotLocal = "path_not_local";
}

/// <summary>
/// One library a manager reports, and whether Weir already has it (<c>DiscoverableLibrary</c>).
/// <paramref name="OutputPath"/> is where the manager expects processed output, when it processes before
/// importing — shown before the import so the operator sees what will be filled in, rather than discovering
/// it afterwards.
/// </summary>
public sealed record DiscoverableLibrary(
    string Key,
    string Name,
    string? MediaType,
    string? RootPath,
    bool AlreadyImported,
    string? LocalPathProblem,
    string? OutputPath = null,
    bool ProcessesBeforeImport = false,
    string? OutputPathProblem = null);

/// <summary>A difference between what the manager says and what Weir has saved (<c>LibraryDrift</c>). Reported,
/// never applied.</summary>
public sealed record LibraryDrift(
    string Kind,
    long? LibraryId,
    string LibraryName,
    string? ManagerValue,
    string? WeirValue,
    string Detail);

/// <summary>
/// The pure, path-shape half of <c>processing_library_discovery</c> (port). The filesystem check
/// (<c>Path.is_dir()</c>) is direct IO and lives in Weir.Infrastructure, next to every other
/// <c>Directory.Exists</c> call in this codebase.
/// </summary>
public static class LibraryDiscoveryRules
{
    private static readonly Regex DriveLetter = new("^[A-Za-z]:/", RegexOptions.Compiled);

    /// <summary><c>_comparable</c>: case- and separator-insensitive, matching <c>HandoffPaths</c>.</summary>
    public static string Comparable(string path) =>
        PyStrings.Strip(path.Replace('\\', '/')).TrimEnd('/').ToLowerInvariant();

    /// <summary>
    /// <c>_looks_absolute</c>: absolute on *any* host, judged textually. <c>Path.IsPathRooted</c> answers for
    /// the host running this code, so a perfectly good POSIX root reported by a Linux manager reads as
    /// relative on Windows. The manager's path is not this host's path, so only the shape is checked here.
    /// </summary>
    public static bool LooksAbsolute(string raw)
    {
        var text = raw.Replace('\\', '/');
        if (text.StartsWith('/'))
        {
            return true;
        }

        // Drive letter (C:/...) or UNC (//server/share).
        return DriveLetter.IsMatch(text) || text.StartsWith("//", StringComparison.Ordinal);
    }
}
