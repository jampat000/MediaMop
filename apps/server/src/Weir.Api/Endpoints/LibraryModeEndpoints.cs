using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Core.Refiner;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Refiner;

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
        return endpoints;
    }

    private static async Task<RefinerLibraryRecord> RequireLibraryAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, long id) =>
        await LibraryStore.GetAsync(uow, id).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, "No Refiner library with that id.");

    private static PyDict SettingsOut(LibrarySettings settings) => new PyDict()
        .Set("library_folders", new PyList(settings.Folders.Select(f => (PyJson)new PyStr(f))))
        .Set("library_schedule_enabled", settings.ScheduleEnabled);

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
        var updated = existing with { Folders = validated };
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
    /// <c>confirm_final_removal: true</c> once the user agrees.
    /// </summary>
    private static JsonApiResult ConfirmationRequired(int files, int tracks, long bytesSaved) => new(
        StatusCodes.Status400BadRequest,
        new PyDict()
            .Set("error", "confirm_final_removal_required")
            .Set("detail", $"{files} files, {tracks} tracks will be removed. Removed tracks are gone for good; getting one back means downloading the title again.")
            .Set("files_count", files)
            .Set("tracks_count", tracks)
            .Set("estimated_bytes_saved", bytesSaved)
            // Empty until #508's LibraryCleanPreflight (seeding/re-download risk) lands; the field's shape is
            // stable now so the web dialog (which already renders it) needs no change when it is populated.
            .Set("warnings", new PyList()));

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

        var (removingFiles, removingTracks, bytesSaved) = RemovalTotals(selected);
        if (removingFiles > 0 && !confirmed)
        {
            return ConfirmationRequired(removingFiles, removingTracks, bytesSaved);
        }

        var jobStore = request.Service<RefinerJobStore>();
        var jobIds = new List<long>();
        foreach (var entry in selected)
        {
            if (entry.Classification != LibraryFileClassification.WouldChange)
            {
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
            .Set("estimated_bytes_saved", bytesSaved));
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
            var (removingFiles, removingTracks, bytesSaved) = RemovalTotals(snapshot?.Files ?? []);
            if (removingFiles > 0 && !confirmed)
            {
                return ConfirmationRequired(removingFiles, removingTracks, bytesSaved);
            }
        }

        var updated = settings with { ScheduleEnabled = enabled };
        await LibrarySettingsStore.SetAsync(uow, libraryId, updated).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(SettingsOut(updated));
    }
}
