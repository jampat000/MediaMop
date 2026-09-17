using Weir.Core.Activity;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Logs;
using Weir.Core.Metrics;
using Weir.Core.Net;
using Weir.Core.Notifications;
using Weir.Core.Observability;
using Weir.Core.Settings;
using Weir.Core.Time;
using Weir.Core.Updates;

namespace Weir.Core.Tests.Platform;

/// <summary>Ports of the backend's unit tests for sessions, rate limits, settings, observability, metrics, logs and updates.</summary>
public sealed class PlatformRulesTests
{
    private static readonly WeirOptions Options = TestRuntime.Load();

    [Theory]
    [InlineData("http", CookieSecureMode.Auto, false)]
    [InlineData("https", CookieSecureMode.Auto, true)]
    [InlineData("http", CookieSecureMode.Always, true)]
    [InlineData("https", CookieSecureMode.Always, true)]
    [InlineData("http", CookieSecureMode.Never, false)]
    [InlineData("https", CookieSecureMode.Never, false)]
    [InlineData("HTTPS", CookieSecureMode.Auto, true)]
    [InlineData("", CookieSecureMode.Auto, false)]
    public void Cookie_secure_flag_follows_the_mode_and_scheme(string scheme, CookieSecureMode mode, bool expected) =>
        Assert.Equal(expected, SessionRules.ResolveCookieSecure(scheme, mode));

    [Fact]
    public void Session_validity_checks_revocation_absolute_expiry_then_idle()
    {
        var now = new DateTime(2026, 1, 15, 10, 0, 0, DateTimeKind.Utc);
        var row = Session(now, absolute: now.AddHours(1), lastSeen: now);
        Assert.Null(SessionRules.InvalidReason(row, TimeSpan.FromHours(12), now));
        Assert.Equal(SessionInvalidReason.Revoked, SessionRules.InvalidReason(row with { RevokedAt = PyDateTime.FromUtc(now) }, TimeSpan.FromHours(12), now));
        Assert.Equal(SessionInvalidReason.AbsoluteExpired, SessionRules.InvalidReason(Session(now, now.AddSeconds(-1), now.AddHours(-24)), TimeSpan.FromHours(12), now));
        Assert.Equal(SessionInvalidReason.AbsoluteExpired, SessionRules.InvalidReason(Session(now, now, now), TimeSpan.FromHours(12), now));
        Assert.Equal(SessionInvalidReason.IdleExpired, SessionRules.InvalidReason(Session(now, now.AddDays(7), now.AddHours(-13)), TimeSpan.FromHours(12), now));
        Assert.Null(SessionRules.InvalidReason(Session(now, now.AddDays(7), now.AddHours(-12)), TimeSpan.FromHours(12), now));
    }

    [Fact]
    public void Last_seen_is_touched_at_most_once_a_minute_or_half_the_idle_window() =>
        Assert.Equal(
            [TimeSpan.FromSeconds(60), TimeSpan.FromSeconds(30)],
            new[] { SessionRules.LastSeenTouchGap(TimeSpan.FromHours(12)), SessionRules.LastSeenTouchGap(TimeSpan.FromMinutes(1)) });

    [Theory]
    [InlineData("Mozilla/5.0 (Windows NT 10.0) Chrome/120.0", "Chrome on Windows")]
    [InlineData("Mozilla/5.0 (Macintosh; Mac OS X) Safari/605", "Safari on macOS")]
    [InlineData("Mozilla/5.0 (X11; Linux) Firefox/120", "Firefox on Linux")]
    [InlineData("Mozilla/5.0 (Windows NT 10.0) Chrome/120 Edg/120", "Edge on Windows")]
    [InlineData("Weir Electron/30", "Weir app on device")]
    [InlineData(null, "Browser on device")]
    public void Session_labels_are_coarse(string? userAgent, string expected) =>
        Assert.Equal(expected, SessionRules.ClientLabelFromUserAgent(userAgent));

