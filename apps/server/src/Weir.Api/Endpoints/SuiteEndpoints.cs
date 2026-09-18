using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Logging;
using Weir.Api.Http;
using Weir.Core;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Logs;
using Weir.Core.Metrics;
using Weir.Core.Settings;
using Weir.Core.Time;
using Weir.Core.Updates;
using Weir.Core.Validation;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Browse;
using Weir.Infrastructure.Http;
using Weir.Infrastructure.Logging;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Runtime;
using Weir.Infrastructure.Settings;

namespace Weir.Api.Endpoints;

/// <summary>
/// Suite-wide settings, configuration bundles and snapshots, logs, metrics, updates and operational
/// history (ports of <c>weir.platform.suite_settings.router</c>, <c>system_configuration.router</c>,
/// <c>pause.api</c> and <c>local_browse.router</c>).
/// </summary>
public static class SuiteEndpoints
{
    public static IEndpointRouteBuilder MapSuiteEndpoints(this IEndpointRouteBuilder endpoints)
    {
        // weir.platform.system_configuration.router (registered before the suite router, as in Python).
        endpoints.MapV1("GET", "/system/suite-configuration-bundle", GetBundleAsync);
        endpoints.MapV1("PUT", "/system/suite-configuration-bundle", PutBundleAsync);
        endpoints.MapV1("GET", "/system/suite-configuration-backups", GetBackupsAsync);
        endpoints.MapV1("GET", "/system/suite-configuration-backups/{backup_id}/download", DownloadBackupAsync);

        // weir.platform.local_browse.router
        endpoints.MapV1("GET", "/system/directories", GetDirectoriesAsync);

        // #548: the external media tools this install actually has. No Python counterpart.
        endpoints.MapV1("GET", "/system/media-tools", GetMediaToolsAsync);

        // weir.platform.suite_settings.router
        endpoints.MapV1("GET", "/suite/settings", GetSettingsAsync);
        endpoints.MapV1("PUT", "/suite/settings", PutSettingsAsync);
        endpoints.MapV1("GET", "/suite/settings/configuration-bundle", GetBundleAsync);
        endpoints.MapV1("GET", "/suite/configuration-bundle", GetBundleAsync);
        endpoints.MapV1("PUT", "/suite/settings/configuration-bundle", PutBundleAsync);
        endpoints.MapV1("PUT", "/suite/configuration-bundle", PutBundleAsync);
        endpoints.MapV1("GET", "/suite/configuration-backups", GetBackupsAsync);
        endpoints.MapV1("GET", "/suite/configuration-backups/{backup_id}/download", DownloadBackupAsync);
        endpoints.MapV1("GET", "/suite/security-overview", GetSecurityOverviewAsync);
        endpoints.MapV1("GET", "/suite/update-status", GetUpdateStatusAsync);
        endpoints.MapV1("GET", "/suite/settings/update-status", GetUpdateStatusAsync);
        endpoints.MapV1("GET", "/suite/update-settings", GetUpdateSettingsAsync);
        endpoints.MapV1("PUT", "/suite/update-settings", PutUpdateSettingsAsync);
        endpoints.MapV1("GET", "/suite/update-state", GetUpdateStateAsync);
        endpoints.MapV1("POST", "/suite/apply-update", PostApplyUpdateAsync);
        endpoints.MapV1("GET", "/suite/operational-history/preview", GetOperationalHistoryPreviewAsync);
        endpoints.MapV1("POST", "/suite/operational-history/reset", PostOperationalHistoryResetAsync);
        endpoints.MapV1("GET", "/suite/logs", GetLogsAsync);
        endpoints.MapV1("GET", "/suite/metrics", GetMetricsAsync);

        // weir.platform.pause.api
        endpoints.MapV1("GET", "/pause", GetPauseAsync);
        endpoints.MapV1("PUT", "/pause", PutPauseAsync);
        return endpoints;
    }

