using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.Refiner;
using Weir.Core.Validation;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Settings;

namespace Weir.Api.Endpoints;

/// <summary>
/// Operator-editable automation settings, the read-only runtime snapshot, the hardware-acceleration
/// report and the metadata-provider connection (ports of <c>refiner_operator_settings_api.py</c>,
/// <c>refiner_runtime_settings_api.py</c>, <c>refiner_hardware_api.py</c> and
/// <c>refiner_metadata_provider_api.py</c> — the settings half only; see <see cref="MetadataProviderStore"/>).
/// </summary>
public static class RefinerSettingsEndpoints
{
    public static IEndpointRouteBuilder MapRefinerSettingsEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/operator-settings", GetOperatorSettingsAsync);
        endpoints.MapV1("PUT", "/refiner/operator-settings", PutOperatorSettingsAsync);
        endpoints.MapV1("GET", "/refiner/runtime-settings", GetRuntimeSettingsAsync);
        endpoints.MapV1("GET", "/refiner/hardware", GetHardwareAsync);
        endpoints.MapV1("GET", "/refiner/metadata-provider", GetMetadataProviderAsync);
        endpoints.MapV1("PUT", "/refiner/metadata-provider", PutMetadataProviderAsync);
        endpoints.MapV1("POST", "/refiner/metadata-provider/test", PostMetadataProviderTestAsync);
        return endpoints;
    }

    private static PyDict OperatorSettingsOut(RefinerOperatorSettingsRecord row, string timezone) => new PyDict()
        .Set("max_concurrent_files", OperatorSettingsRules.ClampMaxConcurrentFiles(row.MaxConcurrentFiles))
        .Set("runner_capacity", OperatorSettingsRules.ClampRunnerCapacity(row.RunnerCapacity))
        .Set("runner_cost_sd", OperatorSettingsRules.ClampRunnerCost(row.RunnerCostSd))
        .Set("runner_cost_720p", OperatorSettingsRules.ClampRunnerCost(row.RunnerCost720P))
        .Set("runner_cost_1080p", OperatorSettingsRules.ClampRunnerCost(row.RunnerCost1080P))
        .Set("runner_cost_4k", OperatorSettingsRules.ClampRunnerCost(row.RunnerCost4K))
        .Set("work_temp_stale_sweep_enabled", row.WorkTempStaleSweepEnabled)
        .Set("failure_cleanup_enabled", row.FailureCleanupEnabled)
        .Set("keep_failed_work_files", row.KeepFailedWorkFiles)
        .Set("file_log_retention_days", OperatorSettingsRules.ClampFileLogRetentionDays(row.FileLogRetentionDays))
        .Set("verbose_detection_logging", row.VerboseDetectionLogging)
        .Set("runner_cost_undetermined", OperatorSettingsRules.ClampRunnerCost(row.RunnerCostUndetermined))
        .Set("min_file_age_seconds", OperatorSettingsRules.ClampMinFileAgeSeconds(row.MinFileAgeSeconds))
        .Set("refiner_min_input_file_size_mb", OperatorSettingsRules.ClampSizeMb(row.RefinerMinInputFileSizeMb))
        .Set("minimum_free_disk_space_mb", OperatorSettingsRules.ClampSizeMb(row.MinimumFreeDiskSpaceMb))
        .Set("movie_schedule_enabled", row.MovieScheduleEnabled)
        .Set("movie_schedule_hours_limited", row.MovieScheduleHoursLimited)
        .Set("movie_schedule_days", row.MovieScheduleDays)
        .Set("movie_schedule_start", row.MovieScheduleStart)
        .Set("movie_schedule_end", row.MovieScheduleEnd)
        .Set("tv_schedule_enabled", row.TvScheduleEnabled)
        .Set("tv_schedule_hours_limited", row.TvScheduleHoursLimited)
        .Set("tv_schedule_days", row.TvScheduleDays)
        .Set("tv_schedule_start", row.TvScheduleStart)
        .Set("tv_schedule_end", row.TvScheduleEnd)
        .Set("schedule_timezone", timezone)
        .Set("updated_at", row.UpdatedAt.IsoFormat());

    private static async Task<ApiResult> GetOperatorSettingsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var suite = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        return ApiRoutes.Ok(OperatorSettingsOut(row, string.IsNullOrWhiteSpace(suite.AppTimezone) ? "UTC" : suite.AppTimezone.Trim()));
    }

    private static async Task<ApiResult> PutOperatorSettingsAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var maxConcurrentFiles = model.OptionalInt("max_concurrent_files", ge: 1, le: 8);
        var runnerCapacity = model.OptionalInt("runner_capacity", ge: 1, le: 64);
        var runnerCostSd = model.OptionalInt("runner_cost_sd", ge: 0, le: 64);
        var runnerCost720P = model.OptionalInt("runner_cost_720p", ge: 0, le: 64);
        var runnerCost1080P = model.OptionalInt("runner_cost_1080p", ge: 0, le: 64);
        var runnerCost4K = model.OptionalInt("runner_cost_4k", ge: 0, le: 64);
        var runnerCostUndetermined = model.OptionalInt("runner_cost_undetermined", ge: 0, le: 64);
        var workTempStaleSweepEnabled = model.OptionalBool("work_temp_stale_sweep_enabled");
        var failureCleanupEnabled = model.OptionalBool("failure_cleanup_enabled");
        var keepFailedWorkFiles = model.OptionalBool("keep_failed_work_files");
        var fileLogRetentionDays = model.OptionalInt("file_log_retention_days", ge: 0, le: 3650);
        var verboseDetectionLogging = model.OptionalBool("verbose_detection_logging");
        var minFileAgeSeconds = model.OptionalInt("min_file_age_seconds", ge: 0, le: 7 * 24 * 3600);
        var refinerMinInputFileSizeMb = model.OptionalInt("refiner_min_input_file_size_mb", ge: 0, le: 1024 * 1024);
        var minimumFreeDiskSpaceMb = model.OptionalInt("minimum_free_disk_space_mb", ge: 0, le: 1024 * 1024);
        var movieScheduleEnabled = model.OptionalBool("movie_schedule_enabled");
        var movieScheduleHoursLimited = model.OptionalBool("movie_schedule_hours_limited");
        var movieScheduleDays = model.OptionalStr("movie_schedule_days", maxLength: 2000);
        var movieScheduleStart = model.OptionalStr("movie_schedule_start", maxLength: 5);
        var movieScheduleEnd = model.OptionalStr("movie_schedule_end", maxLength: 5);
        var tvScheduleEnabled = model.OptionalBool("tv_schedule_enabled");
        var tvScheduleHoursLimited = model.OptionalBool("tv_schedule_hours_limited");
        var tvScheduleDays = model.OptionalStr("tv_schedule_days", maxLength: 2000);
        var tvScheduleStart = model.OptionalStr("tv_schedule_start", maxLength: 5);
        var tvScheduleEnd = model.OptionalStr("tv_schedule_end", maxLength: 5);
        model.Finish(ExtraFields.Forbid);

        var movieGroupCount = new bool?[] { movieScheduleEnabled, movieScheduleHoursLimited }.Count(v => v is not null) +
                               new[] { movieScheduleDays, movieScheduleStart, movieScheduleEnd }.Count(v => v is not null);
        if (movieGroupCount != 0 && movieGroupCount != 5)
        {
            issues.Add(new ValidationIssue("value_error", ["body"], "Value error, Refiner movie schedule fields must all be omitted or all provided together.", PyJson.Null));
        }

        var tvGroupCount = new bool?[] { tvScheduleEnabled, tvScheduleHoursLimited }.Count(v => v is not null) +
                            new[] { tvScheduleDays, tvScheduleStart, tvScheduleEnd }.Count(v => v is not null);
        if (tvGroupCount != 0 && tvGroupCount != 5)
        {
            issues.Add(new ValidationIssue("value_error", ["body"], "Value error, Refiner TV schedule fields must all be omitted or all provided together.", PyJson.Null));
        }

        var hasProcessField = maxConcurrentFiles is not null || runnerCapacity is not null || runnerCostSd is not null ||
                               runnerCost720P is not null || runnerCost1080P is not null || runnerCost4K is not null ||
                               runnerCostUndetermined is not null || workTempStaleSweepEnabled is not null || failureCleanupEnabled is not null ||
                               keepFailedWorkFiles is not null || fileLogRetentionDays is not null || verboseDetectionLogging is not null ||
                               minFileAgeSeconds is not null || refinerMinInputFileSizeMb is not null || minimumFreeDiskSpaceMb is not null;
        if (!hasProcessField && movieScheduleEnabled is null && tvScheduleEnabled is null)
        {
            issues.Add(new ValidationIssue("value_error", ["body"], "Value error, No Refiner operator settings fields to update.", PyJson.Null));
        }

        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var before = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var after = before;
        if (maxConcurrentFiles is { } m)
        {
            after = after with { MaxConcurrentFiles = OperatorSettingsRules.ClampMaxConcurrentFiles(m) };
        }

        if (runnerCapacity is { } rc)
        {
            after = after with { RunnerCapacity = Math.Clamp(rc, 0, 64) };
        }

        if (runnerCostSd is { } v1)
        {
            after = after with { RunnerCostSd = Math.Clamp(v1, 0, 64) };
        }

        if (runnerCost720P is { } v2)
        {
            after = after with { RunnerCost720P = Math.Clamp(v2, 0, 64) };
        }

        if (runnerCost1080P is { } v3)
        {
            after = after with { RunnerCost1080P = Math.Clamp(v3, 0, 64) };
        }

        if (runnerCost4K is { } v4)
        {
            after = after with { RunnerCost4K = Math.Clamp(v4, 0, 64) };
        }

        if (runnerCostUndetermined is { } v5)
        {
            after = after with { RunnerCostUndetermined = Math.Clamp(v5, 0, 64) };
        }

        if (fileLogRetentionDays is { } fl)
        {
            after = after with { FileLogRetentionDays = OperatorSettingsRules.ClampFileLogRetentionDays(fl) };
        }

        if (workTempStaleSweepEnabled is { } wt)
        {
            after = after with { WorkTempStaleSweepEnabled = wt };
        }

        if (failureCleanupEnabled is { } fc)
        {
            after = after with { FailureCleanupEnabled = fc };
        }

        if (keepFailedWorkFiles is { } kf)
        {
            after = after with { KeepFailedWorkFiles = kf };
        }

        if (verboseDetectionLogging is { } vd)
        {
            after = after with { VerboseDetectionLogging = vd };
        }

        if (minFileAgeSeconds is { } mfa)
        {
            after = after with { MinFileAgeSeconds = OperatorSettingsRules.ClampMinFileAgeSeconds(mfa) };
        }

        if (refinerMinInputFileSizeMb is { } rmin)
        {
            after = after with { RefinerMinInputFileSizeMb = OperatorSettingsRules.ClampSizeMb(rmin) };
        }

        if (minimumFreeDiskSpaceMb is { } mfd)
        {
            after = after with { MinimumFreeDiskSpaceMb = OperatorSettingsRules.ClampSizeMb(mfd) };
        }

        try
        {
            if (movieScheduleEnabled is { } me)
            {
                after = after with
                {
                    MovieScheduleEnabled = me,
                    MovieScheduleHoursLimited = movieScheduleHoursLimited ?? false,
                    MovieScheduleDays = ScheduleWindow.ValidateDaysCsv(movieScheduleDays),
                    MovieScheduleStart = ScheduleWindow.NormalizeHhmm(movieScheduleStart, "00:00"),
                    MovieScheduleEnd = ScheduleWindow.NormalizeHhmm(movieScheduleEnd, "23:59"),
                };
            }

            if (tvScheduleEnabled is { } te)
            {
                after = after with
                {
                    TvScheduleEnabled = te,
                    TvScheduleHoursLimited = tvScheduleHoursLimited ?? false,
                    TvScheduleDays = ScheduleWindow.ValidateDaysCsv(tvScheduleDays),
                    TvScheduleStart = ScheduleWindow.NormalizeHhmm(tvScheduleStart, "00:00"),
                    TvScheduleEnd = ScheduleWindow.NormalizeHhmm(tvScheduleEnd, "23:59"),
                };
            }
        }
        catch (ScheduleWindowException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await OperatorSettingsStore.UpdateAsync(uow, before, after).ConfigureAwait(false);
        var updated = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var suite = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(OperatorSettingsOut(updated, string.IsNullOrWhiteSpace(suite.AppTimezone) ? "UTC" : suite.AppTimezone.Trim()));
    }

    private static async Task<ApiResult> GetRuntimeSettingsAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var settings = RuntimeVisibility.From(request.Options);
        return ApiRoutes.Ok(new PyDict()
            .Set("in_process_refiner_worker_count", settings.InProcessRefinerWorkerCount)
            .Set("in_process_workers_disabled", settings.InProcessWorkersDisabled)
            .Set("in_process_workers_enabled", settings.InProcessWorkersEnabled)
            .Set("worker_mode_summary", settings.WorkerModeSummary)
            .Set("sqlite_throughput_note", settings.SqliteThroughputNote)
            .Set("configuration_note", settings.ConfigurationNote)
            .Set("visibility_note", settings.VisibilityNote)
            .Set("refiner_media_extensions", new PyList(settings.RefinerMediaExtensions.Select(e => (PyJson)PyJson.Of(e))))
            .Set("refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs", settings.RefinerWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs)
            .Set("refiner_probe_size_mb", settings.RefinerProbeSizeMb)
            .Set("refiner_analyze_duration_seconds", settings.RefinerAnalyzeDurationSeconds)
            .Set("refiner_watched_folder_min_file_age_seconds", settings.RefinerWatchedFolderMinFileAgeSeconds)
            .Set("refiner_movie_output_cleanup_min_age_seconds", settings.RefinerMovieOutputCleanupMinAgeSeconds)
            .Set("movie_output_cleanup_configuration_note", settings.MovieOutputCleanupConfigurationNote)
            .Set("refiner_tv_output_cleanup_min_age_seconds", settings.RefinerTvOutputCleanupMinAgeSeconds)
            .Set("tv_output_cleanup_configuration_note", settings.TvOutputCleanupConfigurationNote)
            .Set("watched_folder_scan_periodic_configuration_note", settings.WatchedFolderScanPeriodicConfigurationNote)
            .Set("refiner_work_temp_stale_sweep_movie_schedule_enabled", settings.RefinerWorkTempStaleSweepMovieScheduleEnabled)
            .Set("refiner_work_temp_stale_sweep_movie_schedule_interval_seconds", settings.RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds)
            .Set("refiner_work_temp_stale_sweep_tv_schedule_enabled", settings.RefinerWorkTempStaleSweepTvScheduleEnabled)
            .Set("refiner_work_temp_stale_sweep_tv_schedule_interval_seconds", settings.RefinerWorkTempStaleSweepTvScheduleIntervalSeconds)
            .Set("refiner_work_temp_stale_sweep_min_stale_age_seconds", settings.RefinerWorkTempStaleSweepMinStaleAgeSeconds)
            .Set("refiner_movie_failure_cleanup_schedule_enabled", settings.RefinerMovieFailureCleanupScheduleEnabled)
            .Set("refiner_movie_failure_cleanup_schedule_interval_seconds", settings.RefinerMovieFailureCleanupScheduleIntervalSeconds)
            .Set("refiner_tv_failure_cleanup_schedule_enabled", settings.RefinerTvFailureCleanupScheduleEnabled)
            .Set("refiner_tv_failure_cleanup_schedule_interval_seconds", settings.RefinerTvFailureCleanupScheduleIntervalSeconds)
            .Set("refiner_movie_failure_cleanup_grace_period_seconds", settings.RefinerMovieFailureCleanupGracePeriodSeconds)
            .Set("refiner_tv_failure_cleanup_grace_period_seconds", settings.RefinerTvFailureCleanupGracePeriodSeconds)
            .Set("failure_cleanup_configuration_note", settings.FailureCleanupConfigurationNote)
            .Set("work_temp_stale_sweep_periodic_configuration_note", settings.WorkTempStaleSweepPeriodicConfigurationNote));
    }

    private static async Task<ApiResult> GetHardwareAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        IMediaToolResolver resolver = request.Service<IMediaToolResolver>();
        string ffmpeg;
        try
        {
            (_, ffmpeg) = resolver.Resolve();
        }
        catch (MediaToolException exception)
        {
            return ApiRoutes.Ok(new PyDict()
                .Set("detected", false)
                .Set("available_methods", new PyList([]))
                .Set("vendors", new PyList([]))
                .Set("selectable_vendors", new PyList(HardwareAcceleration.VendorMethods.Select(v => v.Key).Order(StringComparer.Ordinal).Select(k => (PyJson)PyJson.Of(k))))
                .Set("strictness_levels", new PyList(HardwareAcceleration.StrictnessLevels.Select(l => (PyJson)PyJson.Of(l))))
                .Set("detail", $"Weir could not find ffmpeg, so it cannot report acceleration methods. {exception.Message}"));
        }

        var mediaTools = request.Service<MediaTools>();
        var report = await mediaTools.DetectAccelerationAsync(ffmpeg, request.Context.RequestAborted).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("detected", report.Detected)
            .Set("available_methods", new PyList(report.AvailableMethods.Select(m => (PyJson)PyJson.Of(m))))
            .Set("vendors", new PyList(report.Vendors.Select(v => (PyJson)PyJson.Of(v))))
            .Set("selectable_vendors", new PyList(HardwareAcceleration.VendorMethods.Select(v => v.Key).Order(StringComparer.Ordinal).Select(k => (PyJson)PyJson.Of(k))))
            .Set("strictness_levels", new PyList(HardwareAcceleration.StrictnessLevels.Select(l => (PyJson)PyJson.Of(l))))
            .Set("detail", report.Detail));
    }

    private static PyDict MetadataProviderOut(MetadataProviderView view) => new PyDict()
        .Set("provider", view.Provider)
        .Set("base_url", view.BaseUrl)
        .Set("key_configured", view.KeyConfigured)
        .Set("known_providers", new PyList(view.KnownProviders.Select(p => (PyJson)PyJson.Of(p))));

    private static async Task<ApiResult> GetMetadataProviderAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(MetadataProviderOut(MetadataProviderStore.View(row)));
    }

    private static async Task<ApiResult> PutMetadataProviderAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var provider = model.Literal("provider", ["", "tmdb"], defaultValue: "");
        var baseUrl = model.OptionalStr("base_url", defaultValue: "", maxLength: 500) ?? string.Empty;
        var apiKey = model.OptionalStr("api_key", maxLength: 500);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await MetadataProviderStore.ApplyAsync(uow, request.Options, request.Time, provider, baseUrl, apiKey).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(MetadataProviderOut(MetadataProviderStore.View(row)));
    }

    private static async Task<ApiResult> PostMetadataProviderTestAsync(ApiRequest request)
    {
        // Same body shape as PUT (MetadataProviderIn); the test itself only reads what is already saved.
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Literal("provider", ["", "tmdb"], defaultValue: "");
        model.OptionalStr("base_url", defaultValue: "", maxLength: 500);
        model.OptionalStr("api_key", maxLength: 500);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        var result = string.IsNullOrWhiteSpace(row.MetadataProviderKeyCiphertext) || string.IsNullOrWhiteSpace(row.MetadataProvider)
            ? MetadataProviderStore.Test(row)
            : await request.Service<MetadataProviderService>().TestProviderAsync(uow, request.Context.RequestAborted).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("status", result.Status).Set("detail", result.Detail));
    }
}
