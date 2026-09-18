using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Api.Endpoints;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Processing;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Processing.RemuxPass;
using Weir.Infrastructure.Scheduling;

namespace Weir.Api;

/// <summary>
/// DI registration and route wiring for the Processing libraries, file state, files/inspection/maintenance/
/// overview/hardware/Direct Play APIs (part of #522). One extension per side, additive only: it never
/// touches <see cref="Weir.Api.WeirApi"/>'s own registrations, so the media-managers (#520) and activity
/// (#519) ports can add their own <c>AddWeirXxx</c> alongside this without conflict.
/// </summary>
public static class ProcessingApi
{
    /// <summary>Services the Processing endpoints need beyond <c>AddWeirApi</c>/<c>AddWeirJobs</c> (already
    /// registered by the auth/settings and jobs ports respectively).</summary>
    public static IServiceCollection AddWeirProcessingApis(this IServiceCollection services)
    {
        services.TryAddSingleton<IMediaToolResolver>(sp => MediaToolResolver.ForCurrentProcess(sp.GetRequiredService<WeirOptions>().WeirHome));
        services.TryAddSingleton<IProcessRunner, ProcessRunner>();
        services.TryAddSingleton<MediaTools>();
        // Caps the #502 "Try on a file" preview at one run at a time (see RulesPreviewGate's own docs).
        services.TryAddSingleton<RulesPreviewGate>();

        // The activity port (#519) and this Processing-apis port (#522) each independently ported
        // processing_file_log_retention_periodic; #546 kept this one (it uses the same UnitOfWork/
        // OperatorSettingsStore/FileLogStore plumbing as the rest of Processing) and deleted the activity
        // port's duplicate file and registration, so this is the only "processing-file-log-retention" task.
        services.AddSingleton<FileLogRetentionTask>();
        services.AddSingleton<IPeriodicTask>(sp => sp.GetRequiredService<FileLogRetentionTask>());

        // Watched-folder scan dispatch (#522 part 5): the job handler that runs a scan, and the periodic
        // scheduler that enqueues one per library. Additive: the job handler registry (AddWeirJobs) simply
        // gains one more kind it can claim, and the periodic task joins the others already registered.
        services.AddSingleton<ProcessingWatchedFolderScanDispatchJobHandler>();
        services.AddSingleton<IJobHandler>(sp => sp.GetRequiredService<ProcessingWatchedFolderScanDispatchJobHandler>());
        services.AddSingleton<IPeriodicTask, ProcessingWatchedFolderScanDispatchScheduleTask>();

        // Watched-folder filesystem watcher (#552): FileSystemWatcher per enabled/watched library, feeding
        // the same scan-dispatch enqueue above. Runs independently of the periodic scheduler — see
        // ProcessingWatchedFolderWatcherService's own docs for what it does and how it diverges from Python.
        services.TryAddSingleton<WatcherStateStore>();
        services.AddHostedService<ProcessingWatchedFolderWatcherService>();
        return services;
    }

    /// <summary>Maps every Processing-native route this PR ports (see the module docs on each endpoint class
    /// for exactly what is and is not covered).</summary>
    public static IEndpointRouteBuilder MapWeirProcessingApis(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapProcessingLibraryEndpoints();
        endpoints.MapProcessingFilesEndpoints();
        endpoints.MapProcessingDirectPlayEndpoints();
        endpoints.MapProcessingJobsEndpoints();
        endpoints.MapProcessingRemuxPassEndpoints();
        endpoints.MapProcessingRulesPreviewEndpoints();
        endpoints.MapProcessingOverviewMaintenanceEndpoints();
        endpoints.MapProcessingSettingsEndpoints();
        endpoints.MapProcessingWatchedFolderScanDispatchEndpoints();
        endpoints.MapLibraryModeEndpoints();
        return endpoints;
    }
}