    private static async Task<ApiResult> GetSettingsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(SuiteSettingsRules.BuildOut(await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false)));
    }

    private static async Task<ApiResult> PutSettingsAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var name = model.Str("product_display_name", minLength: 1, maxLength: 120);
        var notice = model.OptionalStr("signed_in_home_notice", maxLength: 4000);
        var wizard = model.OptionalStr("setup_wizard_state", minLength: 1, maxLength: 32);
        var timezone = model.Str("app_timezone", minLength: 1, maxLength: 120);
        var logRetention = model.Number("log_retention_days", 0, required: true, ge: 1, le: 3650);
        var activityRetention = model.OptionalInt("activity_retention_days", ge: 0, le: 3650);
        model.OptionalBool("application_logs_enabled");
        var backupEnabled = model.OptionalBool("configuration_backup_enabled");
        var backupHours = model.OptionalInt("configuration_backup_interval_hours", ge: 1, le: 720);
        var backupTime = model.OptionalStr("configuration_backup_preferred_time", minLength: 5, maxLength: 5);
        model.Finish(ExtraFields.Ignore);
        issues.ThrowIfAny();

        request.RequireConfirmationToken(csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        PyDict output;
        SuiteSettingsRecord updated;
        try
        {
            var normalized = SuiteSettingsRules.Normalize(
                new SuiteSettingsUpdate(name, notice, timezone, logRetention, wizard, activityRetention, backupEnabled, backupHours, backupTime),
                request.Service<ITimeZoneResolver>());
            var before = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
            await SuiteSettingsStore.UpdateAsync(uow, before, SuiteSettingsRules.Apply(before, normalized)).ConfigureAwait(false);
            updated = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
            output = SuiteSettingsRules.BuildOut(updated);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        PruneLog(request, (int)Math.Max(1, Math.Min(3650, updated.LogRetentionDays)));
        return ApiRoutes.Ok(output);
    }

    /// <summary>
    /// Deliberate fix (#536): the settings are already saved, so a log that cannot be pruned (Python fails on
    /// invalid UTF-8) is logged and never turns the response into a 500.
    /// </summary>
    private static void PruneLog(ApiRequest request, int keepDays)
    {
        var logger = request.LoggerFactory.CreateLogger("weir.core.logging");
        try
        {
            if (!request.Service<WeirLogFile>().Prune(keepDays))
            {
                logger.LogWarning("Suite log prune skipped because the active log could not be rewritten.");
            }
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            logger.LogWarning(exception, "Suite log prune skipped because the active log could not be rewritten.");
        }
    }

    private static async Task<ApiResult> GetBundleAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        try
        {
            return ApiRoutes.Ok(await ConfigurationBundleStore.BuildAsync(uow).ConfigureAwait(false));
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status500InternalServerError, exception.Message);
        }
    }

    private static async Task<ApiResult> PutBundleAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var bundle = model.Dict("bundle");
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        request.RequireConfirmationToken(csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        try
        {
            await ConfigurationBundleStore.ApplyAsync(uow, bundle, request.Service<ITimeZoneResolver>()).ConfigureAwait(false);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await ConfigurationBundleStore.BuildAsync(uow).ConfigureAwait(false));
    }

    private static async Task<ApiResult> GetBackupsAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var backups = request.Service<ConfigurationBackups>();
        var rows = await ConfigurationBackups.ListAsync(uow).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("directory", backups.Directory)
            .Set("items", new PyList(rows.Select(row => (PyJson)ConfigurationBackups.ItemOut(row)))));
    }

    private static async Task<ApiResult> DownloadBackupAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var backupId = request.PathInt("backup_id", issues);
        issues.ThrowIfAny();
        var uow = await request.DbAsync().ConfigureAwait(false);
        string path;
        ConfigurationBackupRecord row;
        try
        {
            (path, row) = await request.Service<ConfigurationBackups>().GetFileAsync(uow, backupId).ConfigureAwait(false);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status404NotFound, exception.Message);
        }

        return new CustomApiResult(context => WriteFileAsync(context, path, row.FileName, "application/json"));
    }

    /// <summary>Starlette's <c>FileResponse</c> headers: disposition, length, last-modified and its md5 ETag.</summary>
    internal static async Task WriteFileAsync(HttpContext context, string path, string fileName, string mediaType)
    {
        var info = new FileInfo(path);
        var bytes = await File.ReadAllBytesAsync(path, context.RequestAborted).ConfigureAwait(false);
        var mtimeTicks = info.LastWriteTimeUtc.Ticks - DateTime.UnixEpoch.Ticks;
        var mtime = (mtimeTicks / TimeSpan.TicksPerSecond) + ((mtimeTicks % TimeSpan.TicksPerSecond) * 100 * 1e-9);
#pragma warning disable CA5351 // Starlette's ETag is an MD5 of mtime and size; it is not a security control.
        var etag = Convert.ToHexStringLower(MD5.HashData(Encoding.UTF8.GetBytes(PyJsonWriter.FloatRepr(mtime) + "-" + info.Length.ToString(CultureInfo.InvariantCulture))));
#pragma warning restore CA5351
        var quoted = Uri.EscapeDataString(fileName);
        context.Response.StatusCode = StatusCodes.Status200OK;
        context.Response.ContentType = mediaType;
        context.Response.Headers.ContentDisposition = quoted != fileName ? $"attachment; filename*=utf-8''{quoted}" : $"attachment; filename=\"{fileName}\"";
        context.Response.ContentLength = bytes.Length;
        context.Response.Headers.LastModified = info.LastWriteTimeUtc.ToString("ddd, dd MMM yyyy HH:mm:ss 'GMT'", CultureInfo.InvariantCulture);
        context.Response.Headers.ETag = $"\"{etag}\"";
        context.Response.Headers.AcceptRanges = "bytes";
        await context.Response.Body.WriteAsync(bytes, context.RequestAborted).ConfigureAwait(false);
    }

    /// <summary>
    /// #548: which external media tools this install has, and what they say they are. Weir bundles both in the
    /// Windows package (<c>server\bin\ffmpeg</c>, <c>server\bin\mkvtoolnix</c>) and the Docker image, but a
    /// source install provides its own, and until this endpoint existed there was no way for an operator to see
    /// whether the one that matters most for a library's writer setting — mkvmerge — had actually been found.
    /// That mattered: the writer setting defaults to "best", and "best" silently means ffmpeg wherever mkvmerge
    /// is missing, so an install with no mkvmerge looked identical to one that was using it.
    ///
    /// <para>
    /// Always 200. <c>mkvmerge: "not installed"</c> is the correct answer for an install without it, not a
    /// failure — the writer falls back to ffmpeg and everything still works, which is the whole reason
    /// <see cref="IMediaToolResolver.ResolveMkvmerge"/> returns null instead of throwing. A missing ffmpeg
    /// reports the same way rather than erroring, because an operator diagnosing exactly that needs the answer,
    /// not a 500.
    /// </para>
    /// </summary>
    private static async Task<ApiResult> GetMediaToolsAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var report = await request.Service<MediaTools>()
            .DescribeVersionsAsync(request.Context.RequestAborted)
            .ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("ffmpeg", report.Ffmpeg)
            .Set("mkvmerge", report.Mkvmerge));
    }

    private static async Task<ApiResult> GetDirectoriesAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        try
        {
            return ApiRoutes.Ok(DirectoryBrowser.Browse(request.Query("path")));
        }
        catch (DirectoryBrowseException exception)
        {
            throw new ApiException(exception.StatusCode, exception.Message);
        }
    }

    private static async Task<ApiResult> GetSecurityOverviewAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(SecurityOverview.Build(request.Options));
    }

    private static async Task<ApiResult> GetUpdateStatusAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var installType = UpdateFiles.DetectInstallType(request.Options.RuntimeKind);
        var currentVersion = WeirVersion.Resolve(request.Options.VersionOverride);
        if (currentVersion.Length == 0)
        {
            currentVersion = "0.0.0";
        }

        try
        {
            var release = await request.Service<IReleaseCatalogClient>().FetchLatestAsync(currentVersion, request.Context.RequestAborted).ConfigureAwait(false);
            return ApiRoutes.Ok(UpdateStatus.FromRelease(currentVersion, installType, release));
        }
        catch (ReleaseFetchException exception) when (exception.StatusCode == 404)
        {
            return ApiRoutes.Ok(UpdateStatus.Unavailable(currentVersion, installType, "not_published", "No public Weir release is published yet."));
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !request.Context.RequestAborted.IsCancellationRequested)
        {
            return ApiRoutes.Ok(UpdateStatus.Unavailable(currentVersion, installType, "unavailable", "Could not check for updates right now."));
        }
    }

    private static async Task<ApiResult> GetUpdateSettingsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var logger = request.LoggerFactory.CreateLogger("weir.platform.suite_settings.update_service");
        return ApiRoutes.Ok(request.Service<UpdateFiles>().ReadSettings(path => logger.LogWarning(
            "Update settings at {Path} could not be read. Falling back to notify-only so a damaged file cannot install an update the operator did not choose.",
            path)));
    }

    private static async Task<ApiResult> PutUpdateSettingsAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var mode = model.Literal("mode", UpdateStatus.Modes);
        var checkOnStartup = model.Bool("check_on_startup", defaultValue: true);
        var interval = model.Number("check_interval_minutes", 60, required: false, ge: 1, le: 10080);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        request.RequireConfirmationToken(csrfToken);
        return ApiRoutes.Ok(request.Service<UpdateFiles>().WriteSettings(mode, checkOnStartup, interval));
    }

    private static async Task<ApiResult> GetUpdateStateAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(request.Service<UpdateFiles>().ReadState());
    }

    private static async Task<ApiResult> PostApplyUpdateAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        request.RequireConfirmationToken(csrfToken);
        var files = request.Service<UpdateFiles>();
        var state = files.ReadState();
        if (!(state.Get("downloaded")?.IsTruthy ?? false))
        {
            throw new ApiException(StatusCodes.Status409Conflict, "No downloaded update is pending.");
        }

        files.WriteApplyFlag();
        return ApiRoutes.Ok(state);
    }

    private static async Task<ApiResult> GetOperationalHistoryPreviewAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(HistoryOut("preview", await OperationalHistoryStore.PreviewAsync(uow).ConfigureAwait(false)));
    }

    private static async Task<ApiResult> PostOperationalHistoryResetAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var confirm = model.Str("confirm", minLength: 5, maxLength: 32);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        request.RequireConfirmationToken(csrfToken);
        if (!string.Equals(confirm.Trim().ToUpperInvariant(), "RESET", StringComparison.Ordinal))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "Type RESET to confirm clearing activity history.");
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var result = await OperationalHistoryStore.ResetAsync(uow).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(HistoryOut("reset", result));
    }

    private static PyDict HistoryOut(string status, OperationalHistoryStore.ResetResult result) => new PyDict()
        .Set("status", status)
        .Set("activity_events_deleted", result.ActivityEventsDeleted)
        .Set("jobs_deleted", result.ProcessingJobsDeleted)
        .Set("total_deleted", result.TotalDeleted);

    private static async Task<ApiResult> GetLogsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var level = request.Query("level");
        var search = request.Query("search");
        bool? hasException = null;
        if (request.Query("has_exception") is { } rawHasException && PydanticRules.TryBool(new PyStr(rawHasException), ["query", "has_exception"], issues, out var parsedHasException))
        {
            hasException = parsedHasException;
        }

        long limit = 100;
        if (request.Query("limit") is { } rawLimit && PydanticRules.TryInt(new PyStr(rawLimit), ["query", "limit"], null, null, issues, out var parsedLimit))
        {
            limit = parsedLimit > long.MaxValue ? long.MaxValue : parsedLimit < long.MinValue ? long.MinValue : (long)parsedLimit;
        }

        issues.ThrowIfAny();
        var filter = new SuiteLogFilter(level, search, hasException, limit);
        var logFile = request.Service<WeirLogFile>();
        var result = SuiteLogFilter.Empty;
        if (File.Exists(logFile.Path))
        {
            if (logFile.ReadLines(filter.Add))
            {
                result = filter.Result();
            }
            else
            {
                request.LoggerFactory.CreateLogger("weir.platform.suite_settings.logs_service").LogWarning("Suite log read skipped because the active log could not be opened.");
            }
        }

        var items = new List<PyJson>();
        var logger = request.LoggerFactory.CreateLogger("weir.platform.suite_settings.router");
        foreach (var entry in result.Items)
        {
            var output = SuiteLogFilter.ToOut(entry);
            if (output is null)
            {
                logger.LogWarning("Skipping suite log entry with invalid timestamp: {Timestamp}", entry.Timestamp);
                continue;
            }

            items.Add(output);
        }

        return ApiRoutes.Ok(new PyDict()
            .Set("items", new PyList(items))
            .Set("total", result.Total)
            .Set("counts", new PyDict().Set("error", result.Errors).Set("warning", result.Warnings).Set("information", result.Information)));
    }

    private static async Task<ApiResult> GetMetricsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(request.Service<RuntimeMetricsStore>().SuiteMetricsOut());
    }

    private static async Task<ApiResult> GetPauseAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await PauseOutAsync(request).ConfigureAwait(false));
    }

    private static async Task<ApiResult> PutPauseAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var paused = model.Bool("paused", defaultValue: false, required: true);
        var minutes = model.OptionalInt("pause_for_minutes", ge: 1, le: 10080);
        var scanWhilePaused = model.Bool("scan_while_paused", defaultValue: true);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        request.ValidateBrowserPostOrigin();
        var secret = request.RequireSessionSecret();
        if (!request.VerifyCsrf(secret, csrfToken, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "Invalid or expired CSRF token.");
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        PyDateTime? until = null;
        if (paused && minutes is { } m)
        {
            until = PyDateTime.FromUtc(PyDateTime.UtcNow(request.Time).AsUtc.AddMinutes(m));
        }

        var updated = row with { ProcessingPaused = paused, ScanWhilePaused = scanWhilePaused, ProcessingPausedUntil = until };
        await SuiteSettingsStore.UpdateAsync(uow, row, updated).ConfigureAwait(false);
        return ApiRoutes.Ok(await PauseOutAsync(request).ConfigureAwait(false));
    }

    /// <summary><c>_out</c>: resolve the pause, clearing a lapsed one so the row and the screen agree.</summary>
    private static async Task<PyDict> PauseOutAsync(ApiRequest request)
    {
        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var state = PauseState.Resolve(row, PyDateTime.UtcNow(request.Time).AsUtc);
        if (state.Expired)
        {
            await SuiteSettingsStore.UpdateAsync(uow, row, row with { ProcessingPaused = false, ProcessingPausedUntil = null }).ConfigureAwait(false);
        }

        return state.ToOut();
    }
}