    [Fact]
    public void Password_strength_rules_and_messages_match()
    {
        Assert.Equal("Password must be at least 8 characters.", Core.Security.PasswordPolicy.Validate("short", "owner"));
        Assert.Equal("Password is too common. Choose a stronger password.", Core.Security.PasswordPolicy.Validate("password1234", "owner"));
        Assert.Equal("Password must not contain the username.", Core.Security.PasswordPolicy.Validate("xxOWNERyy12", "owner"));
        Assert.Equal("Password must use a wider mix of characters.", Core.Security.PasswordPolicy.Validate("aaabbbaaab", "owner"));
        Assert.Null(Core.Security.PasswordPolicy.Validate("longer-password-1", "owner"));
    }

    [Fact]
    public void Rate_limiter_evicts_expired_buckets_and_caps_keys()
    {
        var clock = new ManualTimeProvider();
        var limiter = new SlidingWindowLimiter(2, 10, clock);
        Assert.True(limiter.Allow("one"));
        Assert.True(limiter.Allow("two"));
        Assert.Equal(2, limiter.KeyCount);
        clock.Advance(TimeSpan.FromSeconds(11));
        Assert.True(limiter.Allow("three"));
        Assert.Equal(1, limiter.KeyCount);

        var capped = new SlidingWindowLimiter(5, 60, clock, maxKeys: 2);
        Assert.True(capped.Allow("one"));
        clock.Advance(TimeSpan.FromSeconds(1));
        Assert.True(capped.Allow("two"));
        clock.Advance(TimeSpan.FromSeconds(1));
        Assert.True(capped.Allow("three"));
        Assert.Equal(2, capped.KeyCount);
        Assert.False(capped.HasKey("one"));
        Assert.True(capped.HasKey("three"));

        var limited = new SlidingWindowLimiter(1, 60, clock);
        Assert.True(limited.Allow(null));
        Assert.False(limited.Allow(string.Empty));
    }

    [Fact]
    public void Forwarded_for_is_used_only_through_a_trusted_proxy()
    {
        var warned = 0;
        Assert.Equal("172.18.0.2", ClientRateLimitKey.Resolve("172.18.0.2", "203.0.113.10", [], () => warned++));
        Assert.Equal(1, warned);
        Assert.Equal("172.18.0.2", ClientRateLimitKey.Resolve("172.18.0.2", "203.0.113.10", ["10.0.0.1"]));
        Assert.Equal("203.0.113.7", ClientRateLimitKey.Resolve("10.0.0.1", "198.51.100.20, 203.0.113.7, 10.0.0.1", ["10.0.0.0/24"]));
        Assert.Equal("unknown", ClientRateLimitKey.Resolve(null, null, []));
    }

    [Fact]
    public void Suite_settings_validation_messages_match()
    {
        var zones = new FakeZones();
        string Error(SuiteSettingsUpdate update) => Assert.Throws<PyValueErrorException>(() => SuiteSettingsRules.Normalize(update, zones)).Message;
        Assert.Equal("Product name cannot be empty.", Error(new("   ", null, "UTC", 30)));
        Assert.Equal("Choose a valid timezone (for example: UTC, Europe/London, America/New_York).", Error(new("Weir", null, "Not/A_Real_Zone", 30)));
        Assert.Equal("Log retention must be between 1 and 3650 days.", Error(new("Weir", null, "UTC", 0)));
        Assert.Equal("Setup wizard state must be pending, skipped, or completed.", Error(new("Weir", null, "UTC", 30, "later")));
        Assert.Equal("Backup time must use HH:MM in 24-hour time.", Error(new("Weir", null, "UTC", 30, ConfigurationBackupPreferredTime: "ab:cd")));
        var normalized = SuiteSettingsRules.Normalize(new("  House ", "  ", "UTC", 45, "COMPLETED", ConfigurationBackupPreferredTime: "3:5"), zones);
        Assert.Equal(("House", (string?)null, "completed", "03:05"), (normalized.ProductDisplayName, normalized.SignedInHomeNotice, normalized.SetupWizardState, normalized.ConfigurationBackupPreferredTime));
        Assert.Equal("skipped", SuiteSettingsRules.DefaultSetupWizardState(1));
        Assert.Equal("pending", SuiteSettingsRules.DefaultSetupWizardState(0));
    }

