using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Api.Endpoints;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Scheduling;

namespace Weir.Api;

/// <summary>
/// DI registration and route wiring for the Refiner libraries, file state, files/inspection/maintenance/
/// overview/hardware/Direct Play APIs (part of #522). One extension per side, additive only: it never
/// touches <see cref="Weir.Api.WeirApi"/>'s own registrations, so the media-managers (#520) and activity
/// (#519) ports can add their own <c>AddWeirXxx</c> alongside this without conflict.
/// </summary>
public static class RefinerApi
{
    /// <summary>Services the Refiner endpoints need beyond <c>AddWeirApi</c>/<c>AddWeirJobs</c> (already
    /// registered by the auth/settings and jobs ports respectively).</summary>
    public static IServiceCollection AddWeirRefinerApis(this IServiceCollection services)
    {
        services.TryAddSingleton<IMediaToolResolver>(sp => new MediaToolResolver(sp.GetRequiredService<WeirOptions>().WeirHome));
        services.TryAddSingleton<IProcessRunner, ProcessRunner>();
        services.TryAddSingleton<MediaTools>();
        // Caps the #502 "Try on a file" preview at one run at a time (see RulesPreviewGate's own docs).
        services.TryAddSingleton<RulesPreviewGate>();

        // Not registered here: Weir.Infrastructure.Refiner.FileLogRetentionTask duplicates
        // Weir.Infrastructure.Jobs.RefinerFileLogRetentionTask (registered by AddWeirJobs) — both port the
        // same refiner_file_log_retention_periodic sweep under the identical periodic-task name
        // "refiner-file-log-retention", an accidental collision from #519 and #522 having each ported it
        // independently. Registering both here doubled the periodic task list under one name and made two
        // separate pruning passes race each other for no benefit; the jobs one already runs unconditionally,
        // so this one is left unregistered rather than deleting either #519's or #522's file outright.

        // Watched-folder scan dispatch (#522 part 5): the job handler that runs a scan, and the periodic
        // scheduler that enqueues one per library. Additive: the job handler registry (AddWeirJobs) simply
        // gains one more kind it can claim, and the periodic task joins the others already registered.
        services.AddSingleton<RefinerWatchedFolderScanDispatchJobHandler>();
        services.AddSingleton<IJobHandler>(sp => sp.GetRequiredService<RefinerWatchedFolderScanDispatchJobHandler>());
        services.AddSingleton<IPeriodicTask, RefinerWatchedFolderScanDispatchScheduleTask>();
        return services;
    }

    /// <summary>Maps every Refiner-native route this PR ports (see the module docs on each endpoint class
    /// for exactly what is and is not covered).</summary>
    public static IEndpointRouteBuilder MapWeirRefinerApis(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapRefinerLibraryEndpoints();
        endpoints.MapRefinerFilesEndpoints();
        endpoints.MapRefinerDirectPlayEndpoints();
        endpoints.MapRefinerJobsEndpoints();
        endpoints.MapRefinerRemuxPassEndpoints();
        endpoints.MapRefinerRulesPreviewEndpoints();
        endpoints.MapRefinerOverviewMaintenanceEndpoints();
        endpoints.MapRefinerSettingsEndpoints();
        endpoints.MapRefinerWatchedFolderScanDispatchEndpoints();
        return endpoints;
    }
}
