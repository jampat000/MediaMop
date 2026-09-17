using Weir.Core.Configuration;

namespace Weir.Core.Tests.Configuration;

/// <summary>How each WEIR_* variable is read, clamped and validated, matching <c>WeirSettings.load()</c>.</summary>
public sealed class WeirOptionsParsingTests
{
    [Theory]
    [InlineData(" Production ", "production")]
    [InlineData("", "development")]
    [InlineData("   ", "")]
    public void Env_is_trimmed_and_lower_cased(string raw, string expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_ENV", raw)).Env);

    [Theory]
    [InlineData(" debug ", "debug")]
    [InlineData("", "INFO")]
    [InlineData("   ", "INFO")]
    public void Log_level_is_trimmed_with_info_fallback(string raw, string expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_LOG_LEVEL", raw)).LogLevel);

    [Fact]
    public void Secrets_are_trimmed_and_blank_means_unset()
    {
        var options = TestRuntime.Load(
            ("WEIR_SESSION_SECRET", "  s3cret  "),
            ("WEIR_CREDENTIALS_SECRET", "   "),
            ("WEIR_METRICS_BEARER_TOKEN", " token "));
        Assert.Equal("s3cret", options.SessionSecret);
        Assert.Null(options.CredentialsSecret);
        Assert.Equal("token", options.MetricsBearerToken);
    }

    [Fact]
    public void Previous_credentials_secrets_drop_blanks_and_the_current_secret()
    {
        var options = TestRuntime.Load(
            ("WEIR_CREDENTIALS_SECRET", "current"),
            ("WEIR_PREVIOUS_CREDENTIALS_SECRETS", " old1 , ,current, old2 "));
        Assert.Equal(["old1", "old2"], options.PreviousCredentialsSecrets);
    }

    [Theory]
    [InlineData("  my_cookie ", "my_cookie")]
    [InlineData("   ", "weir_session")]
    public void Cookie_name(string raw, string expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_SESSION_COOKIE_NAME", raw)).SessionCookieName);

    [Theory]
    [InlineData("Strict", CookieSameSite.Strict)]
    [InlineData(" none ", CookieSameSite.None)]
    [InlineData("lax", CookieSameSite.Lax)]
    [InlineData("bogus", CookieSameSite.Lax)]
    [InlineData("", CookieSameSite.Lax)]
    public void Cookie_samesite(string raw, CookieSameSite expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_SESSION_COOKIE_SAMESITE", raw)).SessionCookieSameSite);

    [Theory]
    [InlineData("1", CookieSecureMode.Always)]
    [InlineData("TRUE", CookieSecureMode.Always)]
    [InlineData("yes", CookieSecureMode.Always)]
    [InlineData("on", CookieSecureMode.Always)]
    [InlineData("always", CookieSecureMode.Always)]
    [InlineData("0", CookieSecureMode.Never)]
    [InlineData("false", CookieSecureMode.Never)]
    [InlineData("no", CookieSecureMode.Never)]
    [InlineData("off", CookieSecureMode.Never)]
    [InlineData(" never ", CookieSecureMode.Never)]
    [InlineData("auto", CookieSecureMode.Auto)]
    [InlineData("maybe", CookieSecureMode.Auto)]
    public void Cookie_secure_mode(string raw, CookieSecureMode expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_SESSION_COOKIE_SECURE", raw)).SessionCookieSecureMode);

    [Fact]
    public void Session_lifetimes_have_a_floor_of_one()
    {
        var options = TestRuntime.Load(
            ("WEIR_SESSION_IDLE_MINUTES", "0"),
            ("WEIR_SESSION_ABSOLUTE_DAYS", "-4"),
            ("WEIR_SESSION_TRUSTED_IDLE_DAYS", "-1"),
            ("WEIR_SESSION_TRUSTED_ABSOLUTE_DAYS", "0"));
        Assert.Equal(1, options.SessionIdleMinutes);
        Assert.Equal(1, options.SessionAbsoluteDays);
        Assert.Equal(1440, options.SessionTrustedIdleMinutes);
        Assert.Equal(1, options.SessionTrustedAbsoluteDays);
    }

    [Fact]
    public void Trusted_idle_days_become_minutes()
    {
        Assert.Equal(2 * 1440, TestRuntime.Load(("WEIR_SESSION_TRUSTED_IDLE_DAYS", "2")).SessionTrustedIdleMinutes);
    }

    [Fact]
    public void Rate_limits_have_a_floor_of_one()
    {
        var options = TestRuntime.Load(
            ("WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "0"),
            ("WEIR_AUTH_LOGIN_RATE_WINDOW_SECONDS", "-1"),
            ("WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS", "5"),
            ("WEIR_BOOTSTRAP_RATE_WINDOW_SECONDS", "0"));
        Assert.Equal(1, options.AuthLoginRateMaxAttempts);
        Assert.Equal(1, options.AuthLoginRateWindowSeconds);
        Assert.Equal(5, options.BootstrapRateMaxAttempts);
        Assert.Equal(1, options.BootstrapRateWindowSeconds);
    }

    [Theory]
    [InlineData("1", true)]
    [InlineData(" Yes ", true)]
    [InlineData("on", true)]
    [InlineData("true", true)]
    [InlineData("0", false)]
    [InlineData("no", false)]
    [InlineData("junk", false)]
    public void Hsts_boolean(string raw, bool expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_SECURITY_ENABLE_HSTS", raw)).SecurityEnableHsts);

    [Fact]
    public void Unparseable_booleans_keep_their_default()
    {
        Assert.True(TestRuntime.Load(("WEIR_REFINER_WATCHER_ENABLED", "perhaps")).RefinerWatcherEnabled);
        Assert.False(TestRuntime.Load(("WEIR_REFINER_WATCHER_ENABLED", "off")).RefinerWatcherEnabled);
    }

    [Theory]
    [InlineData("12", 12)]
    [InlineData(" +7 ", 7)]
    [InlineData("1_0", 10)]
    [InlineData("1.5", 10)]
    [InlineData("ten", 10)]
    [InlineData("", 10)]
    [InlineData("1__0", 10)]
    public void Integers_parse_like_python_int_and_fall_back_to_the_default(string raw, int expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_REFINER_PROBE_SIZE_MB", raw)).RefinerProbeSizeMb);

    [Fact]
    public void Webhook_secret_prefers_the_new_name_then_the_legacy_one()
    {
        Assert.Equal("new", TestRuntime.Load(("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", " new "), ("WEIR_SUBBER_WEBHOOK_SECRET", "old")).MediaManagerWebhookSecret);
        Assert.Equal("old", TestRuntime.Load(("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", ""), ("WEIR_SUBBER_WEBHOOK_SECRET", " old ")).MediaManagerWebhookSecret);
        // Python's `a or b`: a whitespace-only new value is truthy, so the legacy one is never read.
        Assert.Null(TestRuntime.Load(("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET", "  "), ("WEIR_SUBBER_WEBHOOK_SECRET", "old")).MediaManagerWebhookSecret);
    }

    [Fact]
    public void Cors_wildcard_is_refused_with_the_python_message()
    {
        var error = Assert.Throws<WeirConfigurationException>(() => TestRuntime.Load(("WEIR_ENV", "production"), ("WEIR_CORS_ORIGINS", "https://a.example, *")));
        Assert.Equal(
            "WEIR_CORS_ORIGINS cannot include '*' because Weir uses credentialed browser requests. Configure explicit origins instead.",
            error.Message);
        Assert.Throws<WeirConfigurationException>(() => TestRuntime.Load(("WEIR_CORS_ORIGINS", "*")));
    }

    [Fact]
    public void Cors_origins_are_split_and_trimmed_without_expansion_outside_development()
    {
        var options = TestRuntime.Load(("WEIR_ENV", "production"), ("WEIR_CORS_ORIGINS", " http://localhost:8782/ , ,https://weir.example "));
        Assert.Equal(["http://localhost:8782/", "https://weir.example"], options.CorsOrigins);
    }

    [Fact]
    public void Development_adds_the_other_loopback_hostname()
    {
        var options = TestRuntime.Load(
            ("WEIR_CORS_ORIGINS", "http://localhost:8782/,https://127.0.0.1,http://weir.lan:1"),
            ("WEIR_TRUSTED_BROWSER_ORIGINS", "HTTP://LOCALHOST:9"));
        Assert.Equal(
            ["http://localhost:8782", "http://127.0.0.1:8782", "https://127.0.0.1", "https://localhost", "http://weir.lan:1"],
            options.CorsOrigins);
        Assert.Equal(["HTTP://LOCALHOST:9", "http://127.0.0.1:9"], options.TrustedBrowserOriginsOverride);
    }

    [Fact]
    public void Development_expansion_fails_on_an_invalid_port_like_python()
    {
        var notNumber = Assert.Throws<WeirConfigurationException>(() => TestRuntime.Load(("WEIR_CORS_ORIGINS", "http://localhost:abc")));
        Assert.Equal("Port could not be cast to integer value as 'abc'", notNumber.Message);
        var outOfRange = Assert.Throws<WeirConfigurationException>(() => TestRuntime.Load(("WEIR_CORS_ORIGINS", "http://localhost:70000")));
        Assert.Equal("Port out of range 0-65535", outOfRange.Message);
    }

    [Fact]
    public void Trusted_browser_origins_fall_back_to_cors()
    {
        Assert.Equal(["https://a.example"], TestRuntime.Load(("WEIR_ENV", "production"), ("WEIR_CORS_ORIGINS", "https://a.example")).TrustedBrowserOrigins);
        Assert.Equal(
            ["https://b.example"],
            TestRuntime.Load(("WEIR_ENV", "production"), ("WEIR_CORS_ORIGINS", "https://a.example"), ("WEIR_TRUSTED_BROWSER_ORIGINS", "https://b.example")).TrustedBrowserOrigins);
    }

    [Fact]
    public void Trusted_proxy_ips_are_a_csv_list()
    {
        Assert.Equal(["10.0.0.0/8", "::1"], TestRuntime.Load(("WEIR_TRUSTED_PROXY_IPS", "10.0.0.0/8, ::1,")).TrustedProxyIps);
    }

    [Theory]
    [InlineData("-3", 1)]
    [InlineData("0", 0)]
    [InlineData("5", 5)]
    [InlineData("99", 8)]
    public void Refiner_worker_count_is_zero_to_eight_and_negative_means_one(string raw, int expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_REFINER_WORKER_COUNT", raw)).RefinerWorkerCount);

    [Theory]
    [InlineData("1", 30)]
    [InlineData("0", 30)]
    [InlineData("-5", 30)]
    [InlineData("120", 120)]
    [InlineData("999999", 86_400)]
    public void Refiner_job_lease_seconds_is_thirty_seconds_to_a_day(string raw, int expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_REFINER_JOB_LEASE_SECONDS", raw)).RefinerJobLeaseSeconds);

    [Theory]
    [InlineData("0", 0.25)]
    [InlineData("10", 10.0)]
    [InlineData("1000", 300.0)]
    [InlineData("2.5", 3.0)]
    public void Watcher_debounce_is_a_whole_number_clamped_to_a_quarter_second_through_five_minutes(string raw, double expected) =>
        Assert.Equal(expected, TestRuntime.Load(("WEIR_REFINER_WATCHER_DEBOUNCE_SECONDS", raw)).RefinerWatcherDebounceSeconds);

    [Fact]
    public void Refiner_ranges_are_clamped()
    {
        var low = TestRuntime.Load(
            ("WEIR_REFINER_PROBE_SIZE_MB", "0"),
            ("WEIR_REFINER_ANALYZE_DURATION_SECONDS", "0"),
            ("WEIR_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "-1"),
            ("WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS", "1"),
            ("WEIR_REFINER_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS", "1"),
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_MIN_STALE_AGE_SECONDS", "1"),
            ("WEIR_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", "1"),
            ("WEIR_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", "1"),
            ("WEIR_REFINER_MOVIE_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", "1"),
            ("WEIR_REFINER_TV_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", "1"),
            ("WEIR_JOB_ROWS_RETENTION_DAYS", "0"),
            ("WEIR_JOB_ROWS_RETENTION_SCHEDULE_INTERVAL_SECONDS", "1"));
        Assert.Equal(1, low.RefinerProbeSizeMb);
        Assert.Equal(1, low.RefinerAnalyzeDurationSeconds);
        Assert.Equal(0, low.RefinerWatchedFolderMinFileAgeSeconds);
        Assert.Equal(3600, low.RefinerMovieOutputCleanupMinAgeSeconds);
        Assert.Equal(3600, low.RefinerTvOutputCleanupMinAgeSeconds);
        Assert.Equal(60, low.RefinerWorkTempStaleSweepMinStaleAgeSeconds);
        Assert.Equal(60, low.RefinerMovieFailureCleanupScheduleIntervalSeconds);
        Assert.Equal(60, low.RefinerTvFailureCleanupScheduleIntervalSeconds);
        Assert.Equal(300, low.RefinerMovieFailureCleanupGracePeriodSeconds);
        Assert.Equal(300, low.RefinerTvFailureCleanupGracePeriodSeconds);
        Assert.Equal(1, low.JobRowsRetentionDays);
        Assert.Equal(60, low.JobRowsRetentionScheduleIntervalSeconds);

        var high = TestRuntime.Load(
            ("WEIR_REFINER_PROBE_SIZE_MB", "99999"),
            ("WEIR_REFINER_ANALYZE_DURATION_SECONDS", "99999"),
            ("WEIR_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "99999999"),
            ("WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS", "99999999"),
            ("WEIR_REFINER_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS", "99999999"),
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_MIN_STALE_AGE_SECONDS", "99999999"),
            ("WEIR_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", "99999999"),
            ("WEIR_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", "99999999"),
            ("WEIR_REFINER_MOVIE_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", "99999999"),
            ("WEIR_REFINER_TV_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", "99999999"),
            ("WEIR_JOB_ROWS_RETENTION_DAYS", "99999"),
            ("WEIR_JOB_ROWS_RETENTION_SCHEDULE_INTERVAL_SECONDS", "99999999"));
        Assert.Equal(1024, high.RefinerProbeSizeMb);
        Assert.Equal(300, high.RefinerAnalyzeDurationSeconds);
        Assert.Equal(7 * 24 * 3600, high.RefinerWatchedFolderMinFileAgeSeconds);
        Assert.Equal(30 * 24 * 3600, high.RefinerMovieOutputCleanupMinAgeSeconds);
        Assert.Equal(30 * 24 * 3600, high.RefinerTvOutputCleanupMinAgeSeconds);
        Assert.Equal(30 * 24 * 3600, high.RefinerWorkTempStaleSweepMinStaleAgeSeconds);
        Assert.Equal(7 * 24 * 3600, high.RefinerMovieFailureCleanupScheduleIntervalSeconds);
        Assert.Equal(7 * 24 * 3600, high.RefinerTvFailureCleanupScheduleIntervalSeconds);
        Assert.Equal(604800, high.RefinerMovieFailureCleanupGracePeriodSeconds);
        Assert.Equal(604800, high.RefinerTvFailureCleanupGracePeriodSeconds);
        Assert.Equal(365, high.JobRowsRetentionDays);
        Assert.Equal(86400, high.JobRowsRetentionScheduleIntervalSeconds);
    }

    [Fact]
    public void Refiner_toggles_are_read()
    {
        var options = TestRuntime.Load(
            ("WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS", "false"),
            ("WEIR_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED", "true"),
            ("WEIR_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED", "1"));
        Assert.False(options.RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs);
        Assert.True(options.RefinerMovieFailureCleanupScheduleEnabled);
        Assert.True(options.RefinerTvFailureCleanupScheduleEnabled);
    }

    [Fact]
    public void Temp_sweep_schedule_falls_back_to_the_legacy_shared_variables()
    {
        var legacy = TestRuntime.Load(
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_ENABLED", "true"),
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_INTERVAL_SECONDS", "7200"));
        Assert.True(legacy.RefinerWorkTempStaleSweepMovieScheduleEnabled);
        Assert.True(legacy.RefinerWorkTempStaleSweepTvScheduleEnabled);
        Assert.Equal(7200, legacy.RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds);
        Assert.Equal(7200, legacy.RefinerWorkTempStaleSweepTvScheduleIntervalSeconds);

        var specific = TestRuntime.Load(
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_ENABLED", "true"),
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_INTERVAL_SECONDS", "7200"),
            // Present but empty still wins over the legacy variable, as `key in os.environ` does.
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED", ""),
            ("WEIR_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_INTERVAL_SECONDS", "30"));
        Assert.False(specific.RefinerWorkTempStaleSweepMovieScheduleEnabled);
        Assert.True(specific.RefinerWorkTempStaleSweepTvScheduleEnabled);
        Assert.Equal(7200, specific.RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds);
        Assert.Equal(60, specific.RefinerWorkTempStaleSweepTvScheduleIntervalSeconds);
    }

    [Fact]
    public void Remux_media_root_is_expanded_and_normalized_but_not_resolved()
    {
        var runtime = TestRuntime.With(("WEIR_REFINER_REMUX_MEDIA_ROOT", " ~/media//movies/ "));
        var expected = PythonCompat.NormalizeLexically(Path.Join(runtime.UserHomeDirectory, "media//movies/"), runtime);
        Assert.Equal(expected, WeirOptionsLoader.Load(runtime).RefinerRemuxMediaRoot);
        Assert.Equal(
            PythonCompat.NormalizeLexically("relative/./media", runtime),
            TestRuntime.Load(("WEIR_REFINER_REMUX_MEDIA_ROOT", "relative/./media")).RefinerRemuxMediaRoot);
    }

    [Fact]
    public void Arr_base_urls_must_be_http_and_keys_are_trimmed()
    {
        var options = TestRuntime.Load(
            ("WEIR_ARR_RADARR_BASE_URL", " http://radarr:7878 "),
            ("WEIR_ARR_RADARR_API_KEY", " key1 "),
            ("WEIR_ARR_SONARR_BASE_URL", "sonarr:8989"),
            ("WEIR_ARR_SONARR_API_KEY", " "));
        Assert.Equal("http://radarr:7878", options.ArrRadarrBaseUrl);
        Assert.Equal("key1", options.ArrRadarrApiKey);
        Assert.Null(options.ArrSonarrBaseUrl);
        Assert.Null(options.ArrSonarrApiKey);
        Assert.Null(TestRuntime.Load(("WEIR_ARR_RADARR_BASE_URL", "HTTP://upper")).ArrRadarrBaseUrl);
    }

    [Fact]
    public void Path_overrides_resolve_relative_to_home_and_expand_tilde()
    {
        var runtime = TestRuntime.With(
            ("WEIR_DB_PATH", "db/custom.sqlite3"),
            ("WEIR_BACKUP_DIR", "~/weir-backups"),
            ("WEIR_LOG_DIR", Path.Join(Path.GetTempPath(), "abs-logs") + Path.DirectorySeparatorChar),
            ("WEIR_TEMP_DIR", "  "));
        var options = WeirOptionsLoader.Load(runtime);
        Assert.Equal(Path.GetFullPath(Path.Join(options.WeirHome, "db", "custom.sqlite3")), options.DbPath);
        Assert.Equal(Path.GetFullPath(Path.Join(runtime.UserHomeDirectory, "weir-backups")), options.BackupDir);
        Assert.Equal(Path.GetFullPath(Path.Join(Path.GetTempPath(), "abs-logs")), options.LogDir);
        Assert.Equal(Path.GetFullPath(Path.Join(options.WeirHome, "temp")), options.TempDir);
    }

    [Fact]
    public void Relative_home_resolves_against_the_working_directory()
    {
        var runtime = TestRuntime.With(("WEIR_HOME", " relative-home "));
        Assert.Equal(Path.GetFullPath(Path.Join(runtime.CurrentDirectory, "relative-home")), WeirOptionsLoader.Load(runtime).WeirHome);
    }

    [Fact]
    public void Web_dist_and_version_override()
    {
        var runtime = TestRuntime.With(("WEIR_WEB_DIST", " ~/web/dist/ "), ("WEIR_VERSION", " 9.9.9 "));
        var options = WeirOptionsLoader.Load(runtime);
        Assert.Equal(Path.GetFullPath(Path.Join(runtime.UserHomeDirectory, "web", "dist")), options.WebDist);
        Assert.Equal("9.9.9", options.VersionOverride);
        Assert.Equal("9.9.9", WeirVersion.Resolve(options.VersionOverride));
        Assert.Equal(WeirVersion.BuildVersion, WeirVersion.Resolve(null));
    }
}