    [Fact]
    public void Configuration_backup_waits_for_the_preferred_local_time_and_interval()
    {
        var zones = new FakeZones();
        var suite = new SuiteSettingsRecord
        {
            ConfigurationBackupEnabled = true,
            ConfigurationBackupIntervalHours = 24,
            ConfigurationBackupPreferredTime = "23:30",
            AppTimezone = "Australia/Sydney",
        };
        Assert.False(ConfigurationBackupSchedule.IsDue(suite, new DateTime(2026, 4, 24, 12, 0, 0, DateTimeKind.Utc), zones));
        Assert.True(ConfigurationBackupSchedule.IsDue(suite, new DateTime(2026, 4, 24, 13, 45, 0, DateTimeKind.Utc), zones));

        var hourly = suite with { ConfigurationBackupIntervalHours = 6, ConfigurationBackupLastRunAt = PyDateTime.Naive(new DateTime(2026, 4, 24, 10, 0, 0)) };
        Assert.False(ConfigurationBackupSchedule.IsDue(hourly, new DateTime(2026, 4, 24, 15, 0, 0, DateTimeKind.Utc), zones));
        Assert.True(ConfigurationBackupSchedule.IsDue(hourly, new DateTime(2026, 4, 24, 16, 0, 0, DateTimeKind.Utc), zones));
        Assert.False(ConfigurationBackupSchedule.IsDue(suite with { ConfigurationBackupEnabled = false }, DateTime.UtcNow, zones));
    }

    [Fact]
    public void Pause_expiry_is_resolved_on_read()
    {
        var now = new DateTime(2026, 9, 17, 2, 0, 0, DateTimeKind.Utc);
        var until = PyDateTime.Naive(new DateTime(2026, 9, 17, 4, 21, 1, 799).AddTicks(8780));
        var paused = PauseState.Resolve(new SuiteSettingsRecord { ProcessingPaused = true, ProcessingPausedUntil = until }, now);
        Assert.Equal(
            "{\"paused\":true,\"paused_until\":\"2026-09-17T04:21:01.799878Z\",\"scan_while_paused\":true,\"reason\":\"Processing is paused. Weir will start work again automatically at 2026-09-17 04:21 UTC.\",\"in_flight_policy\":\"Work already running finishes. Pausing stops Weir starting anything new.\"}",
            PyJsonWriter.Dumps(paused.ToOut(), PyJsonFormat.Response));
        Assert.True(PauseState.Resolve(new SuiteSettingsRecord { ProcessingPaused = true, ProcessingPausedUntil = until }, now.AddHours(3)).Expired);
        Assert.Equal("Processing is paused. Weir will start work again when you resume it.", PauseState.Resolve(new SuiteSettingsRecord { ProcessingPaused = true }, now).Reason);
    }

    [Fact]
    public void Security_overview_uses_plain_durations()
    {
        var overview = SecurityOverview.Build(Options);
        Assert.Equal("14 days", ((PyStr)overview["standard_session_idle_timeout_plain"]).Value);
        Assert.Equal("1 minute", ((PyStr)overview["sign_in_attempt_window_plain"]).Value);
        Assert.Equal("1 hour", ((PyStr)overview["first_time_setup_attempt_window_plain"]).Value);
        Assert.Equal(["1 second", "59 seconds", "2 minutes", "1 day"], new[] { 1L, 59, 120, 86400 }.Select(SecurityOverview.PlainDuration));
    }

