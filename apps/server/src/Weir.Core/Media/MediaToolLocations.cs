using Weir.Core.Json;

namespace Weir.Core.Media;

/// <summary>
/// Where <c>resolve_ffprobe_ffmpeg</c> looks for ffprobe and ffmpeg, and <c>shutil.which</c>'s PATH search,
/// as pure functions of the environment. The filesystem checks are passed in.
/// </summary>
public static class MediaToolLocations
{
    /// <summary><c>shutil._WIN_DEFAULT_PATHEXT</c>.</summary>
    public const string WindowsDefaultPathExt = ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC";

    /// <summary>Python's <c>os.confstr("CS_PATH")</c> on glibc, used when PATH is unset.</summary>
    public const string PosixDefaultPath = "/bin:/usr/bin";

    public const string FfmpegDirEnvironmentVariable = "WEIR_FFMPEG_DIR";

    /// <summary>#548: where a source install points Weir at MKVToolNix, beside <see cref="FfmpegDirEnvironmentVariable"/>.</summary>
    public const string MkvtoolnixDirEnvironmentVariable = "WEIR_MKVTOOLNIX_DIR";

    /// <summary>The bundled subdirectory MKVToolNix lives in, as <c>ffmpeg</c> is for ffprobe and ffmpeg.</summary>
    public const string MkvtoolnixBundleDirectory = "mkvtoolnix";

    public const string MissingToolsMessage =
        "Weir could not find the video tools it needs. Windows and Docker installs should include them; "
        + "source installs must provide ffprobe and ffmpeg on PATH or set WEIR_FFMPEG_DIR.";

    /// <summary>(ffprobe, ffmpeg) file names for the platform.</summary>
    public static (string Ffprobe, string Ffmpeg) ToolNames(bool windows) =>
        windows ? ("ffprobe.exe", "ffmpeg.exe") : ("ffprobe", "ffmpeg");

    /// <summary>#548: the mkvmerge file name for the platform.</summary>
    public static string MkvmergeToolName(bool windows) => windows ? "mkvmerge.exe" : "mkvmerge";

    /// <summary>
    /// #548: the directories checked for mkvmerge, in order, mirroring <see cref="CandidateDirectories"/>:
    /// <c>WEIR_MKVTOOLNIX_DIR</c> (expanded, not resolved), <c>&lt;home&gt;/bin/mkvtoolnix</c>, then, for a
    /// packaged app, <c>&lt;app&gt;/bin/mkvtoolnix</c> and <c>&lt;app&gt;/_internal/bin/mkvtoolnix</c>.
    /// </summary>
    /// <param name="resolvedWeirHome">The Weir home, already made absolute.</param>
    /// <param name="mkvtoolnixDirEnvironment">The raw <c>WEIR_MKVTOOLNIX_DIR</c> value, or null.</param>
    /// <param name="userHome">What <c>~</c> expands to.</param>
    /// <param name="packagedAppDirectory">The packaged executable's directory, or null when not packaged.</param>
    /// <param name="windows">Windows path rules.</param>
    public static IReadOnlyList<string> MkvtoolnixCandidateDirectories(
        string resolvedWeirHome,
        string? mkvtoolnixDirEnvironment,
        string userHome,
        string? packagedAppDirectory,
        bool windows)
    {
        ArgumentNullException.ThrowIfNull(resolvedWeirHome);
        ArgumentNullException.ThrowIfNull(userHome);
        var candidates = new List<string>();
        var rawEnvDir = PyStrings.Strip(mkvtoolnixDirEnvironment ?? string.Empty);
        if (rawEnvDir.Length > 0)
        {
            candidates.Add(Normalize(ExpandUser(rawEnvDir, userHome, windows), windows));
        }

        candidates.Add(Join(windows, resolvedWeirHome, "bin", MkvtoolnixBundleDirectory));
        if (packagedAppDirectory is not null)
        {
            candidates.Add(Join(windows, packagedAppDirectory, "bin", MkvtoolnixBundleDirectory));
            candidates.Add(Join(windows, packagedAppDirectory, "_internal", "bin", MkvtoolnixBundleDirectory));
        }

        return candidates;
    }

