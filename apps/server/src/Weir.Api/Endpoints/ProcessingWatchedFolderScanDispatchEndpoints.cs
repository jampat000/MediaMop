using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Processing;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;

namespace Weir.Api.Endpoints;

/// <summary>Manual enqueue for watched-folder remux scan dispatch (port of
/// <c>processing_watched_folder_remux_scan_dispatch_api.py</c> and
/// <c>schemas_watched_folder_remux_scan_dispatch_manual.py</c>; <c>jobs</c> only).</summary>
public static class ProcessingWatchedFolderScanDispatchEndpoints
{
    public static IEndpointRouteBuilder MapProcessingWatchedFolderScanDispatchEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("POST", "/processing/jobs/watched-folder-remux-scan-dispatch/enqueue", PostEnqueueAsync);
        return endpoints;
    }

    private static async Task<ApiResult> PostEnqueueAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var enqueueRemuxJobs = model.Bool("enqueue_remux_jobs", defaultValue: true);
        var mediaScope = model.Literal("media_scope", ["movie", "tv"], defaultValue: "movie");
        var libraryId = model.OptionalInt("library_id", ge: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var (ok, error) = await ProcessingWatchedFolderScanDispatchEnqueue.ValidatePrerequisitesAsync(
            uow, enqueueRemuxJobs, mediaScope, libraryId).ConfigureAwait(false);
        if (!ok)
        {
            if (error == ScanDispatchPrerequisiteError.MissingOutputForLiveRemux)
            {
                throw new ApiException(StatusCodes.Status400BadRequest, "enqueue_remux_jobs requires a saved output folder for this media scope.");
            }

            var label = mediaScope == "tv" ? "TV" : "Movies";
            throw new ApiException(
                StatusCodes.Status400BadRequest,
                $"{label} watched folder is not set in saved path settings. This scan reads media files under that folder — configure it first.");
        }

        var jobStore = request.Service<ProcessingJobStore>();
        var job = await ProcessingWatchedFolderScanDispatchEnqueue.EnqueueScanDispatchJobAsync(
            uow, jobStore, enqueueRemuxJobs, "manual", mediaScope, libraryId).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);

        return ApiRoutes.Ok(new PyDict()
            .Set("ok", true)
            .Set("job_id", job.Id)
            .Set("dedupe_key", job.DedupeKey)
            .Set("job_kind", job.JobKind));
    }
}