    [Fact]
    public void Failure_messages_classify_like_python()
    {
        var credentials = FailureMessages.FromException("Refiner", "connection test", new FailureSubject("RuntimeError", "api_key=secret was rejected", ExceptionCategory.Other), provider: "jellyfin");
        Assert.Equal(FailureKind.Credential, credentials.Kind);
        Assert.Contains("Refiner connection test for Jellyfin failed", credentials.Message, StringComparison.Ordinal);
        Assert.Contains("Re-enter the Jellyfin credentials", credentials.NextAction, StringComparison.Ordinal);
        Assert.Contains("api_key=[redacted]", credentials.TechnicalDetail, StringComparison.Ordinal);

        var rate = FailureMessages.FromException("Refiner", "subtitle search", new FailureSubject("RuntimeError", "HTTP 429 rate limit", ExceptionCategory.Other), provider: "opensubtitles_com", recoverable: true);
        Assert.Equal(FailureKind.RateLimit, rate.Kind);
        Assert.Contains("skipped and continued", rate.Message, StringComparison.Ordinal);
        Assert.Contains("continue with the next available provider", rate.WhatHappensNext, StringComparison.Ordinal);

        Assert.Equal(FailureKind.Filesystem, FailureMessages.Classify(FailureMessages.FromDotNet(new FileNotFoundException("D:/Downloads/film.mkv"))));
        Assert.Equal(FailureKind.Filesystem, FailureMessages.Classify(FailureMessages.FromDotNet(new UnauthorizedAccessException("denied"))));
        var gone = FailureMessages.FromException("Refiner", "remux", FailureMessages.FromDotNet(new FileNotFoundException("gone")));
        Assert.Contains("file or folder", gone.Message + gone.NextAction, StringComparison.Ordinal);
        Assert.Equal(FailureKind.Network, FailureMessages.Classify(new FailureSubject("ConnectionRefusedError", "refused", ExceptionCategory.NetworkOrOs)));
        Assert.Equal(FailureKind.Validation, FailureMessages.Classify(new FailureSubject("ValueError", "bad", ExceptionCategory.Validation)));
        Assert.Equal(FailureKind.NotFound, FailureMessages.Classify(new FailureSubject("RuntimeError", "HTTP 404", ExceptionCategory.Other)));
        Assert.Equal(FailureKind.Auth, FailureMessages.Classify(new FailureSubject("RuntimeError", "403 Forbidden", ExceptionCategory.Other)));
        Assert.Equal(FailureKind.Internal, FailureMessages.Classify(new FailureSubject("RuntimeError", "boom", ExceptionCategory.Other)));
    }

