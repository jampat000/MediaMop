using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Library;
using Weir.Core.LibraryMode;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Api.Endpoints;

/// <summary>
/// Library mode (#505): library-folder settings, scanning, the file list and Clean, and the schedule toggle. New surface —
/// there is no Python router to port — see <c>apps/server/README.md</c>, "Library mode", for the storage decision behind it.
/// </summary>
public static class LibraryModeEndpoints
{
    public static IEndpointRouteBuilder MapLibraryModeEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/libraries/{library_id}/library-settings", GetSettingsAsync);
        endpoints.MapV1("PUT", "/refiner/libraries/{library_id}/library-settings", PutSettingsAsync);
        endpoints.MapV1("POST", "/refiner/libraries/{library_id}/library-scan", PostScanAsync);
        endpoints.MapV1("GET", "/refiner/libraries/{library_id}/library-files", GetFilesAsync);
        endpoints.MapV1("POST", "/refiner/libraries/{library_id}/library-files/clean", PostCleanAsync);
        endpoints.MapV1("POST", "/refiner/libraries/{library_id}/library-schedule", PostScheduleAsync);
        endpoints.MapV1("GET", "/refiner/libraries/{library_id}/library-redownloads", GetRedownloadsAsync);
        endpoints.MapV1("POST", "/refiner/libraries/{library_id}/library-redownloads", PostRedownloadAsync);
        return endpoints;
    }

    private static async Task<RefinerLibraryRecord> RequireLibraryAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, long id) =>
        await LibraryStore.GetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "No Refiner library with that id.");

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

        var jobStore = request.Service<RefinerJobStore>();
        var job = await LibraryScanStore.RequestScanAsync(uow, jobStore, library.Id, "manual").ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("job_id", job.Id).Set("status", job.Status).Set("already_running", false));
    }

    private static PyDict FileOut(LibraryScanFileEntry entry) => new PyDict()
        .Set("path", entry.Path)
        .Set("size_bytes", entry.SizeBytes)
        .Set("classification", LibraryScanFileEntry.ClassificationName(entry.Classification))
        .Set("summary", entry.Summary)
        .Set("reason", entry.Reason)
        .Set("removed_audio_tracks", entry.RemovedAudioCount)
        .Set("removed_subtitle_tracks", entry.RemovedSubtitleCount)
        .Set("estimated_bytes_saved", entry.EstimatedBytesSaved)
        .Set("manager_kind", entry.ManagerKind)
        .Set("manager_title", entry.ManagerTitle);

    private static async Task<ApiResult> GetFilesAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var classification = request.Query("classification");
        var manager = request.Query("manager");
        var search = request.Query("q");

        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var latest = await LibraryScanStore.LatestAsync(uow, libraryId).ConfigureAwait(false);
        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);

        var files = (snapshot?.Files ?? []).AsEnumerable();
        if (!string.IsNullOrWhiteSpace(classification))
        {
            files = files.Where(f => string.Equals(LibraryScanFileEntry.ClassificationName(f.Classification), classification, StringComparison.OrdinalIgnoreCase));
        }

        if (!string.IsNullOrWhiteSpace(manager))
        {
            files = files.Where(f => string.Equals(f.ManagerKind, manager, StringComparison.OrdinalIgnoreCase));
        }

        if (!string.IsNullOrWhiteSpace(search))
        {
            files = files.Where(f => f.Path.Contains(search, StringComparison.OrdinalIgnoreCase));
        }

        var filtered = files.ToList();
        var all = snapshot?.Files ?? [];
        return ApiRoutes.Ok(new PyDict()
            .Set("library_id", libraryId)
            .Set("scan", latest is null
                ? PyJson.Null
                : new PyDict().Set("job_id", latest.JobId).Set("status", latest.Status).Set("generated_at", snapshot?.GeneratedAt.ToUnixTimeSeconds()))
            .Set("summary", new PyDict()
                .Set("matches", all.Count(f => f.Classification == LibraryFileClassification.Matches))
                .Set("would_change", all.Count(f => f.Classification == LibraryFileClassification.WouldChange))
                .Set("cannot_process", all.Count(f => f.Classification == LibraryFileClassification.CannotProcess))
                .Set("total_removed_audio_tracks", (long)all.Sum(f => f.RemovedAudioCount))
                .Set("total_removed_subtitle_tracks", (long)all.Sum(f => f.RemovedSubtitleCount))
                .Set("estimated_bytes_saved", all.Sum(f => f.EstimatedBytesSaved)))
            .Set("files", new PyList(filtered.Select(f => (PyJson)FileOut(f))))
            .Set("total", filtered.Count));
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
    /// The re-download-risk half (step 2) needs the manager's file id and quality profile id, which #505's title matching does
    /// not resolve yet (<c>apps/server/README.md</c>, "Seams for #507, #508 and #509") — <see cref="LibraryCleanPreflight"/> is
    /// still the single place that decision is made, it just never receives a risk assessment here.
    /// </summary>
    private static List<LibraryFilePreflightResult> Preflight(
        IEnumerable<LibraryScanFileEntry> files, LibrarySettings settings, IHardlinkInspector inspector)
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
            results.Add(LibraryCleanPreflight.Evaluate(file.Path, hardlink, redownloadRisk: null));
        }

        return results;
    }

    private static List<string> PreflightWarningMessages(IEnumerable<LibraryFilePreflightResult> preflight) =>
        preflight.Where(r => r.Skip).Select(r => $"{Path.GetFileName(r.FilePath)}: {string.Join(" ", r.SkipReasons)}").ToList();

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
        var preflight = Preflight(selected, settings, request.Service<IHardlinkInspector>()).ToDictionary(r => r.FilePath, StringComparer.Ordinal);

        var (removingFiles, removingTracks, bytesSaved) = RemovalTotals(selected);
        if (removingFiles > 0 && !confirmed)
        {
            return ConfirmationRequired(removingFiles, removingTracks, bytesSaved, PreflightWarningMessages(preflight.Values));
        }

        var jobStore = request.Service<RefinerJobStore>();
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
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);

        if (enabled && !settings.ScheduleEnabled)
        {
            // #505 point 7: turning the schedule on shows the same final-removal warning once, using whatever the last scan found.
            var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, libraryId).ConfigureAwait(false);
            var files = snapshot?.Files ?? [];
            var (removingFiles, removingTracks, bytesSaved) = RemovalTotals(files);
            if (removingFiles > 0 && !confirmed)
            {
                var preflight = Preflight(files, settings, request.Service<IHardlinkInspector>());
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
    /// "Download again" action <see cref="PostRedownloadAsync"/> offers is gated on <c>can_redownload</c>: true only
    /// for a manager kind issue #509 verified (Sonarr/Radarr) <em>and</em> one Weir can actually name the manager's own
    /// file for — #505's title matching (<c>apps/server/README.md</c>, "Seams for #507, #508 and #509") does not
    /// resolve that id yet, so this is always false today; the field exists so the web needs no change once it does.
    /// </summary>
    private static async Task<ApiResult> GetRedownloadsAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);
        var ruleSet = library.RuleSetId is { } ruleSetId ? await LibraryStore.GetRuleSetAsync(uow, ruleSetId).ConfigureAwait(false) : null;
        var rules = ruleSet is not null ? RemuxPassPaths.RulesConfigFor(ruleSet) : RuleSetConversion.ToRulesConfig(null);

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
            var canRedownload = false; // see the method doc comment: never true until #505's title matching lands.
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
                        ? "Weir does not yet track which manager file this is, so it cannot ask for a redownload automatically."
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
    /// web only shows this action once <c>GET .../library-redownloads</c> said <c>can_redownload: true</c>). Always
    /// answers <see cref="RedownloadOutcome.Unsupported"/> today for the reason <see cref="GetRedownloadsAsync"/>
    /// documents: no manager file id to act on.
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
        await RequireLibraryAsync(uow, libraryId).ConfigureAwait(false);

        // No numeric manager file id is available yet (see GetRedownloadsAsync's remarks) — nothing here can
        // safely name a specific manager file to delete, so this never reaches IManagerRedownload today.
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("path", path)
            .Set("outcome", "unsupported")
            .Set("message", ManagerRedownloadRules.NoManagerMessage));
    }
}
