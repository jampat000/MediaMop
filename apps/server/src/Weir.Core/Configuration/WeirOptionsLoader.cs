namespace Weir.Core.Configuration;

/// <summary>
/// Port of <c>WeirSettings.load()</c> and <c>weir.core.runtime_paths</c> path resolution.
/// Pure: it reads only the <see cref="RuntimeEnvironment"/> it is given. Creating the runtime
/// directories and checking the database location happen at startup, in Infrastructure.
/// </summary>
/// <remarks>
/// Not ported: Python also loads <c>apps/backend/.env</c> for local development. The .NET server
/// reads only the real environment.
/// </remarks>
public static class WeirOptionsLoader
{
    public const string CorsWildcardMessage =
        "WEIR_CORS_ORIGINS cannot include '*' because Weir uses credentialed " +
        "browser requests. Configure explicit origins instead.";

    private const int SevenDaysSeconds = 7 * 24 * 3600;
    private const int ThirtyDaysSeconds = 30 * 24 * 3600;

    /// <summary>Python's <c>DEFAULT_PROCESSING_JOB_LEASE_SECONDS</c> (#540 item 1).</summary>
    public const int DefaultProcessingJobLeaseSeconds = 300;

    public static WeirOptions Load(RuntimeEnvironment runtime)
    {
        ArgumentNullException.ThrowIfNull(runtime);

        var env = Or(runtime.Get("WEIR_ENV"), "development").Trim().ToLowerInvariant();
        var level = Or(Or(runtime.Get("WEIR_LOG_LEVEL"), "INFO").Trim(), "INFO");
        var cors = ParseCsv(runtime.Get("WEIR_CORS_ORIGINS"));
        var session = NullIfEmpty(runtime.Get("WEIR_SESSION_SECRET")?.Trim());
        var credentialsSecret = NullIfEmpty(runtime.Get("WEIR_CREDENTIALS_SECRET")?.Trim());
        var previousCredentialsSecrets = ParseCsv(runtime.Get("WEIR_PREVIOUS_CREDENTIALS_SECRETS"))
            .Where(item => item.Length > 0 && item != credentialsSecret)
            .ToArray();
        var cookieName = Or(runtime.Get("WEIR_SESSION_COOKIE_NAME")?.Trim(), "weir_session");
        var sameSite = Or(runtime.Get("WEIR_SESSION_COOKIE_SAMESITE"), "lax").Trim().ToLowerInvariant() switch
        {
            "strict" => CookieSameSite.Strict,
            "none" => CookieSameSite.None,
            _ => CookieSameSite.Lax,
        };
        // Tri-state, not a bool: a Secure cookie on a plain-HTTP LAN install is discarded by the
        // browser and locks the operator out. Legacy boolish values keep their old meaning.
        var secureMode = (runtime.Get("WEIR_SESSION_COOKIE_SECURE") ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "1" or "true" or "yes" or "on" or "always" => CookieSecureMode.Always,
            "0" or "false" or "no" or "off" or "never" => CookieSecureMode.Never,
            _ => CookieSecureMode.Auto,
        };
        var idleMinutes = Math.Max(1, EnvInt(runtime, "WEIR_SESSION_IDLE_MINUTES", 20160));
        var absoluteDays = Math.Max(1, EnvInt(runtime, "WEIR_SESSION_ABSOLUTE_DAYS", 90));
        var trustedIdleDays = Math.Max(1, EnvInt(runtime, "WEIR_SESSION_TRUSTED_IDLE_DAYS", 60));
        var trustedAbsoluteDays = Math.Max(1, EnvInt(runtime, "WEIR_SESSION_TRUSTED_ABSOLUTE_DAYS", 365));
        var trustedOverride = ParseCsv(runtime.Get("WEIR_TRUSTED_BROWSER_ORIGINS"));
        if (env == "development")
        {
            cors = ExpandLoopbackBrowserOriginsInDevelopment(cors);
            trustedOverride = ExpandLoopbackBrowserOriginsInDevelopment(trustedOverride);
        }

        if (cors.Any(origin => origin == "*"))
        {
            throw new WeirConfigurationException(CorsWildcardMessage);
        }

        var trustedProxyIps = ParseCsv(runtime.Get("WEIR_TRUSTED_PROXY_IPS"));
        var loginMax = Math.Max(1, EnvInt(runtime, "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS", 10));
        var loginWindow = Math.Max(1, EnvInt(runtime, "WEIR_AUTH_LOGIN_RATE_WINDOW_SECONDS", 60));
        var bootstrapMax = Math.Max(1, EnvInt(runtime, "WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS", 10));
        var bootstrapWindow = Math.Max(1, EnvInt(runtime, "WEIR_BOOTSTRAP_RATE_WINDOW_SECONDS", 3600));
        var enableHsts = EnvBool(runtime, "WEIR_SECURITY_ENABLE_HSTS", false);
        var metricsBearerToken = NullIfEmpty(runtime.Get("WEIR_METRICS_BEARER_TOKEN")?.Trim());
        // The legacy name is read second so an install that never renamed it keeps authenticating.
        var webhookSecret = NullIfEmpty(
            Or(OrNullable(runtime.Get("WEIR_MEDIA_MANAGER_WEBHOOK_SECRET"), runtime.Get("WEIR_SUBBER_WEBHOOK_SECRET")), string.Empty).Trim());

        var paths = RuntimePaths.Resolve(runtime);

        var processingWorkers = ClampProcessingWorkerCount(EnvInt(runtime, "WEIR_PROCESSING_WORKER_COUNT", 8));
        var processingJobLeaseSeconds = ClampProcessingJobLeaseSeconds(EnvInt(runtime, "WEIR_PROCESSING_JOB_LEASE_SECONDS", DefaultProcessingJobLeaseSeconds));
        var watcherEnabled = EnvBool(runtime, "WEIR_PROCESSING_WATCHER_ENABLED", true);
        var watcherDebounce = Math.Max(0.25, Math.Min(300.0, EnvInt(runtime, "WEIR_PROCESSING_WATCHER_DEBOUNCE_SECONDS", 3)));

        const string legacySweepEnabled = "WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_SCHEDULE_ENABLED";
        const string legacySweepInterval = "WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_SCHEDULE_INTERVAL_SECONDS";

        bool SweepEnabled(string key) =>
            runtime.IsSet(key) ? EnvBool(runtime, key, false)
            : runtime.IsSet(legacySweepEnabled) && EnvBool(runtime, legacySweepEnabled, false);

        int SweepInterval(string key) =>
            runtime.IsSet(key) ? ClampProcessingScheduleIntervalSeconds(EnvInt(runtime, key, 3600))
            : runtime.IsSet(legacySweepInterval) ? ClampProcessingScheduleIntervalSeconds(EnvInt(runtime, legacySweepInterval, 3600))
            : ClampProcessingScheduleIntervalSeconds(3600);

        var remuxRoot = (runtime.Get("WEIR_PROCESSING_REMUX_MEDIA_ROOT") ?? string.Empty).Trim();
        var webDist = (runtime.Get("WEIR_WEB_DIST") ?? string.Empty).Trim();

        var outputOwnershipChown = EnvBool(runtime, "WEIR_CHOWN_OUTPUT", false);
        var outputOwnershipUid = (uint)Math.Max(0, FirstEnvInt(runtime, 1000, "WEIR_PUID", "PUID"));
        var outputOwnershipGid = (uint)Math.Max(0, FirstEnvInt(runtime, 1000, "WEIR_PGID", "PGID"));
        var outputFileMode = ParseOctalMode(runtime.Get("WEIR_FILE_MODE_OUTPUT"), "WEIR_FILE_MODE_OUTPUT");
        var outputDirMode = ParseOctalMode(runtime.Get("WEIR_DIR_MODE_OUTPUT"), "WEIR_DIR_MODE_OUTPUT");

        return new WeirOptions
        {
            Env = env,
            LogLevel = level,
            CorsOrigins = cors,
            SessionSecret = session,
            CredentialsSecret = credentialsSecret,
            PreviousCredentialsSecrets = previousCredentialsSecrets,
            SessionCookieName = cookieName,
            SessionCookieSecureMode = secureMode,
            SessionCookieSameSite = sameSite,
            SessionIdleMinutes = idleMinutes,
            SessionAbsoluteDays = absoluteDays,
            SessionTrustedIdleMinutes = SaturatingMultiply(trustedIdleDays, 1440),
            SessionTrustedAbsoluteDays = trustedAbsoluteDays,
            TrustedBrowserOriginsOverride = trustedOverride,
            TrustedProxyIps = trustedProxyIps,
            AuthLoginRateMaxAttempts = loginMax,
            AuthLoginRateWindowSeconds = loginWindow,
            BootstrapRateMaxAttempts = bootstrapMax,
            BootstrapRateWindowSeconds = bootstrapWindow,
            SecurityEnableHsts = enableHsts,
            MetricsBearerToken = metricsBearerToken,
            MediaManagerWebhookSecret = webhookSecret,
            WeirHome = paths.Home,
            DbPath = paths.DbPath,
            BackupDir = paths.BackupDir,
            LogDir = paths.LogDir,
            TempDir = paths.TempDir,
            ProcessingWorkerCount = processingWorkers,
            ProcessingJobLeaseSeconds = processingJobLeaseSeconds,
            ProcessingWatcherEnabled = watcherEnabled,
            ProcessingWatcherDebounceSeconds = watcherDebounce,
            ProcessingWatchedFolderRemuxScanDispatchScheduleEnabled = EnvBool(
                runtime, "WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED", true),
            ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs = EnvBool(
                runtime, "WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS", true),
            ProcessingProbeSizeMb = Clamp(EnvInt(runtime, "WEIR_PROCESSING_PROBE_SIZE_MB", 10), 1, 1024),
            ProcessingAnalyzeDurationSeconds = Clamp(EnvInt(runtime, "WEIR_PROCESSING_ANALYZE_DURATION_SECONDS", 10), 1, 300),
            ProcessingWatchedFolderMinFileAgeSeconds = ClampProcessingMinFileAgeSeconds(
                EnvInt(runtime, "WEIR_PROCESSING_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", 300)),
            ProcessingMovieOutputCleanupMinAgeSeconds = Clamp(
                EnvInt(runtime, "WEIR_PROCESSING_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS", 48 * 3600), 3600, ThirtyDaysSeconds),
            ProcessingTvOutputCleanupMinAgeSeconds = Clamp(
                EnvInt(runtime, "WEIR_PROCESSING_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS", 48 * 3600), 3600, ThirtyDaysSeconds),
            ProcessingWorkTempStaleSweepMovieScheduleEnabled = SweepEnabled("WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED"),
            ProcessingWorkTempStaleSweepMovieScheduleIntervalSeconds = SweepInterval("WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_INTERVAL_SECONDS"),
            ProcessingWorkTempStaleSweepTvScheduleEnabled = SweepEnabled("WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED"),
            ProcessingWorkTempStaleSweepTvScheduleIntervalSeconds = SweepInterval("WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_INTERVAL_SECONDS"),
            ProcessingWorkTempStaleSweepMinStaleAgeSeconds = Clamp(
                EnvInt(runtime, "WEIR_PROCESSING_WORK_TEMP_STALE_SWEEP_MIN_STALE_AGE_SECONDS", 86_400), 60, ThirtyDaysSeconds),
            ProcessingMovieFailureCleanupScheduleEnabled = EnvBool(runtime, "WEIR_PROCESSING_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED", false),
            ProcessingMovieFailureCleanupScheduleIntervalSeconds = ClampProcessingScheduleIntervalSeconds(
                EnvInt(runtime, "WEIR_PROCESSING_MOVIE_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", 3600)),
            ProcessingTvFailureCleanupScheduleEnabled = EnvBool(runtime, "WEIR_PROCESSING_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED", false),
            ProcessingTvFailureCleanupScheduleIntervalSeconds = ClampProcessingScheduleIntervalSeconds(
                EnvInt(runtime, "WEIR_PROCESSING_TV_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS", 3600)),
            ProcessingMovieFailureCleanupGracePeriodSeconds = Clamp(
                EnvInt(runtime, "WEIR_PROCESSING_MOVIE_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", 1800), 300, 604800),
            ProcessingTvFailureCleanupGracePeriodSeconds = Clamp(
                EnvInt(runtime, "WEIR_PROCESSING_TV_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS", 1800), 300, 604800),
            ProcessingRemuxMediaRoot = remuxRoot.Length == 0
                ? null
                : PythonCompat.NormalizeLexically(PythonCompat.ExpandUser(remuxRoot, runtime), runtime),
            JobRowsRetentionDays = Clamp(EnvInt(runtime, "WEIR_JOB_ROWS_RETENTION_DAYS", 90), 1, 365),
            JobRowsRetentionScheduleIntervalSeconds = Clamp(
                EnvInt(runtime, "WEIR_JOB_ROWS_RETENTION_SCHEDULE_INTERVAL_SECONDS", 3600), 60, 86400),
            ArrRadarrBaseUrl = NullIfEmpty(HttpUrlOrEmpty(runtime.Get("WEIR_ARR_RADARR_BASE_URL"))),
            ArrRadarrApiKey = NullIfEmpty(runtime.Get("WEIR_ARR_RADARR_API_KEY")?.Trim()),
            ArrSonarrBaseUrl = NullIfEmpty(HttpUrlOrEmpty(runtime.Get("WEIR_ARR_SONARR_BASE_URL"))),
            ArrSonarrApiKey = NullIfEmpty(runtime.Get("WEIR_ARR_SONARR_API_KEY")?.Trim()),
            WebDist = webDist.Length == 0 ? null : PythonCompat.Resolve(PythonCompat.ExpandUser(webDist, runtime), runtime),
            VersionOverride = NullIfEmpty(runtime.Get("WEIR_VERSION")?.Trim()),
            RuntimeKind = runtime.Get("WEIR_RUNTIME"),
            OutputOwnershipChownEnabled = outputOwnershipChown,
            OutputOwnershipUid = outputOwnershipUid,
            OutputOwnershipGid = outputOwnershipGid,
            OutputOwnershipFileMode = outputFileMode,
            OutputOwnershipDirectoryMode = outputDirMode,
        };
    }