    /// <summary>
    /// The directories checked in order, as pathlib would print them: <c>WEIR_FFMPEG_DIR</c> (expanded, not
    /// resolved), <c>&lt;home&gt;/bin/ffmpeg</c>, then, for a packaged app, <c>&lt;app&gt;/bin/ffmpeg</c> and
    /// <c>&lt;app&gt;/_internal/bin/ffmpeg</c>.
    /// </summary>
    /// <param name="resolvedWeirHome">The Weir home, already made absolute (<c>expanduser().resolve()</c>).</param>
    /// <param name="ffmpegDirEnvironment">The raw <c>WEIR_FFMPEG_DIR</c> value, or null.</param>
    /// <param name="userHome">What <c>~</c> expands to.</param>
    /// <param name="packagedAppDirectory">The packaged executable's directory; null when not running packaged (<c>sys.frozen</c>).</param>
    /// <param name="windows">Windows path rules.</param>
    public static IReadOnlyList<string> CandidateDirectories(
        string resolvedWeirHome,
        string? ffmpegDirEnvironment,
        string userHome,
        string? packagedAppDirectory,
        bool windows)
    {
        ArgumentNullException.ThrowIfNull(resolvedWeirHome);
        ArgumentNullException.ThrowIfNull(userHome);
        var candidates = new List<string>();
        var rawEnvDir = PyStrings.Strip(ffmpegDirEnvironment ?? string.Empty);
        if (rawEnvDir.Length > 0)
        {
            candidates.Add(Normalize(ExpandUser(rawEnvDir, userHome, windows), windows));
        }

        candidates.Add(Join(windows, resolvedWeirHome, "bin", "ffmpeg"));
        if (packagedAppDirectory is not null)
        {
            candidates.Add(Join(windows, packagedAppDirectory, "bin", "ffmpeg"));
            candidates.Add(Join(windows, packagedAppDirectory, "_internal", "bin", "ffmpeg"));
        }

        return candidates;
    }

    /// <summary><c>Path(a) / b / c</c> as <c>str()</c> prints it.</summary>
    public static string Join(bool windows, string first, params string[] rest)
    {
        ArgumentNullException.ThrowIfNull(first);
        ArgumentNullException.ThrowIfNull(rest);
        var separator = windows ? "\\" : "/";
        var combined = first;
        foreach (var part in rest)
        {
            combined = combined.Length == 0 ? part : combined + separator + part;
        }

        return Normalize(combined, windows);
    }

    /// <summary>
    /// pathlib's lexical normalisation: separators unified, repeated separators and <c>.</c> segments
    /// dropped, no trailing separator. <c>..</c> is kept, as pathlib keeps it.
    /// </summary>
    public static string Normalize(string path, bool windows)
    {
        ArgumentNullException.ThrowIfNull(path);
        if (path.Length == 0)
        {
            return ".";
        }

        string prefix;
        string rest;
        if (windows)
        {
            path = path.Replace('/', '\\');
            if (path.StartsWith(@"\\", StringComparison.Ordinal))
            {
                // UNC: \\server\share\ is the anchor.
                var parts = path[2..].Split('\\', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length >= 2)
                {
                    prefix = @"\\" + parts[0] + "\\" + parts[1] + "\\";
                    rest = string.Join('\\', parts.Skip(2));
                }
                else
                {
                    prefix = @"\\";
                    rest = string.Join('\\', parts);
                }
            }
            else if (path.Length >= 2 && path[1] == ':' && char.IsAsciiLetter(path[0]))
            {
                var drive = path[..2];
                var afterDrive = path[2..];
                prefix = afterDrive.StartsWith('\\') ? drive + "\\" : drive;
                rest = afterDrive;
            }
            else
            {
                prefix = path.StartsWith('\\') ? "\\" : string.Empty;
                rest = path;
            }
        }
        else
        {
            prefix = path.StartsWith("//", StringComparison.Ordinal) && !path.StartsWith("///", StringComparison.Ordinal)
                ? "//"
                : path.StartsWith('/') ? "/" : string.Empty;
            rest = path;
        }

        var sep = windows ? '\\' : '/';
        var segments = rest.Split(sep, StringSplitOptions.RemoveEmptyEntries).Where(s => s != ".");
        var joined = string.Join(sep, segments);
        var result = prefix + joined;
        return result.Length == 0 ? "." : result;
    }

