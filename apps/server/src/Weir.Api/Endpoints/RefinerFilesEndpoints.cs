using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Activity;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Core.Time;
using Weir.Core.Validation;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Refiner.DirectPlay;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Api.Endpoints;

/// <summary>
/// The Files screen — <c>/api/v1/refiner/files</c> (port of <c>refiner_files_api.py</c>).
/// Implements the fix for #530: <c>passed_through</c> and <c>rejected</c> are valid statuses in both the
/// response and the <c>file_status</c> filter — the previous status vocabulary omitted them, which 500'd a
/// response containing either status and 422'd a filter naming one.
/// </summary>
public static class RefinerFilesEndpoints
{
    public static IEndpointRouteBuilder MapRefinerFilesEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/files", GetFilesAsync);
        endpoints.MapV1("DELETE", "/refiner/files/{file_id}", DeleteFileAsync);
        endpoints.MapV1("POST", "/refiner/files/{file_id}/move-to-top", MoveToTopAsync);
        endpoints.MapV1("POST", "/refiner/files/{file_id}/requeue", RequeueOneAsync);
        endpoints.MapV1("POST", "/refiner/files/requeue", RequeueManyAsync);
        endpoints.MapV1("GET", "/refiner/files/{file_id}/log", GetFileLogAsync);
        endpoints.MapV1("GET", "/refiner/files/{file_id}/log/download", DownloadFileLogAsync);
        endpoints.MapV1("GET", "/refiner/files/{file_id}/tracks", GetFileTracksAsync);
        endpoints.MapV1("POST", "/refiner/files/{file_id}/manual-plan", PostManualPlanAsync);
        return endpoints;
    }

    private static PyDict FileOut(RefinerFileRecord row, string libraryName, List<DirectPlayBadge> directPlay, LiveProgress? progress)
    {
        var quarantined = row.Status == RefinerFileStatuses.OnHold && row.FailureAttempts >= 3;
        return new PyDict()
            .Set("id", row.Id)
            .Set("library_id", row.LibraryId)
            .Set("library_name", libraryName)
            .Set("relative_path", row.RelativePath)
            .Set("status", row.Status)
            .Set("status_reason", row.StatusReason)
            .Set("blocked_by_connection", row.BlockedByConnection)
            .Set("size_bytes", row.SizeBytes)
            .Set("video_codec", row.VideoCodec)
            .Set("video_width", row.VideoWidth)
            .Set("video_height", row.VideoHeight)
            .Set("audio_track_count", row.AudioTrackCount)
            .Set("subtitle_track_count", row.SubtitleTrackCount)
            .Set("duration_seconds", row.DurationSeconds is { } d ? PyJson.Of(d) : PyJson.Null)
            .Set("direct_play", new PyList(directPlay.Select(v => (PyJson)new PyDict()
                .Set("device_id", v.DeviceId)
                .Set("device_name", v.DeviceName)
                .Set("verdict", v.Verdict)
                .Set("reasons", new PyList(v.Reasons.Select(r => (PyJson)PyJson.Of(r)))))))
            .Set("progress_percent", progress?.Percent is { } pct ? PyJson.Of(pct) : PyJson.Null)
            .Set("progress_message", progress?.Message)
            .Set("progress_eta_seconds", progress?.EtaSeconds is { } eta ? PyJson.Of(eta) : PyJson.Null)
            .Set("failure_class", row.FailureClass)
            .Set("failure_attempts", row.FailureAttempts)
            .Set("quarantined", quarantined)
            .Set("next_retry_at", row.NextRetryAt?.PydanticJson())
            .Set("output_collision_policy", row.OutputCollisionPolicy)
            .Set("output_collision_action", row.OutputCollisionAction)
            .Set("output_collision_reason", row.OutputCollisionReason)
            .Set("hold_until", row.HoldUntil?.PydanticJson())
            .Set("size_changed_at", row.SizeChangedAt?.PydanticJson())
            .Set("created_at", row.CreatedAt.PydanticJson())
            .Set("updated_at", row.UpdatedAt.PydanticJson())
            .Set("last_seen_at", row.LastSeenAt?.PydanticJson())
            .Set("last_attempt_at", row.LastAttemptAt?.PydanticJson());
    }

    private static async Task<ApiResult> GetFilesAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        long? libraryId = request.Query("library_id") is { } rawLibrary && PydanticRules.TryInt(new PyStr(rawLibrary), ["query", "library_id"], 1, null, issues, out var parsedLibrary)
            ? (long)parsedLibrary
            : null;
        string? fileStatus = null;
        if (request.Query("file_status") is { } rawStatus)
        {
            if (PydanticRules.TryLiteral(new PyStr(rawStatus), ["query", "file_status"], RefinerFileStatuses.All, issues, out var parsedStatus))
            {
                fileStatus = parsedStatus;
            }
        }

        var pathContains = request.Query("path_contains");
        long? withinDays = request.Query("within_days") is { } rawWithin && PydanticRules.TryInt(new PyStr(rawWithin), ["query", "within_days"], 1, 3650, issues, out var parsedWithin)
            ? (long)parsedWithin
            : null;
        var limit = request.Query("limit") is { } rawLimit && PydanticRules.TryInt(new PyStr(rawLimit), ["query", "limit"], 1, 1000, issues, out var parsedLimit) ? (int)parsedLimit : 200;
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var filter = new RefinerFileListFilter
        {
            LibraryId = libraryId,
            Status = fileStatus,
            PathContains = pathContains,
            Since = withinDays is { } days ? PyDateTime.FromUtc(request.Time.GetUtcNow().AddDays(-days).UtcDateTime) : null,
            Limit = limit,
        };
        var rows = await FileStateStore.ListAsync(uow, filter).ConfigureAwait(false);
        var libraryNames = await FileStateStore.LibraryNamesAsync(uow).ConfigureAwait(false);
        var knownDevices = DeviceProfileLoader.Load(request.Options.WeirHome);
        var devices = await DirectPlayService.SelectedProfilesAsync(uow, knownDevices).ConfigureAwait(false);
        var progressByPath = await LiveProgressStore.ByPathAsync(uow, request.Time).ConfigureAwait(false);

        var files = new List<PyJson>();
        foreach (var row in rows)
        {
            var libraryName = libraryNames.GetValueOrDefault(row.LibraryId, "Unknown library");
            var directPlay = DirectPlayService.ForRow(row, devices);
            progressByPath.TryGetValue(row.RelativePath, out var progress);
            files.Add(FileOut(row, libraryName, directPlay, progress));
        }

        var counts = await FileStateStore.StatusCountsAsync(uow, libraryId).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("files", new PyList(files))
            .Set("status_counts", new PyDict().Also(dict =>
            {
                foreach (var (status, count) in counts)
                {
                    dict.Set(status, count);
                }
            }))
            .Set("returned", files.Count)
            .Set("limit", limit));
    }

    private static async Task<RefinerFileRecord> RequireFileAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, long id) =>
        await FileStateStore.GetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "Weir has no record of that file.");

    private static async Task<ApiResult> DeleteFileAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireFileAsync(uow, id).ConfigureAwait(false);
        await FileStateStore.ForgetAsync(uow, id).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return new CustomApiResult(context =>
        {
            PyResponses.NoContentJson(context);
            return Task.CompletedTask;
        });
    }

    private static async Task<ApiResult> MoveToTopAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireFileAsync(uow, id).ConfigureAwait(false);
        var job = await FindPendingRemuxJobAsync(uow, row.RelativePath).ConfigureAwait(false);
        if (job is null)
        {
            await request.CommitAsync().ConfigureAwait(false);
            return ApiRoutes.Ok(new PyDict()
                .Set("moved", false)
                .Set("detail", "There is no queued work for this file to move. It may already be running, or it may not have been picked up by a scan yet."));
        }

        var jobStore = request.Service<RefinerJobStore>();
        var outcome = await jobStore.MoveToTopAsync(job.Value.Id).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        if (outcome != Weir.Core.Jobs.JobActionOutcome.Ok)
        {
            return ApiRoutes.Ok(new PyDict().Set("moved", false).Set("detail", "This file's work has already started, so it cannot be moved ahead of anything."));
        }

        return ApiRoutes.Ok(new PyDict().Set("moved", true).Set("detail", "Moved to the front of the queue. It starts as soon as there is capacity for it."));
    }

    /// <summary><c>pending_remux_job_for_relative_path</c>: the oldest pending remux job for this path.</summary>
    private static async Task<(long Id, string PayloadJson)?> FindPendingRemuxJobAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, string relativePath)
    {
        var rows = await uow.QueryAsync(
            "SELECT id, payload_json FROM refiner_jobs WHERE job_kind = @kind AND status = 'pending' ORDER BY id",
            reader => (Id: reader.GetInt64(0), Payload: reader.IsDBNull(1) ? null : reader.GetString(1)),
            ("@kind", RequeueStore.RemuxPassJobKind)).ConfigureAwait(false);
        foreach (var (id, payloadJson) in rows)
        {
            if (string.IsNullOrWhiteSpace(payloadJson))
            {
                continue;
            }

            PyJson parsed;
            try
            {
                parsed = PyJsonParser.Parse(payloadJson);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (parsed is PyDict dict && dict.TryGetValue("relative_media_path", out var value) && value is PyStr s && s.Value == relativePath)
            {
                return (id, payloadJson);
            }
        }

        return null;
    }

    private static async Task<ApiResult> RequeueOneAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireFileAsync(uow, id).ConfigureAwait(false);
        var result = await new RequeueStore(request.Service<RefinerJobStore>()).RequeueFileAsync(uow, row).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("requeued", result.Requeued).Set("skipped", result.Skipped).Set("detail", result.Detail));
    }

    private static async Task<ApiResult> RequeueManyAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var libraryId = model.OptionalInt("library_id", ge: 1);
        string? fileStatus = null;
        var rawStatus = model.OptionalStr("file_status");
        if (rawStatus is not null && PydanticRules.TryLiteral(PyJson.Of(rawStatus), ["body", "file_status"], RefinerFileStatuses.All, issues, out var parsedStatus))
        {
            fileStatus = parsedStatus;
        }

        var pathContains = model.OptionalStr("path_contains", maxLength: 500);
        var limit = model.Number("limit", 200, required: false, ge: 1, le: 1000);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var rows = await FileStateStore.ListAsync(uow, new RefinerFileListFilter
        {
            LibraryId = libraryId,
            Status = fileStatus,
            PathContains = pathContains,
            Limit = (int)limit,
        }).ConfigureAwait(false);
        var result = await new RequeueStore(request.Service<RefinerJobStore>()).RequeueFilesAsync(uow, rows).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("requeued", result.Requeued).Set("skipped", result.Skipped).Set("detail", result.Detail));
    }

    private static async Task<ApiResult> GetFileLogAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        var limit = request.Query("limit") is { } rawLimit && PydanticRules.TryInt(new PyStr(rawLimit), ["query", "limit"], 1, 500, issues, out var parsedLimit) ? (int)parsedLimit : 50;
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireFileAsync(uow, id).ConfigureAwait(false);
        var operatorRow = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var rows = await FileLogStore.LogsForFileAsync(uow, row.RelativePath, limit).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);

        var entries = new List<PyJson>();
        foreach (var entry in rows)
        {
            var detail = FileLogStore.ParseDetail(entry.DetailJson);
            var story = FileStory.NarratePass(detail, entry.LibraryName);
            entries.Add(new PyDict()
                .Set("id", entry.Id)
                .Set("recorded_at", entry.RecordedAt.PydanticJson())
                .Set("outcome", entry.Outcome)
                .Set("title", entry.Title)
                .Set("library_name", entry.LibraryName)
                .Set("detail", detail)
                .Set("story", new PyList(story.Select(step => (PyJson)new PyDict()
                    .Set("heading", step.Heading)
                    .Set("sentence", step.Sentence)
                    .Set("tone", step.Tone.ToString().ToLowerInvariant())))));
        }

        return ApiRoutes.Ok(new PyDict()
            .Set("file_id", id)
            .Set("relative_path", row.RelativePath)
            .Set("retention_days", operatorRow.FileLogRetentionDays)
            .Set("entries", new PyList(entries)));
    }

    private static async Task<ApiResult> DownloadFileLogAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireFileAsync(uow, id).ConfigureAwait(false);
        var rows = await FileLogStore.LogsForFileAsync(uow, row.RelativePath, 500).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);

        var safe = new string([.. row.RelativePath.Where(ch => char.IsLetterOrDigit(ch) || ch is '-' or '_' or '.')]);
        safe = safe.Length > 80 ? safe[^80..] : safe;
        safe = safe.Trim('-');
        if (safe.Length == 0)
        {
            safe = "file";
        }

        var text = FileLogStore.RenderLogText(rows);
        return new CustomApiResult(context =>
        {
            context.Response.Headers.ContentDisposition = $"attachment; filename=\"weir-{safe}.log.txt\"";
            return PyResponses.WritePlainTextAsync(context, StatusCodes.Status200OK, text);
        });
    }

    // ---- Choose tracks by hand (issue #501) -------------------------------------------------

    private static PyDict StreamOut(int index, string kind, ProbeStreamInfo stream, TrackDecision? decision)
    {
        var tags = stream.Tags;
        var disposition = stream.Disposition;
        long? channels = null;
        if (kind == "audio" && stream.Get("channels") is { } raw && raw.ValueKind == JsonValueKind.Number && raw.TryGetInt64(out var n))
        {
            channels = n;
        }

        return new PyDict()
            .Set("index", index)
            .Set("type", kind)
            .Set("codec", stream.CodecName.Length > 0 ? stream.CodecName : null)
            .Set("language", tags.GetValueOrDefault("language"))
            .Set("title", tags.GetValueOrDefault("title"))
            .Set("channels", channels)
            .Set("default", disposition.GetValueOrDefault("default") != 0)
            .Set("forced", disposition.GetValueOrDefault("forced") != 0)
            .Set("rule_would_keep", decision?.WouldKeep ?? false)
            .Set("rule_reason", decision?.Reason ?? "This pass does not act on this stream type.");
    }

    private static async Task<ApiResult> GetFileTracksAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        ManualPlanFileContext context;
        try
        {
            context = await ManualPlanSupport.LoadAsync(uow, request.Service<MediaTools>(), request.Options, id, request.Context.RequestAborted)
                .ConfigureAwait(false);
        }
        catch (ManualPlanEnqueueException exception)
        {
            throw new ApiException(exception.StatusCode, exception.Message);
        }

        SourceFingerprint fingerprint;
        try
        {
            fingerprint = SourceFiles.Fingerprint(context.SourcePath);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, $"Weir could not read this file safely: {exception.Message}");
        }

        await request.CommitAsync().ConfigureAwait(false);

        var (video, audio, subtitles) = RemuxRules.SplitStreams(context.Probe);
        var attachments = RemuxRules.AttachmentStreams(context.Probe);
        var decisionsByKey = RemuxRules.ExplainTracks(video, audio, subtitles, context.Rules, attachments)
            .ToDictionary(d => (d.InputIndex, d.Kind));

        TrackDecision? DecisionFor(int index, params string[] kinds)
        {
            foreach (var kind in kinds)
            {
                if (decisionsByKey.TryGetValue((index, kind), out var found))
                {
                    return found;
                }
            }

            return null;
        }

        var rows = new List<(int Index, PyDict Row)>();
        var covered = new HashSet<int>();
        foreach (var stream in video)
        {
            if (stream.Index is not { } idx)
            {
                continue;
            }

            var decision = DecisionFor((int)idx, "video", "image");
            rows.Add(((int)idx, StreamOut((int)idx, decision?.Kind ?? "video", stream, decision)));
            covered.Add((int)idx);
        }

        foreach (var stream in audio)
        {
            if (stream.Index is not { } idx)
            {
                continue;
            }

            rows.Add(((int)idx, StreamOut((int)idx, "audio", stream, DecisionFor((int)idx, "audio"))));
            covered.Add((int)idx);
        }

        foreach (var stream in subtitles)
        {
            if (stream.Index is not { } idx)
            {
                continue;
            }

            rows.Add(((int)idx, StreamOut((int)idx, "subtitle", stream, DecisionFor((int)idx, "subtitle"))));
            covered.Add((int)idx);
        }

        foreach (var stream in attachments)
        {
            if (stream.Index is not { } idx)
            {
                continue;
            }

            rows.Add(((int)idx, StreamOut((int)idx, "attachment", stream, DecisionFor((int)idx, "attachment"))));
            covered.Add((int)idx);
        }

        foreach (var stream in context.Probe.Streams)
        {
            if (stream.Index is not { } idx || covered.Contains((int)idx))
            {
                continue;
            }

            rows.Add(((int)idx, StreamOut((int)idx, stream.CodecType.Length > 0 ? stream.CodecType : "other", stream, null)));
        }

        rows.Sort((a, b) => a.Index.CompareTo(b.Index));
        return ApiRoutes.Ok(new PyDict()
            .Set("file_id", context.File.Id)
            .Set("relative_path", context.File.RelativePath)
            .Set("media_scope", context.Library.MediaType)
            .Set("source_fingerprint", ManualPlanJson.ToPyDict(fingerprint))
            .Set("streams", new PyList(rows.Select(r => (PyJson)r.Row))));
    }

    private static async Task<ApiResult> PostManualPlanAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Ignore);
        issues.ThrowIfAny();

        if (payload is not PyDict body || body.Get("keep") is not PyList keepList)
        {
            throw new ApiException(StatusCodes.Status422UnprocessableEntity, "'keep' is required and must be a list of {index, default, forced}.");
        }

        var keep = new List<ManualKeepEntry>();
        foreach (var item in keepList.Items)
        {
            if (item is not PyDict entry || entry.Get("index") is not PyInt indexValue)
            {
                throw new ApiException(StatusCodes.Status422UnprocessableEntity, "Each item in 'keep' must be an object with an integer 'index'.");
            }

            var isDefault = entry.Get("default") is PyBool { Value: true };
            var forced = entry.Get("forced") is PyBool { Value: true };
            keep.Add(new ManualKeepEntry((int)indexValue.Value, isDefault, forced));
        }

        if (body.Get("order") is not PyList orderList)
        {
            throw new ApiException(StatusCodes.Status422UnprocessableEntity, "'order' is required and must be a list of integers.");
        }

        var order = new List<int>();
        foreach (var item in orderList.Items)
        {
            if (item is not PyInt orderIndex)
            {
                throw new ApiException(StatusCodes.Status422UnprocessableEntity, "'order' must be a list of integers.");
            }

            order.Add((int)orderIndex.Value);
        }

        var choice = new ManualPlanChoice(keep, order);

        var session = await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken, "Invalid or expired CSRF token.");

        var uow = await request.DbAsync().ConfigureAwait(false);
        ManualPlanFileContext context;
        try
        {
            context = await ManualPlanSupport.LoadAsync(uow, request.Service<MediaTools>(), request.Options, id, request.Context.RequestAborted)
                .ConfigureAwait(false);
        }
        catch (ManualPlanEnqueueException exception)
        {
            throw new ApiException(exception.StatusCode, exception.Message);
        }

        if (context.File.Status != RefinerFileStatuses.OnHold)
        {
            throw new ApiException(
                StatusCodes.Status400BadRequest,
                "This file is not on hold, so a manual track choice does not apply. Refresh the Files list and try again.");
        }

        var streams = RemuxRules.SplitStreams(context.Probe);
        var kinds = ManualTrackPlan.ClassifyIndices(streams);
        if (!ManualTrackPlan.TryValidate(choice, kinds, out var problem))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, problem);
        }

        SourceFingerprint fingerprint;
        try
        {
            fingerprint = SourceFiles.Fingerprint(context.SourcePath);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, $"Weir could not read this file safely: {exception.Message}");
        }

        var job = ManualPlanSupport.EnqueueManualPlan(uow, request.Service<RefinerJobStore>(), context, choice, fingerprint);
        var name = System.IO.Path.GetFileName(context.File.RelativePath);
        await ActivityStore.RecordAsync(
            uow,
            ActivityEventTypes.RefinerFileManualPlanQueued,
            "refiner",
            $"Manual track choice queued for {name}",
            $"{session.User.Username} chose {choice.Keep.Count} track(s) to keep for {context.File.RelativePath} (job {job.Id}).")
            .ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);

        return ApiRoutes.Ok(new PyDict()
            .Set("ok", true)
            .Set("job_id", job.Id)
            .Set("dedupe_key", job.DedupeKey)
            .Set("job_kind", job.JobKind));
    }
}

file static class PyDictExtensions
{
    public static PyDict Also(this PyDict dict, Action<PyDict> configure)
    {
        configure(dict);
        return dict;
    }
}
