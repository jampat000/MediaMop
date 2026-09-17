using Weir.Core.Media;

namespace Weir.Infrastructure.Media;

/// <summary>Finds ffprobe and ffmpeg (<c>resolve_ffprobe_ffmpeg</c>).</summary>
public interface IMediaToolResolver
{
    /// <summary>(ffprobe, ffmpeg) paths. Throws <see cref="MediaToolException"/> when either is missing.</summary>
    (string Ffprobe, string Ffmpeg) Resolve();

    /// <summary>
    /// #548: the mkvmerge path, or null when it is not installed. Unlike ffprobe and ffmpeg this is optional —
    /// Weir runs perfectly well without it, writing every container with ffmpeg — so a missing mkvmerge is a
    /// null rather than a <see cref="MediaToolException"/>, and the writer setting falls back accordingly.
    /// </summary>
    string? ResolveMkvmerge();
}

/// <summary>
/// Prefers <c>WEIR_FFMPEG_DIR</c>, then the tools bundled under the Weir home, then (packaged builds only) the
/// tools next to the executable, then PATH. The environment is read on every call, as the reference does.
/// </summary>
public sealed class MediaToolResolver : IMediaToolResolver
{
    private readonly string _weirHome;
    private readonly string? _packagedAppDirectory;
    private readonly Func<string, string?> _getEnvironmentVariable;
    private readonly bool _windows;

    /// <param name="weirHome">The Weir home directory.</param>
    /// <param name="packagedAppDirectory">The packaged app's directory, or null when not running packaged.</param>
    /// <param name="getEnvironmentVariable">Environment lookup; <see cref="Environment.GetEnvironmentVariable(string)"/> when null.</param>
    public MediaToolResolver(string weirHome, string? packagedAppDirectory = null, Func<string, string?>? getEnvironmentVariable = null)
    {
        ArgumentNullException.ThrowIfNull(weirHome);
        _weirHome = weirHome;
        _packagedAppDirectory = packagedAppDirectory;
        _getEnvironmentVariable = getEnvironmentVariable ?? Environment.GetEnvironmentVariable;
        _windows = OperatingSystem.IsWindows();
    }

    /// <summary>
    /// The resolver for this process: a single-file publish (the Windows package and the Docker image, .NET's
    /// equivalent of a frozen build) also looks in <c>&lt;app&gt;/bin/ffmpeg</c>, where the Windows package
    /// bundles ffmpeg and ffprobe.
    /// </summary>
    public static MediaToolResolver ForCurrentProcess(string weirHome) =>
        new(weirHome, string.IsNullOrEmpty(typeof(MediaToolResolver).Assembly.Location) ? AppContext.BaseDirectory : null);

    public (string Ffprobe, string Ffmpeg) Resolve()
    {
        var userHome = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var home = MediaToolLocations.Normalize(Path.GetFullPath(MediaToolLocations.ExpandUser(_weirHome, userHome, _windows)), _windows);
        var (ffprobeName, ffmpegName) = MediaToolLocations.ToolNames(_windows);
        var directories = MediaToolLocations.CandidateDirectories(
            home,
            _getEnvironmentVariable(MediaToolLocations.FfmpegDirEnvironmentVariable),
            userHome,
            _packagedAppDirectory,
            _windows);
        foreach (var directory in directories)
        {
            var ffprobe = MediaToolLocations.Join(_windows, directory, ffprobeName);
            var ffmpeg = MediaToolLocations.Join(_windows, directory, ffmpegName);
            if (File.Exists(ffprobe) && File.Exists(ffmpeg))
            {
                return (ffprobe, ffmpeg);
            }
        }

        var pathEnvironment = _getEnvironmentVariable("PATH");
        var pathExt = _getEnvironmentVariable("PATHEXT");
        var foundProbe = MediaToolLocations.Which("ffprobe", pathEnvironment, pathExt, _windows, IsExecutableFile);
        var foundMpeg = MediaToolLocations.Which("ffmpeg", pathEnvironment, pathExt, _windows, IsExecutableFile);
        if (foundProbe is null || foundMpeg is null)
        {
            throw new MediaToolException(MediaToolLocations.MissingToolsMessage);
        }

        return (foundProbe, foundMpeg);
    }

    /// <summary>
    /// #548: <c>WEIR_MKVTOOLNIX_DIR</c>, then the bundled MKVToolNix under the Weir home, then (packaged builds
    /// only) the one next to the executable, then PATH — the same order as <see cref="Resolve"/>, and read fresh
    /// on every call for the same reason. Null when mkvmerge is nowhere to be found.
    /// </summary>
    public string? ResolveMkvmerge()
    {
        var userHome = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var home = MediaToolLocations.Normalize(Path.GetFullPath(MediaToolLocations.ExpandUser(_weirHome, userHome, _windows)), _windows);
        var name = MediaToolLocations.MkvmergeToolName(_windows);
        var directories = MediaToolLocations.MkvtoolnixCandidateDirectories(
            home,
            _getEnvironmentVariable(MediaToolLocations.MkvtoolnixDirEnvironmentVariable),
            userHome,
            _packagedAppDirectory,
            _windows);
        foreach (var directory in directories)
        {
            var candidate = MediaToolLocations.Join(_windows, directory, name);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return MediaToolLocations.Which(
            "mkvmerge",
            _getEnvironmentVariable("PATH"),
            _getEnvironmentVariable("PATHEXT"),
            _windows,
            IsExecutableFile);
    }

    /// <summary><c>shutil._access_check</c>: exists, is not a directory, and (off Windows) is executable.</summary>
    private bool IsExecutableFile(string candidate)
    {
        if (!File.Exists(candidate))
        {
            return false;
        }

        if (_windows || OperatingSystem.IsWindows())
        {
            return true;
        }

        try
        {
            var mode = File.GetUnixFileMode(candidate);
            return (mode & (UnixFileMode.UserExecute | UnixFileMode.GroupExecute | UnixFileMode.OtherExecute)) != 0;
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
}