    /// <summary><c>clamp_processing_worker_count</c>: 0..8 slots; negative values mean 1.</summary>
    public static int ClampProcessingWorkerCount(long raw) => raw < 0 ? 1 : (int)Math.Min(8, raw);

    /// <summary>
    /// #540 item 1: 30 s .. 1 day. Below 30 s the lease-renewal heartbeat (every ~lease/3) would fire
    /// so often it could swamp the database; above a day, a crashed worker's row would sit unclaimed
    /// for an unreasonable time before startup recovery or a reclaim picks it up.
    /// </summary>
    public static int ClampProcessingJobLeaseSeconds(long raw) => Clamp(raw, 30, 86_400);

    /// <summary><c>clamp_processing_schedule_interval_seconds</c>: 60 s .. 7 days.</summary>
    public static int ClampProcessingScheduleIntervalSeconds(long raw) => Clamp(raw, 60, SevenDaysSeconds);

    /// <summary><c>clamp_processing_min_file_age_seconds</c>: 0 .. 7 days.</summary>
    public static int ClampProcessingMinFileAgeSeconds(long raw) => Clamp(raw, 0, SevenDaysSeconds);

    /// <summary>
    /// For each <c>http(s)://localhost</c> or <c>127.0.0.1</c> origin, also allow the other hostname on
    /// the same port: browsers treat them as different origins and developers switch between them.
    /// </summary>
    public static IReadOnlyList<string> ExpandLoopbackBrowserOriginsInDevelopment(IReadOnlyList<string> origins)
    {
        ArgumentNullException.ThrowIfNull(origins);
        if (origins.Count == 0)
        {
            return origins;
        }

        var ordered = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        void Add(string raw)
        {
            var value = raw.Trim().TrimEnd('/');
            if (value.Length == 0 || !seen.Add(value))
            {
                return;
            }

            ordered.Add(value);
        }

        foreach (var origin in origins)
        {
            Add(origin);
            var parsed = PythonCompat.ParseUrl(origin.Trim());
            if (parsed.Scheme is not ("http" or "https"))
            {
                continue;
            }

            var alternateHost = parsed.Hostname switch
            {
                "localhost" => "127.0.0.1",
                "127.0.0.1" => "localhost",
                _ => null,
            };
            if (alternateHost is null)
            {
                continue;
            }

            Add(parsed.Port is { } port
                ? $"{parsed.Scheme}://{alternateHost}:{port}"
                : $"{parsed.Scheme}://{alternateHost}");
        }

        return ordered;
    }

