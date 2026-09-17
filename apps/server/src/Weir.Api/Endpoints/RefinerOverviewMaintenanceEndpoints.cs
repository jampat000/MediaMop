using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Validation;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Refiner;

namespace Weir.Api.Endpoints;

/// <summary>The custody-screen overview stats and the maintenance job families (ports of
/// <c>refiner_overview_stats_api.py</c> and <c>refiner_maintenance_api.py</c>).</summary>
public static class RefinerOverviewMaintenanceEndpoints
{
    public static IEndpointRouteBuilder MapRefinerOverviewMaintenanceEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/overview-stats", GetOverviewStatsAsync);
        endpoints.MapV1("GET", "/refiner/maintenance", GetMaintenanceAsync);
        endpoints.MapV1("POST", "/refiner/maintenance/run", PostMaintenanceRunAsync);
        return endpoints;
    }

    private static async Task<ApiResult> GetOverviewStatsAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var windowDays = request.Query("window_days") is { } raw && PydanticRules.TryInt(new PyStr(raw), ["query", "window_days"], 1, 3650, issues, out var parsed) ? (int)parsed : 30;
        issues.ThrowIfAny();

        var uow = await request.DbAsync().ConfigureAwait(false);
        var stats = await OverviewStatsStore.BuildAsync(uow, windowDays, request.Time).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("window_days", stats.WindowDays)
            .Set("files_processed", stats.FilesProcessed)
            .Set("files_failed", stats.FilesFailed)
            .Set("success_rate_percent", stats.SuccessRatePercent)
            .Set("output_written_count", stats.OutputWrittenCount)
            .Set("already_optimized_count", stats.AlreadyOptimizedCount)
            .Set("net_space_saved_bytes", stats.NetSpaceSavedBytes)
            .Set("net_space_saved_percent", stats.NetSpaceSavedPercent));
    }

    private static PyDict FamilyOut(MaintenanceFamilyState state) => new PyDict()
        .Set("family", state.Family)
        .Set("enabled", state.Enabled)
        .Set("description", state.Description)
        .Set("pending", state.Pending)
        .Set("running", state.Running)
        .Set("last_completed_at", state.LastCompletedAt?.PydanticJson())
        .Set("last_failed_at", state.LastFailedAt?.PydanticJson())
        .Set("last_error", state.LastError);

    private static async Task<ApiResult> GetMaintenanceAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var operatorRow = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var families = new[]
        {
            await MaintenanceStore.StateForAsync(uow, "work_temp_stale_sweep", operatorRow.WorkTempStaleSweepEnabled).ConfigureAwait(false),
            await MaintenanceStore.StateForAsync(uow, "failure_cleanup", operatorRow.FailureCleanupEnabled).ConfigureAwait(false),
        };
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("families", new PyList(families.Select(f => (PyJson)FamilyOut(f)))));
    }

    private static async Task<ApiResult> PostMaintenanceRunAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var family = model.Literal("family", ["work_temp_stale_sweep", "failure_cleanup"]);
        var mediaScope = model.Literal("media_scope", ["movie", "tv"], defaultValue: "movie");
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        if (family == "work_temp_stale_sweep")
        {
            await MaintenanceStore.EnqueueWorkTempStaleSweepAsync(request.Service<RefinerJobStore>(), mediaScope, "manual").ConfigureAwait(false);
            await request.CommitAsync().ConfigureAwait(false);
            var scopeWord = mediaScope == "tv" ? "TV" : "Movies";
            return ApiRoutes.Ok(new PyDict().Set("queued", true).Set("detail", $"Queued a work file sweep for {scopeWord}. It runs as soon as a worker is free."));
        }

        var (jobId, inserted) = await MaintenanceStore.EnqueueFailureCleanupSweepAsync(uow, mediaScope, "manual").ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        if (!inserted)
        {
            return ApiRoutes.Ok(new PyDict()
                .Set("queued", false)
                .Set("job_id", jobId)
                .Set("detail", "A failure cleanup for this scope is already waiting or running, so nothing new was queued."));
        }

        var label = mediaScope == "tv" ? "TV" : "Movies";
        return ApiRoutes.Ok(new PyDict()
            .Set("queued", true)
            .Set("job_id", jobId)
            .Set("detail", $"Queued failure cleanup for {label}. It runs as soon as a worker is free."));
    }
}
