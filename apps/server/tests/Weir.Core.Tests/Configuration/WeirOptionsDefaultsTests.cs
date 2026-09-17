using Weir.Core.Configuration;

namespace Weir.Core.Tests.Configuration;

/// <summary>Every default <c>WeirSettings.load()</c> produces with no WEIR_* variables set.</summary>
public sealed class WeirOptionsDefaultsTests
{
    private static readonly WeirOptions Defaults = TestRuntime.Load();

    [Fact]
    public void Environment_log_level_and_secrets()
    {
        Assert.Equal("development", Defaults.Env);
        Assert.Equal("INFO", Defaults.LogLevel);
        Assert.Null(Defaults.SessionSecret);
        Assert.Null(Defaults.CredentialsSecret);
        Assert.Empty(Defaults.PreviousCredentialsSecrets);
        Assert.Null(Defaults.MetricsBearerToken);
        Assert.Null(Defaults.MediaManagerWebhookSecret);
        Assert.Null(Defaults.VersionOverride);
        Assert.Null(Defaults.WebDist);
    }

    [Fact]
    public void Sessions_and_cookies()
    {
        Assert.Equal("weir_session", Defaults.SessionCookieName);
        Assert.Equal(CookieSecureMode.Auto, Defaults.SessionCookieSecureMode);
        Assert.Equal(CookieSameSite.Lax, Defaults.SessionCookieSameSite);
        Assert.Equal(20160, Defaults.SessionIdleMinutes);
        Assert.Equal(90, Defaults.SessionAbsoluteDays);
        Assert.Equal(60 * 1440, Defaults.SessionTrustedIdleMinutes);
        Assert.Equal(365, Defaults.SessionTrustedAbsoluteDays);
    }

    [Fact]
    public void Browser_origins_proxies_and_rate_limits()
    {
        Assert.Empty(Defaults.CorsOrigins);
        Assert.Empty(Defaults.TrustedBrowserOriginsOverride);
        Assert.Empty(Defaults.TrustedBrowserOrigins);
        Assert.Empty(Defaults.TrustedProxyIps);
        Assert.Equal(10, Defaults.AuthLoginRateMaxAttempts);
        Assert.Equal(60, Defaults.AuthLoginRateWindowSeconds);
        Assert.Equal(10, Defaults.BootstrapRateMaxAttempts);
        Assert.Equal(3600, Defaults.BootstrapRateWindowSeconds);
        Assert.False(Defaults.SecurityEnableHsts);
    }

    [Fact]
    public void Runtime_paths_live_under_home()
    {
        var home = Path.Join(Path.GetTempPath(), "weir-core-tests", "home");
        Assert.Equal(Path.GetFullPath(home), Defaults.WeirHome);
        Assert.Equal(Path.GetFullPath(Path.Join(home, "data", "weir.sqlite3")), Defaults.DbPath);
        Assert.Equal(Path.GetFullPath(Path.Join(home, "backups")), Defaults.BackupDir);
        Assert.Equal(Path.GetFullPath(Path.Join(home, "logs")), Defaults.LogDir);
        Assert.Equal(Path.GetFullPath(Path.Join(home, "temp")), Defaults.TempDir);
    }

    [Fact]
    public void Refiner()
    {
        Assert.Equal(8, Defaults.RefinerWorkerCount);
        Assert.Equal(300, Defaults.RefinerJobLeaseSeconds);
        Assert.True(Defaults.RefinerWatcherEnabled);
        Assert.Equal(3.0, Defaults.RefinerWatcherDebounceSeconds);
        Assert.True(Defaults.RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs);
        Assert.Equal(10, Defaults.RefinerProbeSizeMb);
        Assert.Equal(10, Defaults.RefinerAnalyzeDurationSeconds);
        Assert.Equal(300, Defaults.RefinerWatchedFolderMinFileAgeSeconds);
        Assert.Equal(48 * 3600, Defaults.RefinerMovieOutputCleanupMinAgeSeconds);
        Assert.Equal(48 * 3600, Defaults.RefinerTvOutputCleanupMinAgeSeconds);
        Assert.False(Defaults.RefinerWorkTempStaleSweepMovieScheduleEnabled);
        Assert.Equal(3600, Defaults.RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds);
        Assert.False(Defaults.RefinerWorkTempStaleSweepTvScheduleEnabled);
        Assert.Equal(3600, Defaults.RefinerWorkTempStaleSweepTvScheduleIntervalSeconds);
        Assert.Equal(86_400, Defaults.RefinerWorkTempStaleSweepMinStaleAgeSeconds);
        Assert.False(Defaults.RefinerMovieFailureCleanupScheduleEnabled);
        Assert.Equal(3600, Defaults.RefinerMovieFailureCleanupScheduleIntervalSeconds);
        Assert.False(Defaults.RefinerTvFailureCleanupScheduleEnabled);
        Assert.Equal(3600, Defaults.RefinerTvFailureCleanupScheduleIntervalSeconds);
        Assert.Equal(1800, Defaults.RefinerMovieFailureCleanupGracePeriodSeconds);
        Assert.Equal(1800, Defaults.RefinerTvFailureCleanupGracePeriodSeconds);
        Assert.Null(Defaults.RefinerRemuxMediaRoot);
    }

    [Fact]
    public void Job_retention_and_arr()
    {
        Assert.Equal(90, Defaults.JobRowsRetentionDays);
        Assert.Equal(3600, Defaults.JobRowsRetentionScheduleIntervalSeconds);
        Assert.Null(Defaults.ArrRadarrBaseUrl);
        Assert.Null(Defaults.ArrRadarrApiKey);
        Assert.Null(Defaults.ArrSonarrBaseUrl);
        Assert.Null(Defaults.ArrSonarrApiKey);
    }

    [Fact]
    public void Default_home_on_windows_is_programdata_weir()
    {
        Assert.Equal(Path.Join(@"C:\ProgramData", "Weir"), RuntimePaths.DefaultHome(TestRuntime.Bare(isWindows: true)));
        Assert.Equal(Path.Join(@"D:\Data", "Weir"), RuntimePaths.DefaultHome(TestRuntime.Bare(isWindows: true, ("PROGRAMDATA", @" D:\Data "))));
        Assert.Equal(Path.Join(@"C:\ProgramData", "Weir"), RuntimePaths.DefaultHome(TestRuntime.Bare(isWindows: true, ("PROGRAMDATA", ""))));
    }

    [Fact]
    public void Default_home_elsewhere_is_xdg_data_home_then_local_share()
    {
        var bare = TestRuntime.Bare(isWindows: false);
        Assert.Equal(Path.Join(bare.UserHomeDirectory, ".local", "share", "weir"), RuntimePaths.DefaultHome(bare));
        Assert.Equal(Path.Join("/srv/xdg", "weir"), RuntimePaths.DefaultHome(TestRuntime.Bare(isWindows: false, ("XDG_DATA_HOME", "/srv/xdg"))));
        Assert.Equal(Path.Join(bare.UserHomeDirectory, ".local", "share", "weir"), RuntimePaths.DefaultHome(TestRuntime.Bare(isWindows: false, ("XDG_DATA_HOME", "  "))));
    }

    [Fact]
    public void Unset_home_uses_the_os_default()
    {
        var runtime = TestRuntime.Bare(OperatingSystem.IsWindows());
        var options = WeirOptionsLoader.Load(runtime);
        Assert.Equal(Path.GetFullPath(RuntimePaths.DefaultHome(runtime)), options.WeirHome);
    }
}
