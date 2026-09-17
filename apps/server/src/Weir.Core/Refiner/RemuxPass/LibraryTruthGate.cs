using System.Globalization;
using Weir.Core.MediaManagers;

namespace Weir.Core.Refiner.RemuxPass;

/// <summary>Whether a folder is clear of every manager's kept library files, and why (<c>LibraryTruthVerdict</c>).</summary>
public sealed record LibraryTruthVerdict(string Check, string Note, IReadOnlyList<string> MatchedPaths)
{
    public const string Passed = "passed";
    public const string Failed = "failed";
    public const string Skipped = "skipped";

    public bool ClearsDelete => Check == Passed;
}

/// <summary>
/// The gate in front of an output-folder delete (port of <c>manager_library_truth.py</c>): only a manager that actually
/// answered can clear a folder, and any one of them keeping a library file inside it stops the delete.
/// </summary>
public static class LibraryTruthGate
{
    /// <summary><c>evaluate_library_truth_for_folder</c>.</summary>
    /// <param name="answers">Every manager's answer for the scope.</param>
    /// <param name="folder">The folder about to be deleted.</param>
    /// <param name="mediaScope"><c>movie</c> or <c>tv</c>.</param>
    /// <param name="resolve">Path resolution (<c>Path(raw).expanduser().resolve()</c>); null when a path cannot be resolved.</param>
    /// <param name="ignoreCase">Whether path comparison ignores case (Windows).</param>
    public static LibraryTruthVerdict EvaluateForFolder(
        IReadOnlyList<ManagerLibraryTruth> answers,
        string folder,
        string mediaScope,
        Func<string, string?> resolve,
        bool ignoreCase)
    {
        ArgumentNullException.ThrowIfNull(answers);
        ArgumentNullException.ThrowIfNull(resolve);
        var scopeWord = mediaScope switch
        {
            "tv" => "TV episodes",
            _ => "Movies",
        };
        if (answers.Count == 0)
        {
            return new LibraryTruthVerdict(
                LibraryTruthVerdict.Skipped,
                $"No media manager is connected for {scopeWord}, so Weir could not check whether this " +
                "folder still holds library files. It was left in place.",
                []);
        }

        var silent = answers.Where(answer => !answer.IsReported).ToList();
        if (silent.Count > 0)
        {
            var names = string.Join(", ", silent.Select(answer => answer.Connection.Label));
            var firstDetail = silent.Select(answer => answer.Detail).FirstOrDefault(detail => !string.IsNullOrEmpty(detail));
            var note = $"Weir could not confirm with {names} whether this folder still holds library files, so it was left in place.";
            if (firstDetail is not null)
            {
                note = $"{note} {firstDetail}";
            }

            return new LibraryTruthVerdict(LibraryTruthVerdict.Skipped, note, []);
        }

        var folderResolved = resolve(folder) ?? folder;
        var hits = new List<string>();
        var holders = new List<string>();
        foreach (var answer in answers)
        {
            var inside = PathsInside(answer.LibraryFilePaths, folderResolved, resolve, ignoreCase);
            if (inside.Count > 0)
            {
                holders.Add(answer.Connection.Label);
                hits.AddRange(inside);
            }
        }

        if (hits.Count > 0)
        {
            return new LibraryTruthVerdict(
                LibraryTruthVerdict.Failed,
                $"{string.Join(", ", holders)} still keeps at least one library file inside this folder, so Weir " +
                $"treats it as the kept library location and will not delete it. Example path(s): {Sample(hits)}",
                hits);
        }

        var all = string.Join(", ", answers.Select(answer => answer.Connection.Label));
        return new LibraryTruthVerdict(
            LibraryTruthVerdict.Passed,
            $"{all} reported no library files inside this folder, so Weir treated it as safe to remove under the other gates.",
            []);
    }

    /// <summary><c>Path.relative_to</c>: whether <paramref name="path"/> is <paramref name="root"/> or sits under it.</summary>
    public static bool IsSameOrUnder(string path, string root, bool ignoreCase)
    {
        ArgumentNullException.ThrowIfNull(path);
        ArgumentNullException.ThrowIfNull(root);
        var comparison = ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var p = Parts(path);
        var r = Parts(root);
        if (p.Count < r.Count)
        {
            return false;
        }

        for (var i = 0; i < r.Count; i++)
        {
            if (!string.Equals(p[i], r[i], comparison))
            {
                return false;
            }
        }

        return true;
    }

    private static List<string> Parts(string path)
    {
        var parts = path.Split('/', '\\').Where(part => part.Length > 0).ToList();
        if (path.StartsWith('/') || path.StartsWith('\\'))
        {
            parts.Insert(0, "/");
        }

        return parts;
    }

    private static List<string> PathsInside(IReadOnlyList<string> rawPaths, string folder, Func<string, string?> resolve, bool ignoreCase)
    {
        var inside = new List<string>();
        foreach (var raw in rawPaths)
        {
            if (resolve(raw) is not { } resolved)
            {
                continue;
            }

            if (IsSameOrUnder(resolved, folder, ignoreCase))
            {
                inside.Add(resolved);
            }
        }

        return inside;
    }

    private static string Sample(List<string> paths)
    {
        var shown = string.Join("; ", paths.Take(3));
        return paths.Count > 3 ? $"{shown} (+{(paths.Count - 3).ToString(CultureInfo.InvariantCulture)} more)" : shown;
    }
}
