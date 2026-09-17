namespace Weir.Core.Media;

/// <summary>pathlib's <c>name</c>, <c>suffix</c> and <c>stem</c>, which differ from <see cref="Path"/>'s for dot files.</summary>
public static class MediaPathNames
{
    /// <summary><c>PurePath.name</c>: the final component.</summary>
    public static string Name(string path, bool windows)
    {
        ArgumentNullException.ThrowIfNull(path);
        var normalized = MediaToolLocations.Normalize(path, windows);
        var cut = windows ? normalized.LastIndexOfAny(['\\', ':']) : normalized.LastIndexOf('/');
        var name = normalized[(cut + 1)..];
        return name == "." ? string.Empty : name;
    }

    /// <summary><c>PurePath.suffix</c>: empty for <c>.bashrc</c> and for a name ending in a dot.</summary>
    public static string Suffix(string path, bool windows)
    {
        var name = Name(path, windows);
        var i = name.LastIndexOf('.');
        return i > 0 && i < name.Length - 1 ? name[i..] : string.Empty;
    }

    /// <summary><c>PurePath.stem</c>.</summary>
    public static string Stem(string path, bool windows)
    {
        var name = Name(path, windows);
        var i = name.LastIndexOf('.');
        return i > 0 && i < name.Length - 1 ? name[..i] : name;
    }
}