    internal static IReadOnlyList<string> ParseCsv(string? raw) =>
        (raw ?? string.Empty).Split(',').Select(part => part.Trim()).Where(part => part.Length > 0).ToArray();

    internal static bool EnvBool(RuntimeEnvironment runtime, string name, bool defaultValue) =>
        (runtime.Get(name) ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "1" or "true" or "yes" or "on" => true,
            "0" or "false" or "no" or "off" => false,
            _ => defaultValue,
        };

    internal static long EnvInt(RuntimeEnvironment runtime, string name, long defaultValue)
    {
        var raw = (runtime.Get(name) ?? string.Empty).Trim();
        return raw.Length > 0 && PythonCompat.TryParseInt(raw, out var value) ? value : defaultValue;
    }

    /// <summary>The first of <paramref name="names"/> that is set to a non-blank, parseable integer; <paramref name="defaultValue"/> otherwise.</summary>
    internal static long FirstEnvInt(RuntimeEnvironment runtime, long defaultValue, params string[] names)
    {
        foreach (var name in names)
        {
            var raw = (runtime.Get(name) ?? string.Empty).Trim();
            if (raw.Length > 0 && PythonCompat.TryParseInt(raw, out var value))
            {
                return value;
            }
        }

        return defaultValue;
    }

    /// <summary>
    /// #555: an octal file/directory mode such as <c>664</c>, <c>775</c> or the setuid/setgid/sticky 4-digit form
    /// <c>2775</c>. <see langword="null"/> when unset; a set but malformed value refuses to start, as
    /// <see cref="CorsWildcardMessage"/> does for <c>WEIR_CORS_ORIGINS</c> — an operator should see this at startup,
    /// not have it silently ignored, since a mode Weir cannot parse is a mode it cannot apply.
    /// </summary>
    internal static UnixFileMode? ParseOctalMode(string? raw, string name)
    {
        var value = (raw ?? string.Empty).Trim();
        if (value.Length == 0)
        {
            return null;
        }

        if (value.Length is not (3 or 4) || value.Any(ch => ch is < '0' or > '7'))
        {
            throw new WeirConfigurationException($"{name} must be an octal file mode such as 664 or 775.");
        }

        return (UnixFileMode)Convert.ToInt32(value, 8);
    }

    private static string HttpUrlOrEmpty(string? raw)
    {
        var value = (raw ?? string.Empty).Trim();
        return value.StartsWith("http://", StringComparison.Ordinal) || value.StartsWith("https://", StringComparison.Ordinal)
            ? value
            : string.Empty;
    }

    private static int Clamp(long value, int min, int max) => (int)Math.Max(min, Math.Min(max, value));

    private static long SaturatingMultiply(long value, long factor) =>
        value > long.MaxValue / factor ? long.MaxValue : value * factor;

    /// <summary>Python's <c>a or b</c> for strings: only an unset or empty value falls through.</summary>
    private static string Or(string? value, string fallback) => string.IsNullOrEmpty(value) ? fallback : value;

    private static string? OrNullable(string? value, string? fallback) => string.IsNullOrEmpty(value) ? fallback : value;

    private static string? NullIfEmpty(string? value) => string.IsNullOrEmpty(value) ? null : value;
}
