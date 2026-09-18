using System.Diagnostics;

namespace Weir.Tray;

/// <summary>
/// Finding and stopping this install's own Weir processes — and only those.
///
/// The installer hooks used to kill every process named <c>Weir</c> or <c>WeirServer</c> on the
/// machine, matched by name alone. A machine can run more than one Weir — a second install, a
/// portable copy, a developer build, a soak rig kept alive by scheduled tasks — and installing or
/// uninstalling this one silently killed all of them. A process is now stopped only when its
/// executable is inside this install's directory. If its path cannot be read (access denied, a
/// different user's process, already gone) it is left alone: not knowing is not permission.
/// </summary>
static class InstallProcesses
{
    internal static readonly string[] Names = ["Weir", "WeirServer"];

    /// <summary>
    /// The directory this install runs from: the folder holding this Weir.exe. Velopack runs the
    /// app from <c>%LocalAppData%\Weir\current</c>, with the server under <c>current\server</c>,
    /// and runs its install and uninstall hooks from the same place.
    /// </summary>
    internal static string Root() => Normalize(AppContext.BaseDirectory);

    /// <summary>Full path, no trailing separator, for prefix comparison.</summary>
    internal static string Normalize(string path) =>
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));

    /// <summary>
    /// Whether <paramref name="executable"/> lives inside <paramref name="root"/>. A directory
    /// boundary is required, so <c>C:\Weir-old\Weir.exe</c> is not inside <c>C:\Weir</c>.
    /// </summary>
    internal static bool IsInside(string? executable, string root)
    {
        if (string.IsNullOrWhiteSpace(executable)) return false;
        string full;
        try { full = Path.GetFullPath(executable); } catch { return false; }
        var prefix = Normalize(root) + Path.DirectorySeparatorChar;
        return full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Stop every running Weir or WeirServer whose executable is inside <paramref name="root"/>,
    /// except this process. <paramref name="sameSessionOnly"/> narrows it to this Windows session.
    /// Everything else is logged and left running. Returns the ids stopped.
    /// </summary>
    internal static List<int> StopOwn(string root, bool sameSessionOnly, Action<string> log, string why)
    {
        var stopped = new List<int>();
        var self = Environment.ProcessId;
        int? session = null;
        if (sameSessionOnly)
        {
            try { session = Process.GetCurrentProcess().SessionId; } catch { return stopped; }
        }

        foreach (var name in Names)
        {
            foreach (var proc in Process.GetProcessesByName(name))
            {
                using (proc)
                {
                    if (proc.Id == self) continue;

                    string? path;
                    try
                    {
                        if (session is { } s && proc.SessionId != s) continue;
                        path = proc.MainModule?.FileName;
                    }
                    catch (Exception ex)
                    {
                        log($"{why}: left {name} (pid {proc.Id}) running: could not read where it runs from ({ex.Message}).");
                        continue;
                    }

                    if (!IsInside(path, root))
                    {
                        log($"{why}: left {name} (pid {proc.Id}) running: {path ?? "unknown path"} is not part of this install ({root}).");
                        continue;
                    }

                    try
                    {
                        proc.Kill(entireProcessTree: true);
                        proc.WaitForExit(5_000);
                        stopped.Add(proc.Id);
                        log($"{why}: stopped {name} (pid {proc.Id}) at {path}.");
                    }
                    catch (Exception ex)
                    {
                        log($"{why}: could not stop {name} (pid {proc.Id}) at {path}: {ex.Message}");
                    }
                }
            }
        }
        return stopped;
    }
}
