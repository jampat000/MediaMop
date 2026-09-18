using System.Diagnostics;

using Xunit;

namespace Weir.Tray.Tests;

/// <summary>
/// The install and uninstall hooks used to kill every process named Weir or WeirServer on the
/// machine. A machine can run more than one Weir, so they must stop only this install's own.
/// </summary>
public sealed class InstallProcessesTests : IDisposable
{
    private readonly string _root;
    private readonly List<Process> _started = [];

    public InstallProcessesTests()
    {
        _root = Path.Combine(Path.GetTempPath(), "weir-tray-tests", Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(_root);
    }

    public void Dispose()
    {
        foreach (var p in _started)
        {
            try { if (!p.HasExited) p.Kill(entireProcessTree: true); p.WaitForExit(5_000); } catch { }
            p.Dispose();
        }
        try { Directory.Delete(_root, recursive: true); } catch { }
    }

    [Theory]
    [InlineData(@"C:\Users\a\AppData\Local\Weir\current\Weir.exe", @"C:\Users\a\AppData\Local\Weir\current", true)]
    [InlineData(@"C:\Users\a\AppData\Local\Weir\current\server\WeirServer.exe", @"C:\Users\a\AppData\Local\Weir\current\", true)]
    [InlineData(@"c:\users\A\appdata\local\weir\CURRENT\server\weirserver.exe", @"C:\Users\a\AppData\Local\Weir\current", true)]
    [InlineData(@"C:\Deluno\Weir\app\current\server\WeirServer.exe", @"C:\Users\a\AppData\Local\Weir\current", false)]
    [InlineData(@"C:\Weir-old\Weir.exe", @"C:\Weir", false)]
    [InlineData(@"C:\Weir\..\Other\Weir.exe", @"C:\Weir", false)]
    [InlineData(@"C:\Weir", @"C:\Weir", false)]
    [InlineData(null, @"C:\Weir", false)]
    [InlineData("", @"C:\Weir", false)]
    public void Only_paths_inside_the_install_count(string? executable, string root, bool expected)
    {
        Assert.Equal(expected, InstallProcesses.IsInside(executable, root));
    }

    /// <summary>
    /// A real process named WeirServer inside the install root, and another outside it. Only the
    /// one inside is stopped. (ping.exe, copied and renamed, stands in for the server: it stays
    /// alive long enough and needs nothing else.)
    /// </summary>
    [Fact]
    public void Stops_this_installs_server_and_leaves_another_weir_running()
    {
        var install = Path.Combine(_root, "install", "current");
        var elsewhere = Path.Combine(_root, "Deluno", "Weir", "app", "current");
        var inside = StartFakeServer(Path.Combine(install, "server"));
        var outside = StartFakeServer(Path.Combine(elsewhere, "server"));
        var log = new List<string>();

        var stopped = InstallProcesses.StopOwn(install, sameSessionOnly: false, log.Add, "test");

        Assert.Contains(inside.Id, stopped);
        Assert.DoesNotContain(outside.Id, stopped);
        Assert.True(inside.WaitForExit(5_000), "the install's own server should have been stopped");
        Assert.False(outside.HasExited, "a Weir outside this install must be left running");
        Assert.Contains(log, line => line.Contains($"pid {outside.Id}") && line.Contains("not part of this install"));
    }

    private Process StartFakeServer(string directory)
    {
        Directory.CreateDirectory(directory);
        var exe = Path.Combine(directory, "WeirServer.exe");
        File.Copy(Path.Combine(Environment.SystemDirectory, "PING.EXE"), exe);
        var p = Process.Start(new ProcessStartInfo(exe, "-n 120 127.0.0.1")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
        })!;
        _started.Add(p);
        Assert.False(p.WaitForExit(500), "the stand-in server exited immediately");
        return p;
    }
}
