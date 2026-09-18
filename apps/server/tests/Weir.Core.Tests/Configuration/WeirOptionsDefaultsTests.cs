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
    public void Processing()
    {
        Assert.Equal(8, Defaults.ProcessingWorkerCount);
        Assert.Equal(300, Defaults.ProcessingJobLeaseSeconds);
        Assert.True(Defaults.ProcessingWatcherEnabled);
        Assert.Equal(3.0, Defaults.ProcessingWatcherDebounceSeconds);
        Assert.True(Defaults.ProcessingWatchedFolderRemuxScanDispatchScheduleEnabled);
        Assert.True(Defaults.ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs);
        Assert.Equal(10, Defaults.ProcessingProbeSizeMb);
        Assert.Equal(10, Defaults.ProcessingAnalyzeDurationSeconds);
        Assert.Equal(300, Defaults.ProcessingWatchedFolderMinFileAgeSeconds);
        Assert.Equal(48 * 3600, Defaults.ProcessingMovieOutputCleanupMinAgeSeconds);
        Assert.Equal(48 * 3600, Defaults.ProcessingTvOutputCleanupMinAgeSeconds);
        Assert.False(Defaults.ProcessingWorkTempStaleSweepMovieScheduleEnabled);
        Assert.Equal(3600, Defaults.ProcessingWorkTempStaleSweepMovieScheduleIntervalSeconds);
        Assert.False(Defaults.ProcessingWorkTempStaleSweepTvScheduleEnabled);
        Assert.Equal(3600, Defaults.ProcessingWorkTempStaleSweepTvScheduleIntervalSeconds);
        Assert.Equal(86_400, Defaults.ProcessingWorkTempStaleSweepMinStaleAgeSeconds);
        Assert.False(Defaults.ProcessingMovieFailureCleanupScheduleEnabled);
        Assert.Equal(3600, Defaults.ProcessingMovieFailureCleanupScheduleIntervalSeconds);
        Assert.False(Defaults.ProcessingTvFailureCleanupScheduleEnabled);
        Assert.Equal(3600, Defaults.ProcessingTvFailureCleanupScheduleIntervalSeconds);
        Assert.Equal(1800, Defaults.ProcessingMovieFailureCleanupGracePeriodSeconds);
        Assert.Equal(1800, Defaults.ProcessingTvFailureCleanupGracePeriodSeconds);
        Assert.Null(Defaults.ProcessingRemuxMediaRoot);
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

    /// <summary>#555: off, 1000/1000 and no modes until an operator sets WEIR_CHOWN_OUTPUT/WEIR_PUID/WEIR_PGID/WEIR_FILE_MODE_OUTPUT/WEIR_DIR_MODE_OUTPUT.</summary>
    [Fact]
    public void Output_ownership_is_off_by_default()
    {
        Assert.False(Defaults.OutputOwnershipChownEnabled);
        Assert.Equal(1000u, Defaults.OutputOwnershipUid);
        Assert.Equal(1000u, Defaults.OutputOwnershipGid);
        Assert.Null(Defaults.OutputOwnershipFileMode);
        Assert.Null(Defaults.OutputOwnershipDirectoryMode);
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