    /// <summary><c>os.path.expanduser</c> for <c>~</c> and <c>~/...</c>; other forms are left alone.</summary>
    public static string ExpandUser(string path, string userHome, bool windows)
    {
        ArgumentNullException.ThrowIfNull(path);
        ArgumentNullException.ThrowIfNull(userHome);
        if (!path.StartsWith('~'))
        {
            return path;
        }

        if (path.Length == 1)
        {
            return userHome;
        }

        var next = path[1];
        return next == '/' || (windows && next == '\\') ? userHome.TrimEnd('/', '\\') + path[1..] : path;
    }

    /// <summary>
    /// <c>shutil.which(cmd)</c> as Python 3.11 runs it for a bare command name: on Windows the current
    /// directory first and each PATHEXT extension; directories deduplicated case-insensitively on Windows.
    /// </summary>
    /// <param name="command">A bare command name such as <c>ffprobe</c>.</param>
    /// <param name="pathEnvironment">PATH, or null when unset.</param>
    /// <param name="pathExtEnvironment">PATHEXT, or null when unset (Windows only).</param>
    /// <param name="windows">Windows rules.</param>
    /// <param name="isExecutableFile">True when the candidate exists, is executable and is not a directory.</param>
    public static string? Which(string command, string? pathEnvironment, string? pathExtEnvironment, bool windows, Func<string, bool> isExecutableFile)
    {
        ArgumentNullException.ThrowIfNull(command);
        ArgumentNullException.ThrowIfNull(isExecutableFile);
        var path = pathEnvironment ?? (windows ? ".;C:\\bin" : PosixDefaultPath);
        if (path.Length == 0)
        {
            return null;
        }

        var directories = path.Split(windows ? ';' : ':').ToList();
        IReadOnlyList<string> files = [command];
        if (windows)
        {
            if (!directories.Contains("."))
            {
                directories.Insert(0, ".");
            }

            var source = string.IsNullOrEmpty(pathExtEnvironment) ? WindowsDefaultPathExt : pathExtEnvironment;
            var extensions = source.Split(';').Where(e => e.Length > 0).ToList();
            files = extensions.Any(ext => command.ToLowerInvariant().EndsWith(ext.ToLowerInvariant(), StringComparison.Ordinal))
                ? [command]
                : extensions.Select(ext => command + ext).ToList();
        }

        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var directory in directories)
        {
            var normalized = windows ? directory.Replace('/', '\\').ToLowerInvariant() : directory;
            if (!seen.Add(normalized))
            {
                continue;
            }

            foreach (var file in files)
            {
                var candidate = OsPathJoin(directory, file, windows);
                if (isExecutableFile(candidate))
                {
                    return candidate;
                }
            }
        }

        return null;
    }

    /// <summary><c>os.path.join(directory, file)</c> for a relative file name.</summary>
    private static string OsPathJoin(string directory, string file, bool windows)
    {
        if (directory.Length == 0)
        {
            return file;
        }

        if (windows)
        {
            var last = directory[^1];
            var bareDrive = directory.Length == 2 && directory[1] == ':';
            return last is '\\' or '/' || bareDrive ? directory + file : directory + "\\" + file;
        }

        return directory.EndsWith('/') ? directory + file : directory + "/" + file;
    }
}