    [Fact]
    public void Diagnostics_and_operator_messages_keep_the_shared_shape()
    {
        var safe = new DiagnosticEvent("refiner", "preview", "scheduled", "failed", Diagnostics.SeverityForResult("failed"), "Jellyfin", "movies", "job-123",
            "Provider returned api_key=abc123 as rejected", "Re-enter the Jellyfin API key and run the connection test again.",
            [new("scanned", 4), new("failed", 1)]).AsSafeDict();
        Assert.Equal(
            "{\"module\":\"refiner\",\"action\":\"preview\",\"trigger\":\"scheduled\",\"result\":\"failed\",\"severity\":\"error\",\"provider\":\"Jellyfin\",\"media_scope\":\"movies\",\"correlation_id\":\"job-123\",\"reason\":\"Provider returned api_key=[redacted] as rejected\",\"next_action\":\"Re-enter the Jellyfin API key and run the connection test again.\",\"counts\":{\"scanned\":4,\"failed\":1}}",
            PyJsonWriter.Dumps(safe, PyJsonFormat.Response));
        Assert.Equal(["info", "info", "warning", "error"], new[] { "success", "skipped", "retrying", "failed" }.Select(Diagnostics.SeverityForResult));
        Assert.Equal(
            "{\"module\":\"refiner\",\"action\":\"search\",\"trigger\":\"worker\",\"result\":\"skipped\",\"severity\":\"info\",\"provider\":\"opensubtitles\",\"media_scope_label\":\"Movies\",\"media_scope\":\"movies\",\"counts\":{\"checked\":1,\"downloaded\":0},\"user_message\":\"No subtitle was found.\"}",
            PyJsonWriter.Dumps(
                OperatorMessages.ActivityDetailEnvelope("refiner", "search", "worker", "skipped", "opensubtitles", "movies", [new("checked", 1), new("downloaded", 0), new("bad_flag", null)], "No subtitle was found."),
                PyJsonFormat.Response));
        Assert.Equal("{\"failed\":0,\"removed\":3}", PyJsonWriter.Dumps(OperatorMessages.CountSummary([new("failed", -5), new("removed", 3)]), PyJsonFormat.Response));
        Assert.Equal(("Jellyfin", "TV episodes"), (OperatorMessages.ProviderLabel("jellyfin"), OperatorMessages.MediaScopeLabel("tv")));
        Assert.Equal(5, MetricsTruth.FinalizedSuccessTotal(new Dictionary<string, long> { ["output_written"] = 2, ["unchanged_copied"] = 3 }));
        Assert.Contains("must not be negative", Assert.Throws<PyValueErrorException>(() => MetricsTruth.RequireNonNegative(new Dictionary<string, long> { ["files_processed"] = -1 })).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Runtime_metrics_render_like_python()
    {
        var store = new RuntimeMetricsStore(new ManualTimeProvider());
        store.RecordRequest("GET", "/api/v1/health", 200, 12.5);
        store.RecordRequest("POST", "/api/v1/refiner/jobs", 500, 33.0);
        store.RecordLog("error");
        store.RecordModuleJobEvent("refiner", "started");
        store.RecordModuleJobEvent("refiner", "completed");
        store.RecordModuleJobEvent("other", "failed");
        store.SetModuleQueueDepth("refiner", 3);
        store.SetModuleQueueDepth("other", 1);
        var output = store.RenderPrometheus();
        Assert.Contains("weir_module_jobs_total{module=\"refiner\",event=\"started\"} 1", output, StringComparison.Ordinal);
        Assert.Contains("weir_module_jobs_total{module=\"other\",event=\"failed\"} 1", output, StringComparison.Ordinal);
        Assert.Contains("weir_module_queue_depth{module=\"other\"} 1", output, StringComparison.Ordinal);
        Assert.Contains("weir_http_requests_total 2", output, StringComparison.Ordinal);
        Assert.Contains("weir_log_records_total{level=\"error\"} 1", output, StringComparison.Ordinal);
        Assert.DoesNotContain("weir_module_savings_bytes_total", output, StringComparison.Ordinal);

        store.RecordModuleSavings("refiner", 12_345_678);
        store.RecordModuleSavings("refiner", 0);
        store.RecordModuleSavings("other", 9_876_543);
        output = store.RenderPrometheus();
        Assert.Contains("# TYPE weir_module_savings_bytes_total counter", output, StringComparison.Ordinal);
        Assert.Contains("weir_module_savings_bytes_total{module=\"refiner\"} 12345678", output, StringComparison.Ordinal);
        var summary = PyJsonWriter.Dumps(store.SuiteMetricsOut(), PyJsonFormat.Response);
        Assert.Contains("\"error_log_count\":1,\"status_counts\":{\"2xx\":1,\"3xx\":0,\"4xx\":0,\"5xx\":1}", summary, StringComparison.Ordinal);
        Assert.Contains("{\"route\":\"GET /api/v1/health\",\"request_count\":1,\"average_response_ms\":12.5}", summary, StringComparison.Ordinal);
    }

    [Fact]
    public void Log_reading_returns_the_newest_matching_rows_and_counts()
    {
        var filter = new SuiteLogFilter(null, "row", null, 5);
        for (var i = 0; i < 20; i++)
        {
            filter.Add($"{{\"timestamp\":\"2026-05-09T10:00:{i:00}Z\",\"level\":\"INFO\",\"logger\":\"weir.tests\",\"message\":\"row-{i}\",\"source\":\"test.py:1\"}}");
        }

        filter.Add("not json");
        filter.Add("{\"timestamp\":\"2026-05-09T10:00:00Z\",\"level\":\"INFO\",\"logger\":\"uvicorn\",\"message\":\"noise\"}");
        var result = filter.Result();
        Assert.Equal(20, result.Total);
        Assert.Equal(20, result.Information);
        Assert.Equal(["row-19", "row-18", "row-17", "row-16", "row-15"], result.Items.Select(item => item.Message));
        Assert.Null(SuiteLogFilter.ToOut(result.Items[0] with { Timestamp = "not-a-time" }));
        Assert.Equal("2026-05-09T10:00:19Z", ((PyStr)SuiteLogFilter.ToOut(result.Items[0])!["timestamp"]).Value);
    }

    [Fact]
    public void Release_versions_and_update_status_match_python()
    {
        Assert.Equal("2.0.8", ReleaseCatalog.NormalizeReleaseVersion("v2.0.8"));
        Assert.Equal("v2.0.8", ReleaseCatalog.TagForVersion("2.0.8"));
        GitHubReleaseAsset Asset(string name) => new(name, $"https://api.github.test/assets/{name}", $"https://downloads.github.test/{name}", 123, "application/octet-stream");
        var current = Asset("Weir-win-Setup.exe");
        var legacy = Asset("WeirSetup.exe");
        GitHubReleaseRecord Record(string version, params GitHubReleaseAsset[] assets) =>
            new($"v{version}", version, $"Weir {version}", "https://example.com/release", PyDateTime.FromUtc(new DateTime(2026, 5, 7, 0, 0, 0, DateTimeKind.Utc)), false, false, assets);
        Assert.Same(current, Record("2.6.1", legacy, current).WindowsInstallerAsset());
        Assert.Same(legacy, Record("2.6.1", legacy).WindowsInstallerAsset());

        var windows = UpdateStatus.FromRelease("2.0.7", "windows", Record("2.0.8", current));
        Assert.Equal("update_available", ((PyStr)windows["status"]).Value);
        Assert.Equal("Updates are managed by the Weir desktop app via Velopack.", ((PyStr)windows["in_app_upgrade_summary"]).Value);
        Assert.Equal("2026-05-07T00:00:00Z", ((PyStr)windows["published_at"]).Value);
        Assert.Equal("up_to_date", ((PyStr)UpdateStatus.FromRelease("2.1.4", "windows", Record("2.1.4"))["status"]).Value);
        var docker = UpdateStatus.FromRelease("2.0.7", "docker", Record("2.0.8"));
        Assert.Equal("docker compose pull && docker compose up -d", ((PyStr)docker["docker_update_command"]).Value);
        Assert.False(((PyBool)docker["in_app_upgrade_supported"]).Value);
        Assert.IsType<PyNull>(docker["in_app_upgrade_summary"]);

        Assert.Null(UpdateStatus.ParseUpdateSettings("{\"mode\": \"Notify"));
        Assert.Null(UpdateStatus.ParseUpdateSettings("{\"mode\": \"InstallEverythingNow\"}"));
        Assert.Equal("{\"mode\":\"DownloadOnly\",\"check_on_startup\":false,\"check_interval_minutes\":240}",
            PyJsonWriter.Dumps(UpdateStatus.ParseUpdateSettings("{\"mode\": \"DownloadOnly\", \"checkOnStartup\": false, \"checkIntervalMinutes\": 240}")!, PyJsonFormat.Response));
        Assert.Equal("{\n  \"mode\": \"Auto\",\n  \"checkOnStartup\": true,\n  \"checkIntervalMinutes\": 1\n}", UpdateStatus.SerializeUpdateSettings("Auto", true, 1));
    }

    [Fact]
    public void Notification_rules_and_url_policy_match_python()
    {
        string Error(string label, string provider, string url, params string[] events) =>
            Assert.Throws<PyValueErrorException>(() => NotificationRules.Validate(label, provider, url, events)).Message;
        Assert.Equal("Unsupported provider: 'slack'. Choose from: webhook, discord", Error("x", "slack", "https://example.com", "job_failed"));
        Assert.Equal("Blocked provider URL host: 10.0.0.1", Error("x", "discord", "http://10.0.0.1/x"));
        Assert.Equal("Blocked provider URL host: localhost", Error("x", "discord", "http://LOCALHOST:80/x", "job_failed"));
        Assert.Equal("Blocked provider URL scheme: ftp", Error("x", "discord", "ftp://example.com/x", "job_failed"));
        Assert.Equal("Unknown events: nope. Supported: job_completed, job_failed, refiner_job_completed, refiner_job_failed", Error("x", "discord", "https://example.com/x", "nope"));
        Assert.Equal("At least one event must be selected.", Error("x", "discord", "https://example.com/x"));
        Assert.Equal("Label must not be empty.", Error("  ", "discord", "https://example.com/x", "job_failed"));
        Assert.Equal("Invalid IPv6 URL", Error("x", "discord", "https://[::1/x", "job_failed"));
        Assert.Equal("[\"job_failed\", \"refiner_job_completed\"]", NotificationRules.SerializeEvents(["job_failed", "refiner_job_completed"]));
        Assert.Equal(["job_failed"], NotificationRules.ParseEvents("[\"job_failed\", 5]"));
        Assert.Empty(NotificationRules.ParseEvents("{bad"));

        Assert.True(PyIpAddress.TryParse("203.0.113.7", out var documentation) && !documentation.IsGlobal);
        Assert.True(PyIpAddress.TryParse("100.64.0.1", out var shared) && !shared.IsGlobal && !shared.IsPrivate);
        Assert.True(PyIpAddress.TryParse("8.8.8.8", out var google) && google.IsGlobal);
        Assert.True(PyIpAddress.TryParse("::ffff:10.0.0.1", out var mapped) && mapped.IsPrivate);
        Assert.False(PyIpAddress.TryParse("01.1.1.1", out _));
        Assert.True(PyIpNetwork.TryParse("10.0.0.5/24", strict: false, out var network) && network.Contains(documentation) is false);
        Assert.False(PyIpNetwork.TryParse("10.0.0.5/24", strict: true, out _));
    }

    [Fact]
    public void Activity_facts_are_lifted_from_the_event()
    {
        Assert.Equal(new ActivityFacts("manual", "success", null, null, null), ActivityClassifier.Classify("auth.login_succeeded", "alice"));
        Assert.Equal(new ActivityFacts("manual", "failed", null, null, null), ActivityClassifier.Classify("auth.bootstrap_denied", "An admin account already exists."));
        Assert.Equal(
            new ActivityFacts("worker", "warning", 3, "Movies/a.mkv", "run:7"),
            ActivityClassifier.Classify("refiner.file_processed", "{\"trigger\": \" Worker \", \"result\": \"warning\", \"library_id\": 3, \"relative_media_path\": \" Movies/a.mkv \", \"run_id\": 7}"));
        Assert.Equal(new ActivityFacts(null, "failed", null, null, null), ActivityClassifier.Classify("refiner.x", "{\"ok\": false, \"library_id\": true}"));
    }

    private static UserSessionRecord Session(DateTime now, DateTime absolute, DateTime lastSeen) =>
        new("ab", 1, "cd", PyDateTime.FromUtc(now), PyDateTime.FromUtc(absolute), false, PyDateTime.FromUtc(lastSeen), null, "Browser session");

    private sealed class FakeZones : ITimeZoneResolver
    {
        public bool TryFind(string name, out TimeZoneInfo zone)
        {
            zone = TimeZoneInfo.Utc;
            switch (name)
            {
                case "UTC":
                    return true;
                case "Australia/Sydney":
                    // AEST, no daylight saving in April after the first Sunday.
                    zone = TimeZoneInfo.CreateCustomTimeZone("Australia/Sydney", TimeSpan.FromHours(10), "Sydney", "AEST");
                    return true;
                default:
                    return false;
            }
        }
    }
}
