using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Processing;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Processing;

namespace Weir.Api.Endpoints;

/// <summary>
/// Read-only <c>jobs</c> inspection and pending-only cancel/recover (port of
/// <c>jobs_inspection_api.py</c>), plus the "why is this file held?" diagnostic (port of
/// <c>processing_hold_diagnostic_api.py</c> — see <see cref="HoldDiagnosticStore"/> for what is and is not
/// live without the media-manager port).
/// </summary>
public static class ProcessingJobsEndpoints
{
    public static IEndpointRouteBuilder MapProcessingJobsEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/processing/jobs/inspection", GetInspectionAsync);
        endpoints.MapV1("POST", "/processing/jobs/{job_id}/cancel-pending", PostCancelPendingAsync);
        endpoints.MapV1("POST", "/processing/jobs/{job_id}/recover-finalize-failed", PostRecoverFinalizeFailedAsync);
        endpoints.MapV1("GET", "/processing/files/{file_id}/why-held", GetWhyHeldAsync);
        return endpoints;
    }

    private static PyDict JobOut(ProcessingJob job)
    {
        var (message, nextAction, technicalDetail) = OperatorJobStatus.Build("processing", job.JobKind, job.Status, job.LastError, job.PayloadJson);
        return new PyDict()
            .Set("id", job.Id)
            .Set("dedupe_key", job.DedupeKey)
            .Set("job_kind", job.JobKind)
            .Set("status", job.Status)
            .Set("attempt_count", job.AttemptCount)
            .Set("max_attempts", job.MaxAttempts)
            .Set("lease_owner", job.LeaseOwner)
            .Set("lease_expires_at", job.LeaseExpiresAt is { } lease ? Weir.Core.Time.PyDateTime.FromDateTimeOffset(lease).PydanticJson() : null)
            .Set("last_error", job.LastError)
            .Set("operator_message", message)
            .Set("next_action", nextAction)
            .Set("technical_detail", technicalDetail)
            .Set("payload_json", job.PayloadJson)
            .Set("created_at", Weir.Core.Time.PyDateTime.FromDateTimeOffset(job.CreatedAt).PydanticJson())
            .Set("updated_at", Weir.Core.Time.PyDateTime.FromDateTimeOffset(job.UpdatedAt).PydanticJson());
    }

    private static async Task<ApiResult> GetInspectionAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var limit = request.Query("limit") is { } rawLimit && PydanticRules.TryInt(new PyStr(rawLimit), ["query", "limit"], 1, 100, issues, out var parsedLimit) ? (int)parsedLimit : 50;
        var statuses = request.Context.Request.Query["status"].Where(s => s is not null).Select(s => s!).ToList();
        issues.ThrowIfAny();

        try
        {
            JobsInspectionStore.ValidateStatuses(statuses);
        }
        catch (ArgumentException exception)
        {
            throw new ApiException(422, exception.Message);
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var (rows, defaultRecentSlice) = await JobsInspectionStore.ListAsync(uow, limit, statuses.Count > 0 ? statuses : null).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("jobs", new PyList(rows.Select(r => (PyJson)JobOut(r))))
            .Set("default_recent_slice", defaultRecentSlice));
    }

    private static async Task<ApiResult> PostCancelPendingAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("job_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);
        var jobStore = request.Service<ProcessingJobStore>();
        // Release this request's write lock before ProcessingJobStore opens its own connection, the same
        // hazard RequeueStore and ProcessingWatchedFolderScanDispatchJobHandler already document. Here the
        // writer is RequireUserAsync: every SessionRules.LastSeenTouchGap it refreshes user_sessions.last_seen_at,
        // and that single UPDATE holds the lock until ApiRoutes commits after this handler returns — so the
        // store's BEGIN IMMEDIATE waits out the full busy timeout on a lock only this handler can release.
        // That touch is the only write in this transaction (the handler itself writes nothing through uow),
        // and AuthService.RevokeExpiredAsync already commits session bookkeeping independently of the
        // request's outcome, so committing it early gives up no atomicity this endpoint relied on.
        await request.CommitAsync().ConfigureAwait(false);
        var outcome = await jobStore.CancelPendingAsync(id).ConfigureAwait(false);
        if (outcome == JobActionOutcome.NotFound)
        {
            throw new ApiException(StatusCodes.Status404NotFound, "Job not found.");
        }

        if (outcome == JobActionOutcome.WrongStatus)
        {
            throw new ApiException(StatusCodes.Status409Conflict, "Only pending jobs can be cancelled (not leased, completed, failed, or already cancelled).");
        }

        return ApiRoutes.Ok(new PyDict().Set("ok", true).Set("job_id", id).Set("status", ProcessingJobStatus.Cancelled));
    }

    private static async Task<ApiResult> PostRecoverFinalizeFailedAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("job_id", issues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        var user = await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);
        var jobStore = request.Service<ProcessingJobStore>();
        // Same reason as the cancel-pending handler above: the session touch is the only write in this
        // request's transaction, and it must be committed before the store's own connection asks for the lock.
        await request.CommitAsync().ConfigureAwait(false);
        var outcome = await jobStore.RecoverHandlerOkFinalizeFailedToCompletedAsync(id, user.User.Username).ConfigureAwait(false);
        if (outcome == JobActionOutcome.NotFound)
        {
            throw new ApiException(StatusCodes.Status404NotFound, "Job not found.");
        }

        if (outcome == JobActionOutcome.WrongStatus)
        {
            throw new ApiException(StatusCodes.Status409Conflict, "Only a job whose media work completed but finalization failed can be recovered.");
        }

        return ApiRoutes.Ok(new PyDict().Set("ok", true).Set("job_id", id).Set("status", ProcessingJobStatus.Completed));
    }

    private static async Task<ApiResult> GetWhyHeldAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var id = request.PathInt("file_id", issues);
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var file = await FileStateStore.GetAsync(uow, id).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status404NotFound, "Weir has no record of that file.");
        var library = await LibraryStore.GetAsync(uow, file.LibraryId).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status404NotFound, "The library this file belonged to no longer exists.");

        var connections = request.Service<MediaManagerConnectionService>();
        var outcome = await HoldDiagnosticStore.EvaluateAsync(uow, file, library, connections, request.Context.RequestAborted).ConfigureAwait(false);
        var verdict = outcome.Verdict switch
        {
            CandidateGateVerdict.Proceed => "proceed",
            CandidateGateVerdict.WaitUpstream => "wait_upstream",
            CandidateGateVerdict.NotHeld => "not_held",
            _ => "no_upstream_signal",
        };
        return ApiRoutes.Ok(new PyDict()
            .Set("file_id", id)
            .Set("relative_path", file.RelativePath)
            .Set("library_name", library.Name)
            .Set("recorded_status", file.Status)
            .Set("recorded_reason", file.StatusReason)
            .Set("verdict", verdict)
            .Set("owned", outcome.Owned)
            .Set("blocked_upstream", outcome.BlockedUpstream)
            .Set("blocked_by_connection", outcome.BlockedByConnection)
            .Set("queue_row_count", outcome.QueueRowCount)
            .Set("managers_consulted", outcome.ManagersConsulted)
            .Set("managers_reporting", outcome.ManagersReporting)
            .Set("managers_without_queue_signal", new PyList(outcome.ManagersWithoutQueueSignal.Select(m => (PyJson)PyJson.Of(m))))
            .Set("reasons", new PyList(outcome.Reasons.Select(r => (PyJson)PyJson.Of(r)))));
    }
}
