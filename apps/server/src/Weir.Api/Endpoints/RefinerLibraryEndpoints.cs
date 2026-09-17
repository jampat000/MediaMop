using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Core.Time;
using Weir.Core.Validation;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Endpoints;

/// <summary>Refiner libraries and rule sets — <c>/api/v1/refiner/libraries</c>, <c>/refiner/rule-sets</c>
/// (port of <c>refiner_libraries_api.py</c>). Manager coverage now reads the linked connections' saved
/// test results (#520). The opt-in Reject failure policy's support gate (<c>GET /refiner/reject-support</c>,
/// and the same check on save) is ported (#522 part 4). Media-manager library discovery (discover/drift/
/// import) and library unlink are ported in #554, backed by <see cref="LibraryDiscoveryService"/>.</summary>
public static class RefinerLibraryEndpoints
{
    public static IEndpointRouteBuilder MapRefinerLibraryEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/libraries", GetLibrariesAsync);
        endpoints.MapV1("POST", "/refiner/libraries", PostLibraryAsync);
        endpoints.MapV1("GET", "/refiner/reject-support", GetRejectSupportAsync);
        endpoints.MapV1("GET", "/refiner/libraries/discover/{connection_id}", GetDiscoverableLibrariesAsync);
        endpoints.MapV1("POST", "/refiner/libraries/discover/{connection_id}/import", PostImportLibrariesAsync);
        endpoints.MapV1("GET", "/refiner/libraries/discover/{connection_id}/drift", GetLibraryDriftAsync);
        endpoints.MapV1("GET", "/refiner/libraries/{library_id}", GetLibraryAsync);
        endpoints.MapV1("PUT", "/refiner/libraries/{library_id}", PutLibraryAsync);
        endpoints.MapV1("DELETE", "/refiner/libraries/{library_id}", DeleteLibraryAsync);
        endpoints.MapV1("POST", "/refiner/libraries/{library_id}/unlink", PostLibraryUnlinkAsync);
        endpoints.MapV1("POST", "/refiner/libraries/reorder", PostReorderAsync);
        endpoints.MapV1("GET", "/refiner/rule-sets", GetRuleSetsAsync);
        endpoints.MapV1("POST", "/refiner/rule-sets", PostRuleSetAsync);
        endpoints.MapV1("PUT", "/refiner/rule-sets/{rule_set_id}", PutRuleSetAsync);
        endpoints.MapV1("DELETE", "/refiner/rule-sets/{rule_set_id}", DeleteRuleSetAsync);
        return endpoints;
    }

    private static async Task<RefinerLibraryRecord> RequireLibraryAsync(UnitOfWork uow, long id) =>
        await LibraryStore.GetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "That library does not exist.");

    /// <summary><c>_require_connection</c>: <c>int = Path(ge=1)</c>.</summary>
    private static long ConnectionId(ApiRequest request, ValidationIssues issues)
    {
        var raw = request.RouteValue("connection_id") ?? string.Empty;
        return PydanticRules.TryInt(new PyStr(raw), ["path", "connection_id"], 1, null, issues, out var value)
            ? value > long.MaxValue ? long.MaxValue : (long)value
            : 0;
    }

    private static async Task<MediaManagerConnectionRecord> RequireConnectionAsync(UnitOfWork uow, long connectionId) =>
        await MediaManagerConnectionStore.GetAsync(uow, connectionId).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "That media manager connection does not exist.");

    private static async Task<RefinerRuleSetRecord> RequireRuleSetAsync(UnitOfWork uow, long id) =>
        await LibraryStore.GetRuleSetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "That rule set does not exist.");

    private static async Task<PyDict> LibraryOutAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        var managerIds = await LibraryStore.ManagerConnectionIdsAsync(uow, row.Id).ConfigureAwait(false);
        var activeJobs = await LibraryStore.ActiveJobCountAsync(uow, row).ConfigureAwait(false);

        // Port of _library_out's manager_coverage: the linked connections' last saved connection-test
        // result (no live call — a listing must not depend on every linked manager answering right now).
        var managerRows = new List<MediaManagerConnectionRecord?>(managerIds.Count);
        foreach (var connectionId in managerIds)
        {
            managerRows.Add(await MediaManagerConnectionStore.GetAsync(uow, connectionId).ConfigureAwait(false));
        }

        string coverage;
        string coverageDetail;
        if (managerRows.Count == 0)
        {
            coverage = "no_upstream_signal";
            coverageDetail = "No media manager is linked. Watched-folder remux can still run after local safety gates, " +
                              "but upstream import protection is reduced.";
        }
        else if (managerRows.Any(item => item is null || !item.Enabled || item.LastTestOk == false))
        {
            coverage = "unreachable";
            coverageDetail = "A linked media manager did not answer its last connection test. Remux remains local, " +
                              "but manager-truth-dependent cleanup is held until the connection is available.";
        }
        else if (managerRows.Any(item => item!.LastTestOk != true))
        {
            coverage = "no_upstream_signal";
            coverageDetail = "A manager is linked but has not returned a successful connection signal yet. " +
                              "This is not the same as an empty queue.";
        }
        else
        {
            coverage = "connected";
            coverageDetail = "The linked manager connection is healthy. Upstream checks and manager-truth-dependent " +
                              "cleanup can use its latest answer.";
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
        .Set("remove_hearing_impaired_subs", row.RemoveHearingImpairedSubs)
        .Set("audio_keep_mode", row.AudioKeepMode)
        .Set("subtitle_max_per_language", row.SubtitleMaxPerLanguage)
        .Set("subtitle_quality_strategy", row.SubtitleQualityStrategy)
        .Set("standardize_track_names", row.StandardizeTrackNames)
        .Set("track_name_template", row.TrackNameTemplate)
        .Set("track_name_overrides", new PyDict()
            .Set("forced", row.TrackNameOverrides.Forced)
            .Set("hearing_impaired", row.TrackNameOverrides.HearingImpaired)
            .Set("commentary", row.TrackNameOverrides.Commentary)
            .Set("audio_description", row.TrackNameOverrides.AudioDescription))
        .Set("clear_video_track_names", row.ClearVideoTrackNames)
        .Set("remove_chapters", row.RemoveChapters)
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

    /// <summary>
    /// <c>GET /api/v1/refiner/reject-support</c>: whether the opt-in Reject failure policy can be chosen for a library
    /// linked to the given connections. Asks each manager's manifest (or its static capabilities, for one whose port
    /// removes queue items), so it is called when the option is shown, not on every list.
    /// </summary>
    private static async Task<ApiResult> GetRejectSupportAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var connectionIds = new List<long>();
        foreach (var raw in request.Context.Request.Query["connection_ids"])
        {
            if (raw is not null && long.TryParse(raw, out var id))
            {
                connectionIds.Add(id);
            }
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var connections = await request.Service<MediaManagerConnectionService>().ConnectionsByIdAsync(uow, connectionIds).ConfigureAwait(false);
        var support = await request.Service<RejectSupportEvaluator>().EvaluateAsync(connections).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("available", support.Available).Set("reason", support.Reason));
    }

    /// <summary>
    /// <c>_refuse_unsupported_reject</c>: <c>reject</c> deletes downloads, so it cannot be saved for a library no manager
    /// can take one for. Called after the row is written (so the manager links it was just given are the ones checked)
    /// but before the transaction commits.
    /// </summary>
    private static async Task RefuseUnsupportedRejectAsync(ApiRequest request, UnitOfWork uow, RefinerLibraryRecord row)
    {
        if (RefinerFailurePolicies.Normalize(row.FailurePolicy) != RefinerFailurePolicies.Reject)
        {
            return;
        }

        var connectionIds = await LibraryStore.ManagerConnectionIdsAsync(uow, row.Id).ConfigureAwait(false);
        var connections = await request.Service<MediaManagerConnectionService>().ConnectionsByIdAsync(uow, connectionIds).ConfigureAwait(false);
        var support = await request.Service<RejectSupportEvaluator>().EvaluateAsync(connections).ConfigureAwait(false);
        if (!support.Available)
        {
            await uow.RollbackAsync().ConfigureAwait(false);
            throw new ApiException(StatusCodes.Status400BadRequest, $"This library cannot use Reject yet. {support.Reason}");
        }
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

        await RefuseUnsupportedRejectAsync(request, uow, row).ConfigureAwait(false);
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

        await RefuseUnsupportedRejectAsync(request, uow, updated).ConfigureAwait(false);
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

        // #505: a deleted library takes its library-mode settings and scan history with it (both live on
        // refiner_jobs rows, not a foreign-keyed table — see apps/server/README.md, "Library mode").
        await Weir.Infrastructure.LibraryMode.LibrarySettingsStore.DeleteAllForLibraryAsync(uow, row.Id).ConfigureAwait(false);

        await request.CommitAsync().ConfigureAwait(false);
        return new CustomApiResult(context =>
        {
            PyResponses.NoContentJson(context);
            return Task.CompletedTask;
        });
    }

    // ---- Media-manager library discovery (#554) ----------------------------------------------

    private static PyDict DiscoverableLibraryOut(DiscoverableLibrary item) => new PyDict()
        .Set("key", item.Key)
        .Set("name", item.Name)
        .Set("media_type", item.MediaType)
        .Set("root_path", item.RootPath)
        .Set("already_imported", item.AlreadyImported)
        .Set("local_path_problem", item.LocalPathProblem)
        .Set("output_path", item.OutputPath)
        .Set("processes_before_import", item.ProcessesBeforeImport)
        .Set("output_path_problem", item.OutputPathProblem);

    private static PyDict LibraryDriftOut(LibraryDrift item) => new PyDict()
        .Set("kind", item.Kind)
        .Set("library_id", item.LibraryId)
        .Set("library_name", item.LibraryName)
        .Set("manager_value", item.ManagerValue)
        .Set("weir_value", item.WeirValue)
        .Set("detail", item.Detail);

    /// <summary><c>GET /refiner/libraries/discover/{connection_id}</c>: what this manager says it looks
    /// after, and whether Weir already has it.</summary>
    private static async Task<ApiResult> GetDiscoverableLibrariesAsync(ApiRequest request)
    {
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var connection = await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        List<DiscoverableLibrary> found;
        try
        {
            found = await request.Service<LibraryDiscoveryService>()
                .DiscoverableLibrariesAsync(uow, connection, request.Context.RequestAborted).ConfigureAwait(false);
        }
        catch (RefinerDiscoveryException exception)
        {
            throw new ApiException(StatusCodes.Status502BadGateway, exception.Message);
        }

        return ApiRoutes.Ok(new PyList(found.Select(item => (PyJson)DiscoverableLibraryOut(item))));
    }

    /// <summary><c>POST /refiner/libraries/discover/{connection_id}/import</c>: create a Refiner library per
    /// selected manager library.</summary>
    private static async Task<ApiResult> PostImportLibrariesAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var keys = model.StrList("keys", []);
        model.Finish(ExtraFields.Forbid);
        if (keys.Count == 0)
        {
            issues.Add(new ValidationIssue("too_short", ["body", "keys"], "List should have at least 1 item after validation, not 0", new PyList()));
        }

        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        // Python's <c>_verify_csrf</c> (shared by every route in this file) refuses with this exact wording.
        request.RequireConfirmationToken(csrfToken, "Invalid or expired CSRF token.");

        var uow = await request.DbAsync().ConfigureAwait(false);
        var connection = await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        List<RefinerLibraryRecord> created;
        try
        {
            created = await request.Service<LibraryDiscoveryService>()
                .ImportLibrariesAsync(uow, connection, keys, request.Context.RequestAborted).ConfigureAwait(false);
        }
        catch (RefinerDiscoveryException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        var items = new List<PyJson>();
        foreach (var row in created)
        {
            items.Add(await LibraryOutAsync(uow, row).ConfigureAwait(false));
        }

        return new JsonApiResult(StatusCodes.Status201Created, new PyList(items));
    }

    /// <summary><c>GET /refiner/libraries/discover/{connection_id}/drift</c>: differences between the manager
    /// and Weir. Reported only — nothing is applied.</summary>
    private static async Task<ApiResult> GetLibraryDriftAsync(ApiRequest request)
    {
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var connection = await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        List<LibraryDrift> drift;
        try
        {
            drift = await request.Service<LibraryDiscoveryService>()
                .ResyncDriftAsync(uow, connection, request.Context.RequestAborted).ConfigureAwait(false);
        }
        catch (RefinerDiscoveryException exception)
        {
            throw new ApiException(StatusCodes.Status502BadGateway, exception.Message);
        }

        return ApiRoutes.Ok(new PyList(drift.Select(item => (PyJson)LibraryDriftOut(item))));
    }

    /// <summary><c>POST /refiner/libraries/{library_id}/unlink</c>: forget where a library came from. The
    /// library itself is untouched.</summary>
    private static async Task<ApiResult> PostLibraryUnlinkAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        // Python's <c>_verify_csrf</c> (shared by every route in this file) refuses with this exact wording.
        request.RequireConfirmationToken(csrfToken, "Invalid or expired CSRF token.");

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireLibraryAsync(uow, id).ConfigureAwait(false);
        var updated = await LibraryDiscoveryService.UnlinkLibraryAsync(uow, row).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await LibraryOutAsync(uow, updated).ConfigureAwait(false));
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

    /// <summary>Shared with <see cref="RefinerRulesPreviewEndpoints"/>, which validates an unsaved rules
    /// payload the same way a save does, without touching the database. <paramref name="issues"/> must be
    /// the same collector <paramref name="model"/> itself reports to, so a bad nested
    /// <c>track_name_overrides</c> field surfaces as one of this request's own validation errors.</summary>
    internal static LibraryRules.RuleSetInput ReadRuleSetBody(BodyModel model, ValidationIssues issues)
    {
        var overridesDict = model.OptionalDict("track_name_overrides");
        var overrides = new TrackNameOverrides();
        if (overridesDict is not null)
        {
            var overridesModel = new BodyModel(overridesDict, issues);
            overrides = new TrackNameOverrides
            {
                Forced = overridesModel.OptionalStr("forced", defaultValue: overrides.Forced, maxLength: 200) ?? overrides.Forced,
                HearingImpaired = overridesModel.OptionalStr("hearing_impaired", defaultValue: overrides.HearingImpaired, maxLength: 200) ?? overrides.HearingImpaired,
                Commentary = overridesModel.OptionalStr("commentary", defaultValue: overrides.Commentary, maxLength: 200) ?? overrides.Commentary,
                AudioDescription = overridesModel.OptionalStr("audio_description", defaultValue: overrides.AudioDescription, maxLength: 200) ?? overrides.AudioDescription,
            };
            overridesModel.Finish(ExtraFields.Forbid);
        }

        return new LibraryRules.RuleSetInput
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

            // #495
            RemoveHearingImpairedSubs = model.Bool("remove_hearing_impaired_subs", defaultValue: false),

            // #497
            AudioKeepMode = model.Literal("audio_keep_mode", [RemuxRuleValues.AudioKeepModeSingle, RemuxRuleValues.AudioKeepModePerLanguage], defaultValue: RemuxRuleValues.AudioKeepModeSingle),
            SubtitleMaxPerLanguage = (int)model.Number("subtitle_max_per_language", defaultValue: 0, required: false, ge: 0),
            SubtitleQualityStrategy = model.Literal(
                "subtitle_quality_strategy",
                [RemuxRuleValues.SubtitleStrategyTextFirst, RemuxRuleValues.SubtitleStrategyImageFirst, RemuxRuleValues.SubtitleStrategyAccessibility],
                defaultValue: RemuxRuleValues.SubtitleStrategyTextFirst),

            // #498
            StandardizeTrackNames = model.Bool("standardize_track_names", defaultValue: false),
            TrackNameTemplate = model.OptionalStr("track_name_template", defaultValue: TrackNaming.DefaultTemplate, maxLength: 200) ?? TrackNaming.DefaultTemplate,
            TrackNameOverrides = overrides,
            ClearVideoTrackNames = model.Bool("clear_video_track_names", defaultValue: false),
            RemoveChapters = model.Bool("remove_chapters", defaultValue: false),
        };
    }

    private static async Task<ApiResult> PostRuleSetAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var body = ReadRuleSetBody(model, issues);
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
        var body = ReadRuleSetBody(model, issues);
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

        // #505 point 6: saving rules on a library with library folders runs a background re-plan (a normal scan, trigger
        // "rule_change"); the web shows "Apply to library? N files would change" once it finishes. Nothing runs on its own.
        var rescanJobIds = new List<long>();
        var jobStore = request.Service<Weir.Infrastructure.Jobs.RefinerJobStore>();
        foreach (var library in await LibraryStore.ListAsync(uow).ConfigureAwait(false))
        {
            if (library.RuleSetId != updated.Id)
            {
                continue;
            }

            var librarySettings = await Weir.Infrastructure.LibraryMode.LibrarySettingsStore.GetAsync(uow, library.Id).ConfigureAwait(false);
            if (librarySettings.Folders.Count == 0)
            {
                continue;
            }

            var job = await Weir.Infrastructure.LibraryMode.LibraryScanStore.RequestScanAsync(uow, jobStore, library.Id, "rule_change").ConfigureAwait(false);
            rescanJobIds.Add(job.Id);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(RuleSetOut(updated, await LibraryStore.RuleSetUsageCountAsync(uow, updated.Id).ConfigureAwait(false))
            .Set("library_rescan_job_ids", new PyList(rescanJobIds.Select(id => (PyJson)new PyInt(id)))));
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
