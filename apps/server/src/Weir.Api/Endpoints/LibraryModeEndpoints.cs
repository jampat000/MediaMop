using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Library;
using Weir.Core.LibraryMode;
using Weir.Core.MediaManagers;
using Weir.Core.Processing;
using Weir.Core.Rules;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Processing.RemuxPass;

namespace Weir.Api.Endpoints;

/// <summary>
/// Library mode (#505): library-folder settings, scanning, the file list and Clean, and the schedule toggle. New surface —
/// there is no Python router to port — see <c>apps/server/README.md</c>, "Library mode", for the storage decision behind it.
/// </summary>
public static class LibraryModeEndpoints
{
    public static IEndpointRouteBuilder MapLibraryModeEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/processing/libraries/{library_id}/library-settings", GetSettingsAsync);
        endpoints.MapV1("PUT", "/processing/libraries/{library_id}/library-settings", PutSettingsAsync);
        endpoints.MapV1("POST", "/processing/libraries/{library_id}/library-scan", PostScanAsync);
        endpoints.MapV1("GET", "/processing/libraries/{library_id}/library-overview", GetOverviewAsync);
        endpoints.MapV1("GET", "/processing/libraries/{library_id}/library-problems", GetProblemsAsync);
        endpoints.MapV1("GET", "/processing/libraries/{library_id}/library-files", GetFilesAsync);
        endpoints.MapV1("POST", "/processing/libraries/{library_id}/library-files/clean", PostCleanAsync);
        endpoints.MapV1("POST", "/processing/libraries/{library_id}/library-schedule", PostScheduleAsync);
        endpoints.MapV1("GET", "/processing/libraries/{library_id}/library-redownloads", GetRedownloadsAsync);
        endpoints.MapV1("POST", "/processing/libraries/{library_id}/library-redownloads", PostRedownloadAsync);
        return endpoints;
    }

    private static async Task<ProcessingLibraryRecord> RequireLibraryAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, long id) =>
        await LibraryStore.GetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "No library with that id.");

    private static PyDict SettingsOut(LibrarySettings settings) => new PyDict()
        .Set("library_folders", new PyList(settings.Folders.Select(f => (PyJson)new PyStr(f))))
        .Set("library_schedule_enabled", settings.ScheduleEnabled)
        .Set("clean_hardlinked_files", settings.CleanHardlinkedFiles)
        .Set("skip_if_manager_would_redownload", settings.SkipIfManagerWouldRedownload);

    private static async Task<ApiResult> GetSettingsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
        return ApiRoutes.Ok(SettingsOut(settings));
    }

    private static async Task<ApiResult> PutSettingsAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var folders = model.StrList("library_folders", []);
        var cleanHardlinkedFiles = model.OptionalBool("clean_hardlinked_files");
        var skipIfManagerWouldRedownload = model.OptionalBool("skip_if_manager_would_redownload");
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        IReadOnlyList<string> validated;
        try
        {
            validated = LibraryFolderRules.Validate(folders, library);
        }
        catch (LibraryModeException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        var existing = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
        var updated = existing with
        {
            Folders = validated,
            CleanHardlinkedFiles = cleanHardlinkedFiles ?? existing.CleanHardlinkedFiles,
            SkipIfManagerWouldRedownload = skipIfManagerWouldRedownload ?? existing.SkipIfManagerWouldRedownload,
        };
        await LibrarySettingsStore.SetAsync(uow, libraryId, updated).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(SettingsOut(updated));
    }

    private static async Task<ApiResult> PostScanAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
        if (settings.Folders.Count == 0)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "Add at least one library folder before scanning.");
        }

        var active = await LibraryScanStore.ActiveScanAsync(uow, library.Id).ConfigureAwait(false);
        if (active is not null)
        {
            await request.CommitAsync().ConfigureAwait(false);
            return ApiRoutes.Ok(new PyDict().Set("job_id", active.JobId).Set("status", active.Status).Set("already_running", true));
        }

        var jobStore = request.Service<ProcessingJobStore>();
        var job = await LibraryScanStore.RequestScanAsync(uow, jobStore, library.Id, "manual").ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("job_id", job.Id).Set("status", job.Status).Set("already_running", false));
    }

    private static PyDict FileOut(LibraryFileRow row) => new PyDict()
        .Set("path", row.Path)
        .Set("size_bytes", row.SizeBytes)
        .Set("modified_at", row.ModifiedTimeUnixSeconds)
        .Set("classification", LibraryScanFileEntry.ClassificationName(row.Classification))
        .Set("summary", row.Summary)
        .Set("reason", row.Reason)
        .Set("removed_audio_tracks", row.RemovedAudioCount)
        .Set("removed_subtitle_tracks", row.RemovedSubtitleCount)
        .Set("estimated_bytes_saved", row.EstimatedBytesSaved)
        .Set("manager_kind", row.ManagerKind)
        .Set("manager_title", row.ManagerTitle)
        .Set("video_codec", row.VideoCodec)
        .Set("video_height", row.VideoHeight)
        .Set("resolution_class", row.ResolutionClass)
        .Set("audio_track_count", row.AudioTrackCount)
        .Set("subtitle_track_count", row.SubtitleTrackCount)
        .Set("audio_summary", row.AudioSummary)
        .Set("subtitle_summary", row.SubtitleSummary)
        .Set("link_count", row.LinkCount)
        .Set("problem_kind", row.ProblemKind is { } kind ? LibraryProblems.Name(kind) : null);

    /// <summary>
    /// The scan's own state for the header: which job, what it is doing, when it last finished and anything it
    /// could not do. <c>running</c> is what the "Scan now" button and its progress read.
    /// </summary>
    private static async Task<PyJson> ScanOutAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, long libraryId)
    {
        var latest = await LibraryScanStore.LatestAsync(uow, libraryId).ConfigureAwait(false);
        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);
        if (latest is null)
        {
            return snapshot is null
                ? PyJson.Null
                : new PyDict().Set("job_id", PyJson.Null).Set("status", "completed").Set("running", false)
                    .Set("generated_at", snapshot.GeneratedAt.ToUnixTimeSeconds()).Set("errors", new PyList([]));
        }

        var running = latest.Status is "pending" or "leased";
        return new PyDict()
            .Set("job_id", latest.JobId)
            .Set("status", latest.Status)
            .Set("running", running)
            .Set("generated_at", snapshot?.GeneratedAt.ToUnixTimeSeconds())
            .Set("errors", new PyList((snapshot?.Errors ?? []).Select(e => (PyJson)new PyStr(e))));
    }

    /// <summary>Reads the Files table's filters, sort and page off the query string.</summary>
    private static LibraryFileQuery QueryFrom(ApiRequest request)
    {
        var facets = new List<LibraryFileFacet>();
        foreach (var facet in LibraryFacets.All)
        {
            if (request.Query(facet) is { Length: > 0 } value)
            {
                facets.Add(new LibraryFileFacet(facet, value));
            }
        }

        return new LibraryFileQuery
        {
            Classification = NullIfBlank(request.Query("classification")),
            ManagerKind = NullIfBlank(request.Query("manager")),
            Search = NullIfBlank(request.Query("q")),
            Facets = facets,
            ProblemKind = LibraryProblems.Parse(request.Query("problem")),
            Sort = LibraryFileSort.Normalize(request.Query("sort")),
            Descending = string.Equals(request.Query("direction"), "desc", StringComparison.OrdinalIgnoreCase),
            Page = PositiveInt(request.Query("page"), 1),
            PageSize = Math.Clamp(PositiveInt(request.Query("page_size"), LibraryFileSort.DefaultPageSize), 1, LibraryFileSort.MaxPageSize),
        };
    }

    private static string? NullIfBlank(string? value) => string.IsNullOrWhiteSpace(value) ? null : value;

    private static int PositiveInt(string? value, int fallback) =>
        int.TryParse(value, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var parsed) && parsed > 0
            ? parsed
            : fallback;

    /// <summary>
    /// #568's Overview: what the library holds and how much of it the rules would touch, plus the breakdowns by
    /// codec, resolution class and language. Every number is a SQL aggregate over <c>library_files</c> and its
    /// facet rows (issue #568 point 7) — this never sends thousands of file rows for the browser to add up.
    /// </summary>
    private static async Task<ApiResult> GetOverviewAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
        var totals = await LibraryViewStore.TotalsAsync(uow, libraryId).ConfigureAwait(false);
        var breakdowns = await LibraryViewStore.AllBreakdownsAsync(uow, libraryId).ConfigureAwait(false);
        var problems = await LibraryViewStore.ProblemsAsync(uow, libraryId, settings.CleanHardlinkedFiles).ConfigureAwait(false);

        var breakdownsOut = new PyDict();
        foreach (var facet in LibraryFacets.All)
        {
            var rows = breakdowns.GetValueOrDefault(facet, []);
            breakdownsOut.Set(facet, new PyList(rows.Select(row => (PyJson)BreakdownRowOut(row, totals.Files))));
        }

        return ApiRoutes.Ok(new PyDict()
            .Set("library_id", libraryId)
            .Set("folders_configured", settings.Folders.Count)
            .Set("scan", await ScanOutAsync(uow, libraryId).ConfigureAwait(false))
            .Set("totals", TotalsOut(totals))
            .Set("breakdowns", breakdownsOut)
            .Set("problems", new PyList(problems.Select(group => (PyJson)ProblemGroupOut(group)))));
    }

    private static PyDict TotalsOut(LibraryTotals totals) => new PyDict()
        .Set("files", totals.Files)
        .Set("size_bytes", totals.SizeBytes)
        .Set("matches", totals.Matches)
        .Set("would_change", totals.WouldChange)
        .Set("cannot_process", totals.CannotProcess)
        .Set("estimated_bytes_saved", totals.EstimatedBytesSaved)
        .Set("total_removed_audio_tracks", totals.RemovedAudioTracks)
        .Set("total_removed_subtitle_tracks", totals.RemovedSubtitleTracks);

    /// <summary><c>share</c> is computed here, not in the browser, so every bar in the UI is drawn from one number.</summary>
    private static PyDict BreakdownRowOut(LibraryBreakdownRow row, long totalFiles) => new PyDict()
        .Set("value", row.Value)
        .Set("files", row.Files)
        .Set("size_bytes", row.SizeBytes)
        .Set("share", totalFiles > 0 ? Math.Round((double)row.Files / totalFiles, 4) : 0.0);

    private static PyDict ProblemGroupOut(LibraryProblemGroup group) => new PyDict()
        .Set("kind", LibraryProblems.Name(group.Kind))
        .Set("title", LibraryProblems.Title(group.Kind))
        .Set("what_to_do", LibraryProblems.WhatToDo(group.Kind))
        .Set("files", group.Files)
        .Set("size_bytes", group.SizeBytes)
        .Set("sample_paths", new PyList(group.SampleFiles.Select(path => (PyJson)new PyStr(path))));

    /// <summary>#568's Problems view: every reason a file is not something Weir will clean, grouped, with advice.</summary>
    private static async Task<ApiResult> GetProblemsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
        var groups = await LibraryViewStore.ProblemsAsync(uow, libraryId, settings.CleanHardlinkedFiles).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("library_id", libraryId)
            .Set("scan", await ScanOutAsync(uow, libraryId).ConfigureAwait(false))
            .Set("groups", new PyList(groups.Select(group => (PyJson)ProblemGroupOut(group))))
            .Set("total", groups.Sum(group => group.Files)));
    }

    /// <summary>
    /// #568's Files table: one page of the library's files, sorted by any of
    /// <see cref="LibraryFileSort.Columns"/> and narrowed by classification, manager, a path/title search, any of
    /// the breakdown facets, or a Problems group. <c>summary</c> is the whole library's totals (what the header
    /// says), <c>filtered</c> the totals for what the filters select, and <c>total</c> the row count behind the
    /// paging.
    /// </summary>
    private static async Task<ApiResult> GetFilesAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);

        var query = QueryFrom(request);
        var overall = await LibraryViewStore.TotalsAsync(uow, libraryId).ConfigureAwait(false);
        var filtered = await LibraryViewStore.TotalsAsync(uow, libraryId, query).ConfigureAwait(false);
        var rows = await LibraryViewStore.ListFilesAsync(uow, libraryId, query).ConfigureAwait(false);

        return ApiRoutes.Ok(new PyDict()
            .Set("library_id", libraryId)
            .Set("scan", await ScanOutAsync(uow, libraryId).ConfigureAwait(false))
            .Set("summary", TotalsOut(overall))
            .Set("filtered", TotalsOut(filtered))
            .Set("files", new PyList(rows.Select(row => (PyJson)FileOut(row))))
            .Set("total", filtered.Files)
            .Set("page", query.Page)
            .Set("page_size", query.PageSize)
            .Set("sort", query.Sort)
            .Set("direction", query.Descending ? "desc" : "asc"));
    }

    /// <summary>The final-removal confirmation numbers for a set of files (#505 point 5), shared by Clean and the schedule toggle.</summary>
    private static (int Files, int Tracks, long BytesSaved) RemovalTotals(IEnumerable<LibraryScanFileEntry> files)
    {
        var removing = files.Where(f => f.Classification == LibraryFileClassification.WouldChange && f.RemovedAudioCount + f.RemovedSubtitleCount > 0).ToList();
        return (removing.Count, removing.Sum(f => f.RemovedAudioCount + f.RemovedSubtitleCount), removing.Sum(f => f.EstimatedBytesSaved));
    }

    /// <summary>
    /// The 400 the web renders as the #505 point 5 confirmation dialog. <c>detail</c> is the exact required sentence; the web
    /// combines it with <c>estimated_bytes_saved</c> for "the size saved" and re-sends the same request with
    /// <c>confirm_final_removal: true</c> once the user agrees. <paramref name="warnings"/> is #508's per-file preflight
    /// notes (seeding, re-download risk) — shown alongside the removal count, whether or not they caused a file to be
    /// skipped outright.
    /// </summary>
    private static JsonApiResult ConfirmationRequired(int files, int tracks, long bytesSaved, IReadOnlyList<string> warnings) => new(
        StatusCodes.Status400BadRequest,
        new PyDict()
            .Set("error", "confirm_final_removal_required")
            .Set("detail", $"{files} files, {tracks} tracks will be removed. Removed tracks are gone for good; getting one back means downloading the title again.")
            .Set("files_count", files)
            .Set("tracks_count", tracks)
            .Set("estimated_bytes_saved", bytesSaved)
            .Set("warnings", new PyList(warnings.Select(w => (PyJson)new PyStr(w)))));

    /// <summary>
    /// #508's hardlink preflight (step 1) for a set of already-scanned files, run at request time rather than trusting the
    /// scan's own cached classification, since a download client can start seeding a file at any moment after it was scanned.
    /// The re-download-risk half (step 2, #551) runs too, for any file a scan matched to a Sonarr/Radarr title: the match
    /// already carries the manager's file id and quality profile id, so no extra lookup is needed beyond the two calls
    /// <see cref="RedownloadRiskChecker"/> itself makes. A file with nothing removed, or no match, never dials out.
    /// </summary>
    private static async Task<List<LibraryFilePreflightResult>> PreflightAsync(
        IEnumerable<LibraryScanFileEntry> files,
        LibrarySettings settings,
        ProcessingRulesConfig rules,
        string mediaScope,
        IHardlinkInspector inspector,
        RedownloadRiskChecker riskChecker,
        IReadOnlyDictionary<long, ManagerConnection> connectionsById,
        CancellationToken cancellationToken)
    {
        var results = new List<LibraryFilePreflightResult>();
        foreach (var file in files)
        {
            int? linkCount;
            try
            {
                linkCount = inspector.LinkCount(file.Path);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                linkCount = null;
            }

            var hardlink = HardlinkPolicy.Evaluate(linkCount, settings.CleanHardlinkedFiles);
            var risk = await RedownloadRiskForFileAsync(file, rules, mediaScope, riskChecker, connectionsById, settings.SkipIfManagerWouldRedownload, cancellationToken).ConfigureAwait(false);
            results.Add(LibraryCleanPreflight.Evaluate(file.Path, hardlink, risk));
        }

        return results;
    }

    private static async Task<RedownloadRiskAssessment?> RedownloadRiskForFileAsync(
        LibraryScanFileEntry file,
        ProcessingRulesConfig rules,
        string mediaScope,
        RedownloadRiskChecker riskChecker,
        IReadOnlyDictionary<long, ManagerConnection> connectionsById,
        bool skipIfManagerWouldRedownload,
        CancellationToken cancellationToken)
    {
        if (file.ManagerConnectionId is not { } connectionId ||
            file.ManagerFileId is not { } fileId ||
            file.ManagerQualityProfileId is not { } qualityProfileId ||
            !connectionsById.TryGetValue(connectionId, out var connection))
        {
            return null;
        }

        var removedAudioLanguages = RemovedAudioLanguages(file, rules);
        if (removedAudioLanguages.Count == 0)
        {
            return null;
        }

        return await riskChecker.CheckAsync(
                connection, mediaScope, fileId, qualityProfileId, file.ManagerTitle ?? Path.GetFileName(file.Path),
                removedAudioLanguages, skipIfManagerWouldRedownload, cancellationToken)
            .ConfigureAwait(false);
    }

    /// <summary>
    /// The languages of the audio tracks the current rules would remove from an already-scanned file, re-derived
    /// from its cached ffprobe JSON (the scan's own plan cache carries only a count, not the languages) — the same
    /// replan <see cref="LibraryCleanHandler"/> runs before actually touching the file.
    /// </summary>
    private static List<string> RemovedAudioLanguages(LibraryScanFileEntry file, ProcessingRulesConfig rules)
    {
        if (file.RemovedAudioCount == 0 || file.ProbeJson is not { Length: > 0 } probeJson)
        {
            return [];
        }

        try
        {
            var classification = LibraryFilePlanner.Classify(ProbeResult.Parse(probeJson), rules);
            return classification.Plan?.RemovedTrackRecords
                .Where(track => track.Type == RemovedTrackType.Audio)
                .Select(track => track.Language)
                .ToList() ?? [];
        }
        catch (RulesInputException)
        {
            return [];
        }
    }

    private static List<string> PreflightWarningMessages(IEnumerable<LibraryFilePreflightResult> preflight) =>
        preflight.Where(r => r.Skip).Select(r => $"{Path.GetFileName(r.FilePath)}: {string.Join(" ", r.SkipReasons)}").ToList();

    /// <summary>The library's rules, exactly as the scan and clean handlers resolve them (no rule set = the defaults).</summary>
    private static async Task<ProcessingRulesConfig> RulesForAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, ProcessingLibraryRecord library)
    {
        var ruleSet = library.RuleSetId is { } ruleSetId ? await LibraryStore.GetRuleSetAsync(uow, ruleSetId).ConfigureAwait(false) : null;
        return ruleSet is not null ? RemuxPassPaths.RulesConfigFor(ruleSet) : RuleSetConversion.ToRulesConfig(null);
    }

    /// <summary>Every distinct manager connection a set of scanned files was matched to, resolved once for a preflight pass.</summary>
    private static async Task<Dictionary<long, ManagerConnection>> ConnectionsForFilesAsync(
        Weir.Infrastructure.Sqlite.UnitOfWork uow, MediaManagerConnectionService connections, IEnumerable<LibraryScanFileEntry> files)
    {
        var ids = files.Select(f => f.ManagerConnectionId).OfType<long>().Distinct().ToList();
        var resolved = await connections.ConnectionsByIdAsync(uow, ids).ConfigureAwait(false);
        return resolved.Where(c => c.ConnectionId is not null).ToDictionary(c => c.ConnectionId!.Value);
    }

    private static async Task<ApiResult> PostCleanAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var paths = model.StrList("paths", []);
        var confirmed = model.Bool("confirm_final_removal", false);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        if (paths.Count == 0)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "Select at least one file to clean.");
        }

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);
        var byPath = (snapshot?.Files ?? []).ToDictionary(f => f.Path, StringComparer.Ordinal);
        var selected = paths.Select(p => byPath.GetValueOrDefault(p)).OfType<LibraryScanFileEntry>().ToList();
        if (selected.Count == 0)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "None of the selected files are in the latest scan. Scan the library again first.");
        }

        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
        var rules = await RulesForAsync(uow, library).ConfigureAwait(false);
        var connectionsById = await ConnectionsForFilesAsync(uow, request.Service<MediaManagerConnectionService>(), selected).ConfigureAwait(false);
        var preflightResults = await PreflightAsync(
                selected, settings, rules, library.MediaType, request.Service<IHardlinkInspector>(),
                request.Service<RedownloadRiskChecker>(), connectionsById, request.Context.RequestAborted)
            .ConfigureAwait(false);
        var preflight = preflightResults.ToDictionary(r => r.FilePath, StringComparer.Ordinal);

        // #568: the Problems view groups "still shared with a download" and "the manager would download it again"
        // from the file's own row. Only a preflight can know either, and a preflight costs a filesystem read and
        // (for the second) two manager calls per file, so this records what it just found rather than making the
        // Problems view re-run it over a whole library. Even a request that ends in the confirmation dialog below
        // has already done the work, so the notes are recorded either way.
        foreach (var result in preflightResults)
        {
            await LibraryViewStore.RecordPreflightProblemAsync(uow, libraryId, result.FilePath, result.ProblemKind).ConfigureAwait(false);
        }

        var (removingFiles, removingTracks, bytesSaved) = RemovalTotals(selected);
        if (removingFiles > 0 && !confirmed)
        {
            // Nothing is queued, but the preflight notes just recorded above are real observations worth keeping
            // even if the operator cancels the dialog, so they are committed rather than rolled back with it.
            await request.CommitAsync().ConfigureAwait(false);
            return ConfirmationRequired(removingFiles, removingTracks, bytesSaved, PreflightWarningMessages(preflight.Values));
        }

        var jobStore = request.Service<ProcessingJobStore>();
        var jobIds = new List<long>();
        var skipped = new List<string>();
        foreach (var entry in selected)
        {
            if (entry.Classification != LibraryFileClassification.WouldChange)
            {
                continue;
            }

            // #508: a file still shared with a download is never queued, confirmation or not — clean_hardlinked_files
            // is the only thing that can allow it, since this is a data-safety fact, not a "are you sure" question.
            if (preflight.TryGetValue(entry.Path, out var fileResult) && fileResult.Skip)
            {
                skipped.Add(entry.Path);
                continue;
            }

            var fileConfirmed = entry.RemovedAudioCount + entry.RemovedSubtitleCount == 0 || confirmed;
            var job = await LibraryScanStore.EnqueueCleanAsync(uow, jobStore, library.Id, entry.Path, "manual", fileConfirmed).ConfigureAwait(false);
            jobIds.Add(job.Id);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("queued", jobIds.Count)
            .Set("job_ids", new PyList(jobIds.Select(id => (PyJson)new PyInt(id))))
            .Set("files_count", removingFiles)
            .Set("tracks_count", removingTracks)
            .Set("estimated_bytes_saved", bytesSaved)
            .Set("skipped_paths", new PyList(skipped.Select(p => (PyJson)new PyStr(p))))
            .Set("warnings", new PyList(PreflightWarningMessages(preflight.Values).Select(w => (PyJson)new PyStr(w)))));
    }

    private static async Task<ApiResult> PostScheduleAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var enabled = model.Bool("enabled", false, required: true);
        var confirmed = model.Bool("confirm_final_removal", false);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);

        if (enabled && !settings.ScheduleEnabled)
        {
            // #505 point 7: turning the schedule on shows the same final-removal warning once, using whatever the last scan found.
            var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);
            var files = snapshot?.Files ?? [];
            var (removingFiles, removingTracks, bytesSaved) = RemovalTotals(files);
            if (removingFiles > 0 && !confirmed)
            {
                var rules = await RulesForAsync(uow, library).ConfigureAwait(false);
                var connectionsById = await ConnectionsForFilesAsync(uow, request.Service<MediaManagerConnectionService>(), files).ConfigureAwait(false);
                var preflight = await PreflightAsync(
                        files, settings, rules, library.MediaType, request.Service<IHardlinkInspector>(),
                        request.Service<RedownloadRiskChecker>(), connectionsById, request.Context.RequestAborted)
                    .ConfigureAwait(false);
                return ConfirmationRequired(removingFiles, removingTracks, bytesSaved, PreflightWarningMessages(preflight));
            }
        }

        var updated = settings with { ScheduleEnabled = enabled };
        await LibrarySettingsStore.SetAsync(uow, libraryId, updated).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(SettingsOut(updated));
    }

    private static PyDict RemovedTrackOut(RemovedTrackRecord track) => new PyDict()
        .Set("language", track.Language)
        .Set("type", track.Type == RemovedTrackType.Audio ? "audio" : "subtitle")
        .Set("codec", track.Codec)
        .Set("variant", track.Variant)
        .Set("reason", track.Reason);

    /// <summary>
    /// #509: titles a library's *current* rules would now keep a track for that a past clean removed for good — "12
    /// titles are missing tracks your new rules keep" (issue #509 step 2's diff), scoped to this library. The
    /// "Download again" action <see cref="PostRedownloadAsync"/> offers is gated on <c>can_redownload</c>
    /// (<see cref="ManagerRedownloadRules.CanRedownload"/>): true only for a manager kind issue #509 verified
    /// (Sonarr/Radarr) <em>and</em> a file #551's title matching actually resolved to one of that manager's titles.
    /// </summary>
    private static async Task<ApiResult> GetRedownloadsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var rules = await RulesForAsync(uow, library).ConfigureAwait(false);

        var removedTrackStore = request.Service<IRemovedTrackStore>();
        var allRemoved = await removedTrackStore.GetAllAsync().ConfigureAwait(false);
        var forLibrary = allRemoved.Where(kv => kv.Key.LibraryId == libraryId).ToDictionary(kv => kv.Key, kv => kv.Value);
        var affected = RemovedTrackDiff.AffectedFiles(rules, forLibrary);

        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);
        var scannedByPath = (snapshot?.Files ?? []).ToDictionary(f => f.Path, StringComparer.Ordinal);

        var items = affected.Select(result =>
        {
            var path = result.File.RelativePath;
            scannedByPath.TryGetValue(path, out var scanned);
            var titleName = scanned?.ManagerTitle ?? System.IO.Path.GetFileName(path);
            var canRedownload = ManagerRedownloadRules.CanRedownload(scanned?.ManagerKind, scanned?.ManagerConnectionId, scanned?.ManagerTitleId);
            return new PyDict()
                .Set("path", path)
                .Set("manager_kind", scanned?.ManagerKind)
                .Set("manager_title", scanned?.ManagerTitle)
                .Set("removed_tracks", new PyList(result.TracksNowWanted.Select(t => (PyJson)RemovedTrackOut(t))))
                .Set("can_redownload", canRedownload)
                .Set("confirmation_message", canRedownload ? ManagerRedownloadRules.DestructiveConfirmation(titleName, null) : null)
                .Set("unavailable_reason", canRedownload
                    ? null
                    : (scanned?.ManagerKind is { } kind && ManagerRedownloadRules.KindSupportsRedownload(kind)
                        ? "Weir does not know which manager file this is, so it cannot ask for a redownload automatically. Scan the library again."
                        : ManagerRedownloadRules.NoManagerMessage));
        }).ToList();

        return ApiRoutes.Ok(new PyDict()
            .Set("library_id", libraryId)
            .Set("titles", new PyList(items.Select(i => (PyJson)i)))
            .Set("total", items.Count));
    }

    /// <summary>
    /// #509 step 3: asks a manager to redownload one title's file. Requires <c>confirm_destructive</c>
    /// (the operator has seen <see cref="ManagerRedownloadRules.DestructiveConfirmation"/>'s exact wording — the
    /// web only shows this action once <c>GET .../library-redownloads</c> said <c>can_redownload: true</c>).
    /// Resolves the manager connection and title id #551's title matching stored on the latest scan for this
    /// path; answers <see cref="RedownloadOutcome.Unsupported"/> when no scan ever matched it (stale scan, or the
    /// file was cleaned by hand between the two), and <c>"failed"</c> when the manager call itself throws before
    /// committing to anything destructive (a network problem, not a data-safety one).
    /// </summary>
    private static async Task<ApiResult> PostRedownloadAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        var model = new BodyModel(payload, issues);
        var path = model.Str("path", minLength: 1);
        var confirmedDestructive = model.Bool("confirm_destructive", false, required: true);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        if (!confirmedDestructive)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "This action deletes the current file before asking for a new one; confirm_destructive must be true.");
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);
        var scanned = (snapshot?.Files ?? []).FirstOrDefault(f => string.Equals(f.Path, path, StringComparison.Ordinal));

        if (!ManagerRedownloadRules.CanRedownload(scanned?.ManagerKind, scanned?.ManagerConnectionId, scanned?.ManagerTitleId))
        {
            await request.CommitAsync().ConfigureAwait(false);
            return ApiRoutes.Ok(new PyDict().Set("path", path).Set("outcome", "unsupported").Set("message", ManagerRedownloadRules.NoManagerMessage));
        }

        var connections = await request.Service<MediaManagerConnectionService>().ConnectionsByIdAsync(uow, [scanned!.ManagerConnectionId!.Value]).ConfigureAwait(false);
        var connection = connections.FirstOrDefault();
        await request.CommitAsync().ConfigureAwait(false);
        if (connection is null)
        {
            return ApiRoutes.Ok(new PyDict().Set("path", path).Set("outcome", "unsupported").Set("message", ManagerRedownloadRules.NoManagerMessage));
        }

        RedownloadResult result;
        try
        {
            result = await request.Service<IManagerRedownload>()
                .RequestRedownloadAsync(connection, library.MediaType, scanned.ManagerTitleId!, path, request.Context.RequestAborted)
                .ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return ApiRoutes.Ok(new PyDict()
                .Set("path", path)
                .Set("outcome", "failed")
                .Set("message", $"Weir could not ask {connection.Label} to download this again: {exception.Message}"));
        }

        var outcome = result.Outcome switch
        {
            RedownloadOutcome.Requested => "requested",
            RedownloadOutcome.DeletedButSearchFailed => "deleted_but_search_failed",
            _ => "unsupported",
        };
        return ApiRoutes.Ok(new PyDict().Set("path", path).Set("outcome", outcome).Set("message", result.Summary));
    }
}
