using System.Text.Json;

using Xunit;

namespace MediaMop.Tray.Tests;

/// <summary>
/// The tray is the component that actually installs an update, so what it reads out of
/// update-settings.json decides whether software lands on a machine unattended. These
/// tests exist because that read had no coverage at all while it silently escalated a
/// damaged file to Auto.
/// </summary>
public sealed class UpdateSettingsTests : IDisposable
{
    private readonly string _home;
    private readonly string? _previousHome;

    public UpdateSettingsTests()
    {
        _home = Path.Combine(Path.GetTempPath(), "mediamop-tray-tests", Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(_home);
        // Load logs through Program.RuntimeHome() on the failure path; point that at the
        // temp folder so a test can never append to a real install's tray-host.log.
        _previousHome = Environment.GetEnvironmentVariable("MEDIAMOP_HOME");
        Environment.SetEnvironmentVariable("MEDIAMOP_HOME", _home);
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("MEDIAMOP_HOME", _previousHome);
        try { Directory.Delete(_home, recursive: true); } catch { }
    }

    private string SettingsPath => Path.Combine(_home, "update-settings.json");

    [Fact]
    public void No_file_is_the_shipped_default()
    {
        var got = UpdateSettings.Load(_home);

        Assert.Equal(UpdateMode.Auto, got.Mode);
        Assert.True(got.CheckOnStartup);
        Assert.Equal(60, got.CheckIntervalMinutes);
    }

    [Fact]
    public void A_saved_choice_round_trips()
    {
        new UpdateSettings
        {
            Mode = UpdateMode.DownloadOnly,
            CheckOnStartup = false,
            CheckIntervalMinutes = 240,
        }.Save(_home);

        var got = UpdateSettings.Load(_home);

        Assert.Equal(UpdateMode.DownloadOnly, got.Mode);
        Assert.False(got.CheckOnStartup);
        Assert.Equal(240, got.CheckIntervalMinutes);
    }

    [Fact]
    public void A_truncated_file_falls_back_to_notify_only_not_to_auto()
    {
        // The operator chose something. Auto is the only mode that installs with nobody
        // watching, so it is the one guess that can act against that choice.
        new UpdateSettings { Mode = UpdateMode.NotifyOnly }.Save(_home);
        File.WriteAllText(SettingsPath, "{\"mode\": \"Notify");

        Assert.Equal(UpdateMode.NotifyOnly, UpdateSettings.Load(_home).Mode);
    }

    [Fact]
    public void An_unknown_mode_is_rejected_rather_than_defaulting_to_auto()
    {
        File.WriteAllText(SettingsPath, "{\"mode\": \"InstallEverythingNow\"}");

        Assert.Equal(UpdateMode.NotifyOnly, UpdateSettings.Load(_home).Mode);
    }

    [Fact]
    public void An_empty_file_falls_back_to_notify_only()
    {
        // Deserialize returns null for a bare "null" document rather than throwing, which
        // is the case the old `?? new UpdateSettings()` quietly turned into Auto.
        File.WriteAllText(SettingsPath, "null");

        Assert.Equal(UpdateMode.NotifyOnly, UpdateSettings.Load(_home).Mode);
    }

    [Fact]
    public void The_failure_path_says_why_in_the_tray_log()
    {
        File.WriteAllText(SettingsPath, "{ not json");

        UpdateSettings.Load(_home);

        var log = File.ReadAllText(Path.Combine(_home, "tray-host.log"));
        Assert.Contains("update-settings.json could not be read", log);
        Assert.Contains("NotifyOnly", log);
    }

    [Fact]
    public void A_stale_scratch_file_from_another_writer_is_not_touched()
    {
        // The backend writes this same file. Both used to pick the same scratch name, so one
        // could rename the other's half-written file into place and report success. The name
        // is unique per write now, which is why this pre-existing file survives untouched.
        // Planted at exactly the name the old code used, so this fails against it.
        var foreign = SettingsPath + ".tmp";
        File.WriteAllText(foreign, "{\"mode\": \"Auto\"}");

        new UpdateSettings { Mode = UpdateMode.NotifyOnly }.Save(_home);

        Assert.Equal(UpdateMode.NotifyOnly, UpdateSettings.Load(_home).Mode);
        Assert.True(File.Exists(foreign));
    }

    [Fact]
    public void The_file_is_replaced_whole_and_leaves_no_scratch_file()
    {
        new UpdateSettings { Mode = UpdateMode.DownloadOnly, CheckIntervalMinutes = 10080 }.Save(_home);
        new UpdateSettings { Mode = UpdateMode.Auto, CheckIntervalMinutes = 1 }.Save(_home);

        using var doc = JsonDocument.Parse(File.ReadAllText(SettingsPath));
        Assert.Equal("Auto", doc.RootElement.GetProperty("mode").GetString());
        Assert.Equal(1, doc.RootElement.GetProperty("checkIntervalMinutes").GetInt32());
        Assert.Empty(Directory.GetFiles(_home, "*.tmp"));
    }
}
