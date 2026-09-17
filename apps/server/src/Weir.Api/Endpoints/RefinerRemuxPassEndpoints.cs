using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Api.Endpoints;

/// <summary>Manual enqueue of one per-file pass (port of <c>file_remux_pass/api.py</c>).</summary>
public static class RefinerRemuxPassEndpoints
{
    public static IEndpointRouteBuilder MapRefinerRemuxPassEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("POST", "/refiner/jobs/file-remux-pass/enqueue", PostEnqueueAsync);
        return endpoints;
    }

    private static async Task<ApiResult> PostEnqueueAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var relativeMediaPath = model.Str("relative_media_path", minLength: 1);
        var mediaScope = model.Literal("media_scope", ["movie", "tv"], "movie");
        var libraryId = model.OptionalInt("library_id", ge: 1);
        var passThrough = model.Bool("pass_through_unchanged", false);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken, "Invalid or expired CSRF token.");

        var uow = await request.DbAsync().ConfigureAwait(false);
        Weir.Core.Jobs.RefinerJob job;
        try
        {
            job = await RemuxPassEnqueue.EnqueueManualAsync(uow, request.Service<RefinerJobStore>(), relativeMediaPath, mediaScope, libraryId, passThrough)
                .ConfigureAwait(false);
        }
        catch (RemuxPassEnqueueException exception)
        {
            throw new ApiException(exception.StatusCode, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("ok", true)
            .Set("job_id", job.Id)
            .Set("dedupe_key", job.DedupeKey)
            .Set("job_kind", job.JobKind));
    }
}
