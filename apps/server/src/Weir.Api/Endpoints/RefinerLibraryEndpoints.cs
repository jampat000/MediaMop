using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Time;
using Weir.Core.Validation;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Endpoints;

/// <summary>Refiner libraries and rule sets — <c>/api/v1/refiner/libraries</c>, <c>/refiner/rule-sets</c>
/// (port of <c>refiner_libraries_api.py</c>). Discovery/import/drift/unlink and the reject-support gate
/// are not ported: they need the media-manager port (#520).</summary>
public static class RefinerLibraryEndpoints
{
    public static IEndpointRouteBuilder MapRefinerLibraryEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/libraries", GetLibrariesAsync);
        endpoints.MapV1("POST", "/refiner/libraries", PostLibraryAsync);
        endpoints.MapV1("GET", "/refiner/libraries/{library_id}", GetLibraryAsync);
        endpoints.MapV1("PUT", "/refiner/libraries/{library_id}", PutLibraryAsync);
        endpoints.MapV1("DELETE", "/refiner/libraries/{library_id}", DeleteLibraryAsync);
        endpoints.MapV1("POST", "/refiner/libraries/reorder", PostReorderAsync);
        endpoints.MapV1("GET", "/refiner/rule-sets", GetRuleSetsAsync);
        endpoints.MapV1("POST", "/refiner/rule-sets", PostRuleSetAsync);
        endpoints.MapV1("PUT", "/refiner/rule-sets/{rule_set_id}", PutRuleSetAsync);
        endpoints.MapV1("DELETE", "/refiner/rule-sets/{rule_set_id}", DeleteRuleSetAsync);
        return endpoints;
    }

    private static async Task<RefinerLibraryRecord> RequireLibraryAsync(UnitOfWork uow, long id) =>
        await LibraryStore.GetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "That Refiner library does not exist.");

    private static async Task<RefinerRuleSetRecord> RequireRuleSetAsync(UnitOfWork uow, long id) =>
        await LibraryStore.GetRuleSetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "That Refiner rule set does not exist.");

    private static async Task<PyDict> LibraryOutAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        var managerIds = await LibraryStore.ManagerConnectionIdsAsync(uow, row.Id).ConfigureAwait(false);
        var activeJobs = await LibraryStore.ActiveJobCountAsync(uow, row).ConfigureAwait(false);

        // The manager-coverage gate needs live connection health (#520); until then, "no manager linked"
        // is reported exactly as Python does, and any linked manager is reported as unreachable rather than
        // guessed healthy — never a false "connected".
        string coverage;
        string coverageDetail;
        if (managerIds.Count == 0)
        {
            coverage = "no_upstream_signal";
            coverageDetail = "No media manager is linked. Watched-folder remux can still run after local safety gates, " +
                              "but upstream import protection is reduced.";
        }
        else
        {
            coverage = "unreachable";
            coverageDetail = "A linked media manager did not answer its last connection test. Remux remains local, " +
                              "but manager-truth-dependent cleanup is held until the connection is available.";
        }

        return new PyDict()
            .Set("id", row.Id)
            .Set("name", row.Name)
            .Set("enabled", row.Enabled)
            .Set("media_type", row.MediaType)
            .Set("display_order", row.DisplayOrder)
            .Set("watched_folder", row.WatchedFolder)
            .Set("work_folder", row.WorkFolder)
            .Set("output_folder", row.OutputFolder)
            .Set("media_extensions_csv", row.MediaExtensionsCsv)
            .Set("exclude_markers_csv", row.ExcludeMarkersCsv)
            .Set("include_patterns_csv", row.IncludePatternsCsv)
            .Set("exclude_patterns_csv", row.ExcludePatternsCsv)
            .Set("min_file_size_mb", row.MinFileSizeMb)
            .Set("max_file_size_mb", row.MaxFileSizeMb)
            .Set("rejected_file_action", row.RejectedFileAction.Length > 0 ? row.RejectedFileAction : "leave")
            .Set("min_file_age_seconds", row.MinFileAgeSeconds)
            .Set("created_after", row.CreatedAfter?.PydanticJson())
            .Set("created_before", row.CreatedBefore?.PydanticJson())
            .Set("modified_after", row.ModifiedAfter?.PydanticJson())
            .Set("modified_before", row.ModifiedBefore?.PydanticJson())
            .Set("exclude_hidden", row.ExcludeHidden)
            .Set("top_level_only", row.TopLevelOnly)
            .Set("scan_interval_seconds", row.ScanIntervalSeconds)
            .Set("hold_minutes", row.HoldMinutes)
            .Set("sidecar_patterns_csv", row.SidecarPatternsCsv)
            .Set("preserve_original_timestamps", row.PreserveOriginalTimestamps)
            .Set("output_collision_policy", row.OutputCollisionPolicy.Length > 0 ? row.OutputCollisionPolicy : "replace")
            .Set("hardware_decode_mode", row.HardwareDecodeMode.Length > 0 ? row.HardwareDecodeMode : "off")
            .Set("hardware_device", row.HardwareDevice)
            .Set("hardware_disabled_vendors_csv", row.HardwareDisabledVendorsCsv)
            .Set("ffmpeg_strictness", row.FfmpegStrictness.Length > 0 ? row.FfmpegStrictness : "normal")
            .Set("file_detection_interval_seconds", row.FileDetectionIntervalSeconds)
            .Set("ignore_size_changes", row.IgnoreSizeChanges)
            .Set("skip_access_tests", row.SkipAccessTests)
            .Set("file_system_events_enabled", row.FileSystemEventsEnabled)
            .Set("schedule_grid", row.ScheduleGrid)
            .Set("max_attempts", row.MaxAttempts)
            .Set("retry_backoff_seconds", row.RetryBackoffSeconds)
            .Set("retry_execution_failures", row.RetryExecutionFailures)
            .Set("retry_preflight_failures", row.RetryPreflightFailures)
            .Set("failure_policy", RefinerFailurePolicies.Normalize(row.FailurePolicy))
            .Set("schedule_enabled", row.ScheduleEnabled)
            .Set("schedule_hours_limited", row.ScheduleHoursLimited)
            .Set("schedule_days", row.ScheduleDays)
            .Set("schedule_start", row.ScheduleStart)
            .Set("schedule_end", row.ScheduleEnd)
            .Set("max_concurrent_files", row.MaxConcurrentFiles)
            .Set("priority", row.Priority)
            .Set("rule_set_id", row.RuleSetId)
            .Set("manager_connection_ids", new PyList(managerIds.Select(id => (PyJson)PyJson.Of(id))))
            .Set("manager_coverage", coverage)
            .Set("manager_coverage_detail", coverageDetail)
            .Set("discovered_from_connection_id", row.DiscoveredFromConnectionId)
            .Set("discovered_library_key", row.DiscoveredLibraryKey)
            .Set("active_job_count", activeJobs)
            .Set("updated_at", row.UpdatedAt.PydanticJson());
    }

    private static PyDict RuleSetOut(RefinerRuleSetRecord row, int usedByLibraryCount) => new PyDict()
        .Set("id", row.Id)
        .Set("name", row.Name)
        .Set("primary_audio_lang", row.PrimaryAudioLang)
        .Set("secondary_audio_lang", row.SecondaryAudioLang)
        .Set("tertiary_audio_lang", row.TertiaryAudioLang)
        .Set("default_audio_slot", row.DefaultAudioSlot)
        .Set("remove_commentary", row.RemoveCommentary)
        .Set("subtitle_mode", row.SubtitleMode)
        .Set("subtitle_langs_csv", row.SubtitleLangsCsv)
        .Set("preserve_forced_subs", row.PreserveForcedSubs)
        .Set("preserve_default_subs", row.PreserveDefaultSubs)
        .Set("audio_preference_mode", row.AudioPreferenceMode)
        .Set("audio_sorters_json", row.AudioSortersJson)
        .Set("subtitle_sorters_json", row.SubtitleSortersJson)
        .Set("keep_original_language", row.KeepOriginalLanguage)
        .Set("original_language_additional_csv", row.OriginalLanguageAdditionalCsv)
        .Set("original_language_keep_only_first", row.OriginalLanguageKeepOnlyFirst)
        .Set("original_language_first_if_none", row.OriginalLanguageFirstIfNone)
        .Set("original_language_treat_empty_as_original", row.OriginalLanguageTreatEmptyAsOriginal)
        .Set("remove_images", row.RemoveImages)
        .Set("remove_attachments", row.RemoveAttachments)
        .Set("remove_title", row.RemoveTitle)
        .Set("remove_language_tags", row.RemoveLanguageTags)
        .Set("remove_other_metadata", row.RemoveOtherMetadata)
        .Set("used_by_library_count", usedByLibraryCount)
        .Set("updated_at", row.UpdatedAt.PydanticJson());

    private static async Task<ApiResult> GetLibrariesAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var rows = await LibraryStore.ListAsync(uow).ConfigureAwait(false);
        var items = new List<PyJson>();
        foreach (var row in rows)
        {
            items.Add(await LibraryOutAsync(uow, row).ConfigureAwait(false));
        }

        return ApiRoutes.Ok(new PyList(items));
    }

    private static async Task<ApiResult> GetLibraryAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("library_id", issues);
        issues.ThrowIfAny();
        var uow = await request.DbAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await LibraryOutAsync(uow, await RequireLibraryAsync(uow, id).ConfigureAwait(false)).ConfigureAwait(false));
    }

    private static RefinerLibraryInput ReadLibraryBody(BodyModel model)
    {
        var name = model.Str("name", minLength: 1, maxLength: 120);
        var mediaType = model.Literal("media_type", RefinerMediaScopes.All);
        var enabled = model.Bool("enabled", defaultValue: true);
        var watchedFolder = model.OptionalStr("watched_folder", defaultValue: "", maxLength: 4000) ?? "";
        var workFolder = model.OptionalStr("work_folder", defaultValue: "", maxLength: 4000) ?? "";
        var outputFolder = model.OptionalStr("output_folder", defaultValue: "", maxLength: 4000) ?? "";
        var mediaExtensionsCsv = model.OptionalStr("media_extensions_csv", defaultValue: "", maxLength: 1000) ?? "";
        var excludeMarkersCsv = model.OptionalStr("exclude_markers_csv", defaultValue: "", maxLength: 1000) ?? "";
        var includePatternsCsv = model.OptionalStr("include_patterns_csv", defaultValue: "", maxLength: 1000) ?? "";
        var excludePatternsCsv = model.OptionalStr("exclude_patterns_csv", defaultValue: "", maxLength: 1000) ?? "";
        var minFileSizeMb = model.Number("min_file_size_mb", 0, required: false, ge: 0, le: 1_000_000);
        var maxFileSizeMb = model.Number("max_file_size_mb", 0, required: false, ge: 0, le: 1_000_000);
        var rejectedFileAction = model.Literal("rejected_file_action", ["leave", "delete_file"], defaultValue: "leave");
        var minFileAgeSeconds = model.Number("min_file_age_seconds", 60, required: false, ge: 0, le: 604800);
        var createdAfter = model.OptionalDateTime("created_after");
        var createdBefore = model.OptionalDateTime("created_before");
        var modifiedAfter = model.OptionalDateTime("modified_after");
        var modifiedBefore = model.OptionalDateTime("modified_before");
        var excludeHidden = model.Bool("exclude_hidden", defaultValue: true);
        var topLevelOnly = model.Bool("top_level_only", defaultValue: false);
        var sidecarPatternsCsv = model.OptionalStr("sidecar_patterns_csv", defaultValue: ".srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png") ?? string.Empty;
        var preserveOriginalTimestamps = model.Bool("preserve_original_timestamps", defaultValue: false);
        var outputCollisionPolicy = model.Literal("output_collision_policy", ["replace", "skip", "keep_both", "replace_if_larger", "replace_if_newer"], defaultValue: "replace");
        var hardwareDecodeMode = model.Literal("hardware_decode_mode", ["off", "auto", "device"], defaultValue: "off");
        var hardwareDevice = model.OptionalStr("hardware_device", defaultValue: "", maxLength: 32) ?? string.Empty;
        var hardwareDisabledVendorsCsv = model.OptionalStr("hardware_disabled_vendors_csv", defaultValue: "", maxLength: 200) ?? string.Empty;
        var ffmpegStrictness = model.Literal("ffmpeg_strictness", ["very", "strict", "normal", "unofficial", "experimental"], defaultValue: "normal");
        var scanIntervalSeconds = model.Number("scan_interval_seconds", 300, required: false, ge: 10, le: 604800);
        var holdMinutes = model.Number("hold_minutes", 0, required: false, ge: 0, le: 10080);
        var fileDetectionIntervalSeconds = model.Number("file_detection_interval_seconds", 30, required: false, ge: 0, le: 3600);
        var ignoreSizeChanges = model.Bool("ignore_size_changes", defaultValue: false);
        var skipAccessTests = model.Bool("skip_access_tests", defaultValue: false);
        var maxAttempts = model.Number("max_attempts", 3, required: false, ge: 1, le: 20);
        var retryBackoffSeconds = model.Number("retry_backoff_seconds", 300, required: false, ge: 1, le: 3600);
        var retryExecutionFailures = model.Bool("retry_execution_failures", defaultValue: true);
        var failurePolicy = model.Literal("failure_policy", RefinerFailurePolicies.All, defaultValue: RefinerFailurePolicies.PassThrough);
        var retryPreflightFailures = model.Bool("retry_preflight_failures", defaultValue: false);
        var scheduleGrid = model.OptionalStr("schedule_grid", defaultValue: "") ?? string.Empty;
        var fileSystemEventsEnabled = model.Bool("file_system_events_enabled", defaultValue: true);
        var scheduleEnabled = model.Bool("schedule_enabled", defaultValue: true);
        var scheduleHoursLimited = model.Bool("schedule_hours_limited", defaultValue: false);
        var scheduleDays = model.OptionalStr("schedule_days", defaultValue: "", maxLength: 200) ?? string.Empty;
        var scheduleStart = model.OptionalStr("schedule_start", defaultValue: "00:00", maxLength: 5) ?? "00:00";
        var scheduleEnd = model.OptionalStr("schedule_end", defaultValue: "23:59", maxLength: 5) ?? "23:59";
        var maxConcurrentFiles = model.Number("max_concurrent_files", 1, required: false, ge: 1, le: 8);
        var priority = model.Number("priority", 0, required: false, ge: -100, le: 100);
        var ruleSetId = model.OptionalInt("rule_set_id");
        var managerConnectionIds = model.IntList("manager_connection_ids");

        return new RefinerLibraryInput
        {
            Name = name,
            MediaType = mediaType,
            Enabled = enabled,
            WatchedFolder = watchedFolder,
            WorkFolder = workFolder,
            OutputFolder = outputFolder,
            MediaExtensionsCsv = mediaExtensionsCsv,
            ExcludeMarkersCsv = excludeMarkersCsv,
            IncludePatternsCsv = includePatternsCsv,
            ExcludePatternsCsv = excludePatternsCsv,
            MinFileSizeMb = minFileSizeMb,
            MaxFileSizeMb = maxFileSizeMb,
            RejectedFileAction = rejectedFileAction,
            MinFileAgeSeconds = minFileAgeSeconds,
            CreatedAfter = createdAfter,
            CreatedBefore = createdBefore,
            ModifiedAfter = modifiedAfter,
            ModifiedBefore = modifiedBefore,
            ExcludeHidden = excludeHidden,
            TopLevelOnly = topLevelOnly,
            SidecarPatternsCsv = sidecarPatternsCsv,
            PreserveOriginalTimestamps = preserveOriginalTimestamps,
            OutputCollisionPolicy = outputCollisionPolicy,
            HardwareDecodeMode = hardwareDecodeMode,
            HardwareDevice = hardwareDevice,
            HardwareDisabledVendorsCsv = hardwareDisabledVendorsCsv,
            FfmpegStrictness = ffmpegStrictness,
            ScanIntervalSeconds = scanIntervalSeconds,
            HoldMinutes = holdMinutes,
            FileDetectionIntervalSeconds = fileDetectionIntervalSeconds,
            IgnoreSizeChanges = ignoreSizeChanges,
            SkipAccessTests = skipAccessTests,
            MaxAttempts = maxAttempts,
            RetryBackoffSeconds = retryBackoffSeconds,
            RetryExecutionFailures = retryExecutionFailures,
            FailurePolicy = failurePolicy,
            ScheduleGrid = scheduleGrid,
            RetryPreflightFailures = retryPreflightFailures,
            FileSystemEventsEnabled = fileSystemEventsEnabled,
            ScheduleEnabled = scheduleEnabled,
            ScheduleHoursLimited = scheduleHoursLimited,
            ScheduleDays = scheduleDays,
            ScheduleStart = scheduleStart,
            ScheduleEnd = scheduleEnd,
            MaxConcurrentFiles = maxConcurrentFiles,
            Priority = priority,
            RuleSetId = ruleSetId,
            ManagerConnectionIds = managerConnectionIds,
        };
    }

    /// <summary>
    /// <c>detection_window_requires_timezone</c> (a <c>field_validator</c>) and
    /// <c>detection_windows_are_ordered</c> (a <c>model_validator</c>), both surfaced as pydantic
    /// <c>value_error</c> issues so the 422 body matches FastAPI's shape rather than a flat detail string.
    /// </summary>
    private static void ValidateDetectionWindows(RefinerLibraryInput body, ValidationIssues issues)
    {
        void RequireTimezone(string field, PyDateTime? value)
        {
            if (value is { Offset: null })
            {
                issues.Add(new ValidationIssue("value_error", ["body", field], "Value error, Detection-window times must include a timezone.", PyJson.Null));
            }
        }

        RequireTimezone("created_after", body.CreatedAfter);
        RequireTimezone("created_before", body.CreatedBefore);
        RequireTimezone("modified_after", body.ModifiedAfter);
        RequireTimezone("modified_before", body.ModifiedBefore);
        if (issues.Any)
        {
            return;
        }

        if (body.CreatedAfter is { } ca && body.CreatedBefore is { } cb && ca.AsUtc >= cb.AsUtc)
        {
            issues.Add(new ValidationIssue("value_error", ["body"], "Value error, Created after must be earlier than created before.", PyJson.Null));
        }

        if (body.ModifiedAfter is { } ma && body.ModifiedBefore is { } mb && ma.AsUtc >= mb.AsUtc)
        {
            issues.Add(new ValidationIssue("value_error", ["body"], "Value error, Modified after must be earlier than modified before.", PyJson.Null));
        }
    }

    private static async Task<ApiResult> PostLibraryAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var body = ReadLibraryBody(model);
        model.Finish(ExtraFields.Forbid);
        if (!issues.Any)
        {
            ValidateDetectionWindows(body, issues);
        }

        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        RefinerLibraryRecord row;
        try
        {
            row = await LibraryStore.CreateAsync(uow, body).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return new JsonApiResult(StatusCodes.Status201Created, await LibraryOutAsync(uow, row).ConfigureAwait(false));
    }

    private static async Task<ApiResult> PutLibraryAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var pathIssues = new ValidationIssues();
        var id = request.PathInt("library_id", pathIssues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var body = ReadLibraryBody(model);
        model.Finish(ExtraFields.Forbid);
        pathIssues.ThrowIfAny();
        if (!issues.Any)
        {
            ValidateDetectionWindows(body, issues);
        }

        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var existing = await RequireLibraryAsync(uow, id).ConfigureAwait(false);
        RefinerLibraryRecord updated;
        try
        {
            updated = await LibraryStore.UpdateAsync(uow, existing, body).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await LibraryOutAsync(uow, updated).ConfigureAwait(false));
    }

    private static async Task<ApiResult> DeleteLibraryAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireLibraryAsync(uow, id).ConfigureAwait(false);
        try
        {
            await LibraryStore.DeleteAsync(uow, row).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status409Conflict, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return new CustomApiResult(context =>
        {
            PyResponses.NoContentJson(context);
            return Task.CompletedTask;
        });
    }

    private static async Task<ApiResult> PostReorderAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var orderedIds = model.IntList("library_ids_in_order");
        model.Finish(ExtraFields.Forbid);
        if (orderedIds.Count == 0)
        {
            issues.Add(new ValidationIssue("too_short", ["body", "library_ids_in_order"], "List should have at least 1 item after validation, not 0", new PyList()));
        }

        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        List<RefinerLibraryRecord> rows;
        try
        {
            rows = await LibraryStore.ReorderAsync(uow, orderedIds).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        var items = new List<PyJson>();
        foreach (var row in rows)
        {
            items.Add(await LibraryOutAsync(uow, row).ConfigureAwait(false));
        }

        return ApiRoutes.Ok(new PyList(items));
    }

    // ---- Rule sets --------------------------------------------------------------------------

    private static async Task<ApiResult> GetRuleSetsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var rows = await LibraryStore.ListRuleSetsAsync(uow).ConfigureAwait(false);
        var items = new List<PyJson>();
        foreach (var row in rows)
        {
            items.Add(RuleSetOut(row, await LibraryStore.RuleSetUsageCountAsync(uow, row.Id).ConfigureAwait(false)));
        }

        return ApiRoutes.Ok(new PyList(items));
    }

    private static LibraryRules.RuleSetInput ReadRuleSetBody(BodyModel model) => new()
    {
        Name = model.Str("name", minLength: 1, maxLength: 120),
        PrimaryAudioLang = model.OptionalStr("primary_audio_lang", defaultValue: "", maxLength: 24) ?? string.Empty,
        SecondaryAudioLang = model.OptionalStr("secondary_audio_lang", defaultValue: "", maxLength: 24) ?? string.Empty,
        TertiaryAudioLang = model.OptionalStr("tertiary_audio_lang", defaultValue: "", maxLength: 24) ?? string.Empty,
        DefaultAudioSlot = model.Literal("default_audio_slot", ["primary", "secondary", "tertiary"], defaultValue: "primary"),
        RemoveCommentary = model.Bool("remove_commentary", defaultValue: false),
        SubtitleMode = model.Literal("subtitle_mode", ["keep_all", "keep_listed", "remove_all"], defaultValue: "keep_all"),
        SubtitleLangsCsv = model.OptionalStr("subtitle_langs_csv", defaultValue: "", maxLength: 500) ?? string.Empty,
        PreserveForcedSubs = model.Bool("preserve_forced_subs", defaultValue: true),
        PreserveDefaultSubs = model.Bool("preserve_default_subs", defaultValue: true),
        AudioSortersJson = model.OptionalStr("audio_sorters_json", defaultValue: "") ?? string.Empty,
        SubtitleSortersJson = model.OptionalStr("subtitle_sorters_json", defaultValue: "") ?? string.Empty,
        KeepOriginalLanguage = model.Bool("keep_original_language", defaultValue: false),
        OriginalLanguageAdditionalCsv = model.OptionalStr("original_language_additional_csv", defaultValue: "", maxLength: 200) ?? string.Empty,
        OriginalLanguageKeepOnlyFirst = model.Bool("original_language_keep_only_first", defaultValue: true),
        OriginalLanguageFirstIfNone = model.Bool("original_language_first_if_none", defaultValue: true),
        OriginalLanguageTreatEmptyAsOriginal = model.Bool("original_language_treat_empty_as_original", defaultValue: false),
        RemoveImages = model.Bool("remove_images", defaultValue: false),
        RemoveAttachments = model.Bool("remove_attachments", defaultValue: false),
        RemoveTitle = model.Bool("remove_title", defaultValue: false),
        RemoveLanguageTags = model.Bool("remove_language_tags", defaultValue: false),
        RemoveOtherMetadata = model.Bool("remove_other_metadata", defaultValue: false),
        AudioPreferenceMode = model.Literal("audio_preference_mode", ["preferred_langs_quality", "preferred_langs_strict", "quality_all_languages"], defaultValue: "preferred_langs_quality"),
    };

    private static async Task<ApiResult> PostRuleSetAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var body = ReadRuleSetBody(model);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        RefinerRuleSetRecord row;
        try
        {
            row = await LibraryStore.CreateRuleSetAsync(uow, body).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return new JsonApiResult(StatusCodes.Status201Created, RuleSetOut(row, await LibraryStore.RuleSetUsageCountAsync(uow, row.Id).ConfigureAwait(false)));
    }

    private static async Task<ApiResult> PutRuleSetAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var pathIssues = new ValidationIssues();
        var id = request.PathInt("rule_set_id", pathIssues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var body = ReadRuleSetBody(model);
        model.Finish(ExtraFields.Forbid);
        pathIssues.ThrowIfAny();
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var existing = await RequireRuleSetAsync(uow, id).ConfigureAwait(false);
        RefinerRuleSetRecord updated;
        try
        {
            updated = await LibraryStore.UpdateRuleSetAsync(uow, existing, body).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(RuleSetOut(updated, await LibraryStore.RuleSetUsageCountAsync(uow, updated.Id).ConfigureAwait(false)));
    }

    private static async Task<ApiResult> DeleteRuleSetAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("rule_set_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireRuleSetAsync(uow, id).ConfigureAwait(false);
        try
        {
            await LibraryStore.DeleteRuleSetAsync(uow, row).ConfigureAwait(false);
        }
        catch (RefinerLibraryException exception)
        {
            throw new ApiException(StatusCodes.Status409Conflict, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return new CustomApiResult(context =>
        {
            PyResponses.NoContentJson(context);
            return Task.CompletedTask;
        });
    }
}
