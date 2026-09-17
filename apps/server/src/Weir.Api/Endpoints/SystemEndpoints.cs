using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Weir.Api.Http;
using Weir.Core;
using Weir.Core.Configuration;
using Weir.Core.Readiness;
using Weir.Core.Refiner;
using Weir.Core.Workers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Endpoints;

/// <summary>
/// <c>GET /health</c>, <c>GET /ready</c> and <c>GET /api/v1/system/readiness</c>
/// (ports of <c>weir.platform.health</c> and <c>weir.platform.readiness</c>). Each also answers HEAD.
/// </summary>
public static class SystemEndpoints
{
    private static readonly string[] GetAndHead = [HttpMethods.Get, HttpMethods.Head];

    public static IEndpointRouteBuilder MapSystemEndpoints(this IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var routes = endpoints.ServiceProvider.GetRequiredService<RouteTable>();
        routes.Add("/health", [HttpMethods.Get], "/health");
        routes.Add("/ready", [HttpMethods.Get], "/ready");
        routes.Add("/api/v1/system/readiness", [HttpMethods.Get], "/api/v1/system/readiness");

        endpoints.MapMethods("/health", GetAndHead, async (HttpContext context) =>
        {
            var report = await BuildHealthAsync(context.RequestServices).ConfigureAwait(false);
            await ApiJson.WriteAsync(
                context,
                report.IsOk ? StatusCodes.Status200OK : StatusCodes.Status503ServiceUnavailable,
                new HealthResponse(report.Status, report.Dependencies),
                ApiJsonContext.Default.HealthResponse).ConfigureAwait(false);
        }).WithMetadata(new RouteLabel("/health"));

        endpoints.MapMethods("/ready", GetAndHead, async (HttpContext context) =>
        {
            var report = await BuildReadinessAsync(context.RequestServices).ConfigureAwait(false);
            await ApiJson.WriteAsync(
                context,
                report.Ready ? StatusCodes.Status200OK : StatusCodes.Status503ServiceUnavailable,
                new PublicReadinessResponse(report.Ready, report.Status),
                ApiJsonContext.Default.PublicReadinessResponse).ConfigureAwait(false);
        }).WithMetadata(new RouteLabel("/ready"));

        endpoints.MapMethods("/api/v1/system/readiness", GetAndHead, async (HttpContext context) =>
        {
            var authentication = context.RequestServices.GetRequiredService<IOperatorAuthentication>();
            if (!await authentication.RequireOperatorAsync(context).ConfigureAwait(false))
            {
                return;
            }

            var report = await BuildReadinessAsync(context.RequestServices).ConfigureAwait(false);
            await ApiJson.WriteAsync(
                context,
                report.Ready ? StatusCodes.Status200OK : StatusCodes.Status503ServiceUnavailable,
                ToResponse(report),
                ApiJsonContext.Default.ReadinessResponse).ConfigureAwait(false);
        }).WithMetadata(new RouteLabel("/api/v1/system/readiness"));

        return endpoints;
    }

    internal static async Task<HealthReport> BuildHealthAsync(IServiceProvider services) =>
        HealthReport.FromDatabase(await DatabaseIsConnectedAsync(services).ConfigureAwait(false));

    internal static async Task<ReadinessReport> BuildReadinessAsync(IServiceProvider services)
    {
        var lifecycle = services.GetRequiredService<ServerLifecycle>();
        var options = services.GetRequiredService<WeirOptions>();
        var heartbeats = services.GetRequiredService<WorkerHeartbeats>();
        var databaseReady = await DatabaseIsConnectedAsync(services).ConfigureAwait(false);
        var workers = heartbeats.Snapshot([new KeyValuePair<string, int>("refiner", options.RefinerWorkerCount)]);
        // #552: the watcher (Weir.Infrastructure.Refiner.RefinerWatchedFolderWatcherService) reports here
        // through the shared WatcherStateStore singleton; a host that never registered the Refiner watched-
        // folder area (a minimal test host) still reports "no libraries watched" rather than throwing.
        var watcherSummary = services.GetService<WatcherStateStore>()?.Summary() ?? ReadinessBuilder.NoWatchedLibraries;
        var inputs = new ReadinessInputs(
            lifecycle.Elapsed,
            databaseReady,
            lifecycle.StartupComplete,
            workers,
            watcherSummary);
        return ReadinessBuilder.Build(inputs, WeirVersion.Resolve(options.VersionOverride));
    }

    private static async Task<bool> DatabaseIsConnectedAsync(IServiceProvider services)
    {
        if (!services.GetRequiredService<ServerLifecycle>().DatabaseOpened)
        {
            return false;
        }

        var connected = await services.GetRequiredService<SqliteDatabase>().IsConnectedAsync().ConfigureAwait(false);
        if (!connected)
        {
            services.GetRequiredService<ILoggerFactory>()
                .CreateLogger("Weir.Api.Health")
                .LogError("health check failed: database connectivity probe failed");
        }

        return connected;
    }

    private static ReadinessResponse ToResponse(ReadinessReport report) => new(
        report.Ready,
        report.Version,
        report.Status,
        report.StartupSeconds,
        [.. report.Steps.Select(step => new ReadinessStepResponse(step.Name, step.Status, step.Detail))],
        [.. report.WorkerHealth.Select(lane => new ReadinessWorkerResponse(
            lane.Module, lane.ExpectedWorkers, lane.ActiveWorkers, lane.StaleWorkers, lane.StoppedWorkers, lane.Status, lane.Detail))]);
}
