namespace Weir.Core.Configuration;

/// <summary>How the session cookie's <c>Secure</c> flag is decided (<c>WEIR_SESSION_COOKIE_SECURE</c>).</summary>
public enum CookieSecureMode
{
    /// <summary>HTTPS-only exactly when the request arrived over HTTPS.</summary>
    Auto,
    Always,
    Never,
}

/// <summary>The session cookie's <c>SameSite</c> value (<c>WEIR_SESSION_COOKIE_SAMESITE</c>).</summary>
public enum CookieSameSite
{
    Lax,
    Strict,
    None,
}

/// <summary>
/// Runtime configuration loaded once at process start, read from the same <c>WEIR_*</c>
/// environment variables, with the same defaults and clamps, as the Python backend's
/// <c>weir.core.config.WeirSettings</c>. Build it with <see cref="WeirOptionsLoader"/>.
/// </summary>
/// <remarks>
/// Values that Python keeps as unbounded integers are <see cref="long"/> here; inputs outside
/// the <see cref="long"/> range saturate instead of growing without limit.
/// </remarks>
public sealed record WeirOptions
{
    public required string Env { get; init; }
    public required string LogLevel { get; init; }
    public required IReadOnlyList<string> CorsOrigins { get; init; }
    public required string? SessionSecret { get; init; }
    public required string? CredentialsSecret { get; init; }
    public required IReadOnlyList<string> PreviousCredentialsSecrets { get; init; }
    public required string SessionCookieName { get; init; }
    public required CookieSecureMode SessionCookieSecureMode { get; init; }
    public required CookieSameSite SessionCookieSameSite { get; init; }
    public required long SessionIdleMinutes { get; init; }
    public required long SessionAbsoluteDays { get; init; }
    public required long SessionTrustedIdleMinutes { get; init; }
    public required long SessionTrustedAbsoluteDays { get; init; }
    public required IReadOnlyList<string> TrustedBrowserOriginsOverride { get; init; }
    public required IReadOnlyList<string> TrustedProxyIps { get; init; }
    public required long AuthLoginRateMaxAttempts { get; init; }
    public required long AuthLoginRateWindowSeconds { get; init; }
    public required long BootstrapRateMaxAttempts { get; init; }
    public required long BootstrapRateWindowSeconds { get; init; }
    public required bool SecurityEnableHsts { get; init; }
    public required string? MetricsBearerToken { get; init; }

    /// <summary>
    /// Guards the hand-off intake webhook for installs with no per-connection secret yet.
    /// Read from <c>WEIR_MEDIA_MANAGER_WEBHOOK_SECRET</c>, then the legacy <c>WEIR_SUBBER_WEBHOOK_SECRET</c>.
    /// </summary>
    public required string? MediaManagerWebhookSecret { get; init; }

    public required string WeirHome { get; init; }
    public required string DbPath { get; init; }
    public required string BackupDir { get; init; }
    public required string LogDir { get; init; }
    public required string TempDir { get; init; }

    /// <summary>0 = no in-process Refiner workers; 1..8 worker slots otherwise.</summary>
    public required int RefinerWorkerCount { get; init; }

    /// <summary>
    /// How long a worker's claim on a <c>refiner_jobs</c> row lasts before another worker may reclaim
    /// it (<c>WEIR_REFINER_JOB_LEASE_SECONDS</c>, #540 item 1). A heartbeat renews it roughly every
    /// third of this while a handler runs, so a job taking longer than this is still never claimed
    /// twice; this only bounds how long a crashed worker's row sits unclaimed before recovery.
    /// </summary>
    public required int RefinerJobLeaseSeconds { get; init; }
    public required bool RefinerWatcherEnabled { get; init; }
    public required double RefinerWatcherDebounceSeconds { get; init; }
    /// <summary>
    /// #533: the global kill switch for the periodic watched-folder scan timer itself
    /// (<c>WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED</c>, default on). Distinct
    /// from <see cref="RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs"/>, which only
    /// controls whether a periodic scan that *does* run may queue remux work off what it finds — with
    /// this off, no periodic scan runs at all for any scope, regardless of that other setting or of a
    /// library's own <c>schedule_enabled</c>/<c>enabled</c> columns. A manual scan (the HTTP enqueue
    /// route) is unaffected: it is a one-off request, not the timer this switch stops.
    /// </summary>
    public required bool RefinerWatchedFolderRemuxScanDispatchScheduleEnabled { get; init; }

