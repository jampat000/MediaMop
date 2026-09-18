using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>Either a relative path Processing can use, or the reason it cannot be produced.</summary>
public sealed record HandoffPathResult(string? RelativeMediaPath, string? Problem)
{
    public bool Ok => RelativeMediaPath is not null;
}

/// <summary>
/// A manager's absolute file path made relative to a watched folder, textually and without touching
/// the filesystem (port of <c>weir.platform.media_managers.handoff_paths</c>).
/// </summary>
public static class HandoffPaths
{
    public static HandoffPathResult RelativeMediaPathForHandoff(string? watchedFolder, string? filePath)
    {
        var folder = PyStrings.Strip(watchedFolder ?? string.Empty);
        if (folder.Length == 0)
        {
            return new HandoffPathResult(
                null,
                "Weir's watched folder is not set for this media scope, so there is nowhere to resolve the hand-off against.");
        }

        var target = PyStrings.Strip(filePath ?? string.Empty);
        if (target.Length == 0)
        {
            return new HandoffPathResult(null, "The hand-off did not name a file path.");
        }

        var folderParts = Comparable(folder).Split('/').Where(p => p.Length > 0).ToList();
        var targetPartsCmp = Comparable(target).Split('/').Where(p => p.Length > 0).ToList();
        var targetPartsRaw = PyStrings.Strip(target.Replace('\\', '/')).Split('/').Where(p => p.Length > 0).ToList();

        if (targetPartsCmp.Count <= folderParts.Count || !targetPartsCmp.Take(folderParts.Count).SequenceEqual(folderParts, StringComparer.Ordinal))
        {
            return new HandoffPathResult(null, OutsideMessage(folder, target));
        }

        var relative = PosixJoin(targetPartsRaw.Skip(folderParts.Count));
        if (relative.Length == 0 || relative.Split('/').Contains(".."))
        {
            return new HandoffPathResult(null, OutsideMessage(folder, target));
        }

        return new HandoffPathResult(relative, null);
    }

    /// <summary><c>PurePath(*parts).as_posix()</c> for parts that hold no separators: empty and <c>.</c> parts drop out.</summary>
    private static string PosixJoin(IEnumerable<string> parts) => string.Join('/', parts.Where(p => p != "."));

    private static string Comparable(string part) =>
        PyStrings.Strip(part.Replace('\\', '/')).TrimEnd('/').ToLowerInvariant();

    private static string OutsideMessage(string folder, string target) =>
        $"The hand-off names {PyStrings.Repr(target)}, which is not inside Weir's watched folder {PyStrings.Repr(folder)}. " +
        "Point the media manager and Weir at the same folder — both hosts have to see it at that path.";
}
