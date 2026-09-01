using System.ComponentModel;
using System.Diagnostics;

using Xunit;

namespace MediaMop.Tray.Tests;

public sealed class BrowserLaunchTests : IDisposable
{
    private readonly string _home;
    private readonly string? _previousHome;

    public BrowserLaunchTests()
    {
        _home = Path.Combine(Path.GetTempPath(), "mediamop-tray-tests", Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(_home);
        _previousHome = Environment.GetEnvironmentVariable("MEDIAMOP_HOME");
        Environment.SetEnvironmentVariable("MEDIAMOP_HOME", _home);
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("MEDIAMOP_HOME", _previousHome);
        try { Directory.Delete(_home, recursive: true); } catch { }
    }

    [Fact]
    public void Browser_shell_failure_is_non_fatal_and_logged()
    {
        var result = Program.OpenBrowser(
            8788,
            _ => throw new Win32Exception(unchecked((int)0x80004021), "Shell execution unavailable"));

        Assert.False(result);
        var log = File.ReadAllText(Path.Combine(_home, "tray-host.log"));
        Assert.Contains("Could not open MediaMop in the browser", log);
        Assert.Contains("Shell execution unavailable", log);
    }

    [Fact]
    public void Browser_launch_uses_the_local_server_and_shell_execution()
    {
        ProcessStartInfo? observed = null;

        var result = Program.OpenBrowser(8788, info => observed = info);

        Assert.True(result);
        Assert.NotNull(observed);
        Assert.Equal("http://127.0.0.1:8788/", observed.FileName);
        Assert.True(observed.UseShellExecute);
    }
}
