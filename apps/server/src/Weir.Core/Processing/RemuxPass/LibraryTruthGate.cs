using System.Globalization;
using Weir.Core.MediaManagers;

namespace Weir.Core.Processing.RemuxPass;

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
    /// <param name="expectedOutputFile">
    /// Issue #545 item 1: the file this pass just published under <paramref name="folder"/>. A manager that reports no
    /// library files inside the folder is not, by itself, evidence the folder is safe to remove — it may simply not have
    /// scanned or imported yet (or it imports by copy and scans later). When given, at least one reporting manager must
    /// show positive evidence this exact release has been picked up: either the exact output path anywhere in its
    /// reported library, or the same title (file-name stem) at a different path, which is how several managers record an
    /// import they then renamed. Without that evidence the folder is left in place, never deleted, regardless of age.
    /// </param>
    /// <param name="handoffOutcomeAcknowledged">
    /// Issue #545 item 1, second way to be "confirmed": the hand-off ledger already recorded this pass's outcome as
    /// delivered (<c>completed</c> or <c>passed-through</c>) to the manager that asked for it. When true, the
    /// <paramref name="expectedOutputFile"/> check is skipped — the manager has already been told the file is ready, so
    /// the "no evidence yet" caution no longer applies. A hand-off that has not reached that terminal state (or that
    /// names no manager at all) leaves this false and the ordinary evidence check runs.
    /// </param>
    public static LibraryTruthVerdict EvaluateForFolder(
        IReadOnlyList<ManagerLibraryTruth> answers,
        string folder,
        string mediaScope,
        Func<string, string?> resolve,
        bool ignoreCase,
        string? expectedOutputFile = null,
        bool handoffOutcomeAcknowledged = false)
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
        if (!handoffOutcomeAcknowledged && expectedOutputFile is not null && !AnyManagerConfirmsImport(answers, expectedOutputFile, resolve, ignoreCase))
        {
            return new LibraryTruthVerdict(
                LibraryTruthVerdict.Skipped,
                $"{all} reported no library files inside this folder, but has not yet reported this release as imported " +
                "(at its output path, or moved elsewhere under the same title) either, and Weir has no confirmed " +
                "hand-off outcome for it. It may simply not have scanned or finished importing yet, so Weir left the " +
                "folder in place rather than remove it during the manager's import window.",
                []);
        }

        return new LibraryTruthVerdict(
            LibraryTruthVerdict.Passed,
            $"{all} reported no library files inside this folder, so Weir treated it as safe to remove under the other gates.",
            []);
    }

    /// <summary>
    /// Issue #545 item 1: positive evidence a manager picked up this exact release — its output path appears anywhere in
    /// a reporting manager's library (not only inside the folder being considered), or the same title (file-name stem)
    /// appears at a different path, which is how a manager that renames on import would record it.
    /// </summary>
    private static bool AnyManagerConfirmsImport(IReadOnlyList<ManagerLibraryTruth> answers, string expectedOutputFile, Func<string, string?> resolve, bool ignoreCase)
    {
        var comparison = ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var expectedResolved = resolve(expectedOutputFile) ?? expectedOutputFile;
        var expectedTitle = TitleKey(expectedResolved);
        foreach (var answer in answers)
        {
            foreach (var raw in answer.LibraryFilePaths)
            {
                var resolved = resolve(raw) ?? raw;
                if (string.Equals(resolved, expectedResolved, comparison))
                {
                    return true;
                }

                if (expectedTitle.Length > 0 && string.Equals(TitleKey(resolved), expectedTitle, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
        }

        return false;
    }

    /// <summary>The file-name stem, used to recognise the same release at a different path (a manager's own rename).</summary>
    private static string TitleKey(string path) =>
        System.IO.Path.GetFileNameWithoutExtension(path.Replace('\\', '/'));

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
