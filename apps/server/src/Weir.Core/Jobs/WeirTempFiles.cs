using System.Text.RegularExpressions;

namespace Weir.Core.Jobs;

/// <summary>
/// The names of temporary files Weir itself creates, so crash recovery and sweeps delete only those
/// (#534). Nothing else in a work or output folder is ever matched.
/// </summary>
/// <remarks>
/// <list type="bullet">
/// <item>Remux output: <c>tempfile.mkstemp(prefix=f"{src.stem}.processing.", suffix=src.suffix or ".mkv", dir=work_dir)</c>,
/// so <c>{stem}.processing.{8 characters of [a-z0-9_]}{suffix}</c> in the library's work folder.</item>
/// <item>The dry-run placeholder <c>dry-run-ffmpeg-destination-placeholder.mkv</c>.</item>
/// <item>Atomic output writes: <c>mkstemp(prefix=f".{dst.name}.", suffix=".partial", dir=dst.parent)</c>,
/// swept by the existing <c>.*.partial</c> glob.</item>
/// </list>
/// Python's periodic sweep matches any name containing <c>.processing.</c>; this is deliberately the
/// exact <c>mkstemp</c> shape instead, so an operator's own <c>Film.processing.notes.txt</c> survives.
/// </remarks>
public static partial class WeirTempFiles
{
    public const string DryRunPlaceholderName = "dry-run-ffmpeg-destination-placeholder.mkv";

    /// <summary><c>tempfile</c>'s random name characters and length.</summary>
    private const string RandomPart = "[a-z0-9_]{8}";

    /// <summary>Any remux temp output name Weir creates, for any source.</summary>
    public static bool IsRemuxTempName(string fileName)
    {
        ArgumentNullException.ThrowIfNull(fileName);
        return fileName == DryRunPlaceholderName || RemuxTempName().IsMatch(fileName);
    }

    /// <summary>
    /// The remux temp output names for one source file: <c>{stem}.processing.XXXXXXXX{suffix}</c>, where
    /// stem and suffix follow Python's <c>PurePath.stem</c> and <c>PurePath.suffix</c>.
    /// </summary>
    public static Regex RemuxTempNameFor(string relativeMediaPath)
    {
        ArgumentNullException.ThrowIfNull(relativeMediaPath);
        var name = PythonName(relativeMediaPath);
        var (stem, suffix) = PythonStemAndSuffix(name);
        var effectiveSuffix = suffix.Length == 0 ? ".mkv" : suffix;
        return new Regex(
            "^" + Regex.Escape(stem) + @"\.processing\." + RandomPart + Regex.Escape(effectiveSuffix) + "$",
            RegexOptions.CultureInvariant,
            TimeSpan.FromSeconds(1));
    }

    /// <summary>Python's <c>glob(".*.partial")</c> name test: a hidden name ending in <c>.partial</c>.</summary>
    public static bool IsPartialOutputName(string fileName, bool ignoreCase)
    {
        ArgumentNullException.ThrowIfNull(fileName);
        var comparison = ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        // "." + "*" + ".partial": at least nine characters, the leading dot not shared with the suffix.
        return fileName.Length >= 1 + ".partial".Length &&
               fileName.StartsWith('.') &&
               fileName.EndsWith(".partial", comparison);
    }

    /// <summary><c>PurePath(path).name</c> for either separator.</summary>
    public static string PythonName(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        var trimmed = path.TrimEnd('/', '\\');
        var index = trimmed.LastIndexOfAny(['/', '\\']);
        return index < 0 ? trimmed : trimmed[(index + 1)..];
    }

    /// <summary><c>PurePath.stem</c> and <c>PurePath.suffix</c>: the last dot not at the start splits them.</summary>
    public static (string Stem, string Suffix) PythonStemAndSuffix(string name)
    {
        ArgumentNullException.ThrowIfNull(name);
        var index = name.LastIndexOf('.');
        if (index <= 0 || index == name.Length - 1)
        {
            return (name, string.Empty);
        }

        return (name[..index], name[index..]);
    }

    [GeneratedRegex(@"^.+\.processing\.[a-z0-9_]{8}(\.[^.]+)$", RegexOptions.CultureInvariant)]
    private static partial Regex RemuxTempName();
}