    public required bool RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs { get; init; }
    public required int RefinerProbeSizeMb { get; init; }
    public required int RefinerAnalyzeDurationSeconds { get; init; }
    public required int RefinerWatchedFolderMinFileAgeSeconds { get; init; }
    public required int RefinerMovieOutputCleanupMinAgeSeconds { get; init; }
    public required int RefinerTvOutputCleanupMinAgeSeconds { get; init; }
    public required bool RefinerWorkTempStaleSweepMovieScheduleEnabled { get; init; }
    public required int RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds { get; init; }
    public required bool RefinerWorkTempStaleSweepTvScheduleEnabled { get; init; }
    public required int RefinerWorkTempStaleSweepTvScheduleIntervalSeconds { get; init; }
    public required int RefinerWorkTempStaleSweepMinStaleAgeSeconds { get; init; }
    public required bool RefinerMovieFailureCleanupScheduleEnabled { get; init; }
    public required int RefinerMovieFailureCleanupScheduleIntervalSeconds { get; init; }
    public required bool RefinerTvFailureCleanupScheduleEnabled { get; init; }
    public required int RefinerTvFailureCleanupScheduleIntervalSeconds { get; init; }
    public required int RefinerMovieFailureCleanupGracePeriodSeconds { get; init; }
    public required int RefinerTvFailureCleanupGracePeriodSeconds { get; init; }

    /// <summary>Legacy read only; remux paths come from saved Refiner settings.</summary>
    public required string? RefinerRemuxMediaRoot { get; init; }

    public required int JobRowsRetentionDays { get; init; }
    public required int JobRowsRetentionScheduleIntervalSeconds { get; init; }
    public required string? ArrRadarrBaseUrl { get; init; }
    public required string? ArrRadarrApiKey { get; init; }
    public required string? ArrSonarrBaseUrl { get; init; }
    public required string? ArrSonarrApiKey { get; init; }

    /// <summary>
    /// The built web app to serve (<c>WEIR_WEB_DIST</c>), resolved to an absolute path, or
    /// <see langword="null"/> when unset. Whether it holds an <c>index.html</c> is checked per request.
    /// </summary>
    public required string? WebDist { get; init; }

    /// <summary><c>WEIR_VERSION</c> when set; otherwise the build's own version is reported.</summary>
    public required string? VersionOverride { get; init; }

    /// <summary><c>WEIR_RUNTIME</c> (<c>windows</c>, <c>docker</c> or <c>source</c>), which the update check reports as the install type.</summary>
    public string? RuntimeKind { get; init; }

    /// <summary>
    /// #555: whether Weir should <c>chown</c> a file it just published, or a folder it just created for one, to
    /// <see cref="OutputOwnershipUid"/>/<see cref="OutputOwnershipGid"/> (<c>WEIR_CHOWN_OUTPUT</c>, default off).
    /// Linux only; ignored on Windows (logged once at startup when set — there is no POSIX owner there).
    /// </summary>
    public required bool OutputOwnershipChownEnabled { get; init; }

    /// <summary>
    /// The target owner for <see cref="OutputOwnershipChownEnabled"/>: the first non-blank of
    /// <c>WEIR_PUID</c>/<c>PUID</c> (default 1000) — the same variable the Docker entrypoint uses to remap the
    /// container's own runtime user, so a chowned output file matches the identity Weir itself runs as.
    /// </summary>
    public required uint OutputOwnershipUid { get; init; }

    /// <summary>The target group for <see cref="OutputOwnershipChownEnabled"/>: first non-blank of <c>WEIR_PGID</c>/<c>PGID</c> (default 1000).</summary>
    public required uint OutputOwnershipGid { get; init; }

    /// <summary>
    /// Optional file mode applied to a file Weir just published (<c>WEIR_FILE_MODE_OUTPUT</c>, an octal string such
    /// as <c>664</c>). <see langword="null"/> when unset. Linux only.
    /// </summary>
    public required UnixFileMode? OutputOwnershipFileMode { get; init; }

    /// <summary>
    /// Optional directory mode applied to a folder Weir just created to publish into (<c>WEIR_DIR_MODE_OUTPUT</c>,
    /// an octal string such as <c>775</c> or the setgid form <c>2775</c>). <see langword="null"/> when unset. Linux only.
    /// </summary>
    public required UnixFileMode? OutputOwnershipDirectoryMode { get; init; }

    /// <summary>Origins allowed for the unsafe-request Origin/Referer check.</summary>
    public IReadOnlyList<string> TrustedBrowserOrigins =>
        TrustedBrowserOriginsOverride.Count > 0 ? TrustedBrowserOriginsOverride : CorsOrigins;
}
