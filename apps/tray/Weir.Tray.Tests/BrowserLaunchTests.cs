using System.ComponentModel;
using System.Diagnostics;

using Xunit;

namespace Weir.Tray.Tests;

public sealed class BrowserLaunchTests : IDisposable
{
    private readonly string _home;
    private readonly string? _previousHome;

    public BrowserLaunchTests()
    {
        _home = Path.Combine(Path.GetTempPath(), "weir-tray-tests", Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(_home);
        _previousHome = Environment.GetEnvironmentVariable("WEIR_HOME");
        Environment.SetEnvironmentVariable("WEIR_HOME", _home);
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("WEIR_HOME", _previousHome);
        try { Directory.Delete(_home, recursive: true); } catch { }
    }

    [Fact]
    public void Browser_shell_failure_is_non_fatal_and_logged()
    {
        var result = Program.OpenBrowser(
            9347,
            _ => throw new Win32Exception(unchecked((int)0x80004021), "Shell execution unavailable"));

        Assert.False(result);
        var log = File.ReadAllText(Path.Combine(_home, "tray-host.log"));
        Assert.Contains("Could not open Weir in the browser", log);
        Assert.Contains("Shell execution unavailable", log);
    }

    [Fact]
    public void Browser_launch_uses_the_local_server_and_shell_execution()
    {
        ProcessStartInfo? observed = null;

        var result = Program.OpenBrowser(9347, info => observed = info);

        Assert.True(result);
        Assert.NotNull(observed);
        Assert.Equal("http://127.0.0.1:9347/", observed.FileName);
        Assert.True(observed.UseShellExecute);
    }

    [Fact]
    public void Browser_launch_can_open_the_local_upgrade_settings_page()
    {
        ProcessStartInfo? observed = null;

        var result = Program.OpenBrowser(
            9347,
            info => observed = info,
            Program.UpgradeSettingsPath);

        Assert.True(result);
        Assert.NotNull(observed);
        Assert.Equal("http://127.0.0.1:9347/settings?tab=upgrade", observed.FileName);
        Assert.True(observed.UseShellExecute);
    }

    [Theory]
    [InlineData(true, null)]
    [InlineData(false, Program.UpgradeSettingsPath)]
    public void Update_menu_falls_back_to_the_web_upgrade_page_when_unmanaged(
        bool isInstalled,
        string? expectedPath)
    {
        Assert.Equal(expectedPath, Program.TrayUpdateFallbackPath(isInstalled));
    }
}
