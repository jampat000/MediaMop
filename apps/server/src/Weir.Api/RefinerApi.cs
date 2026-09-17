using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Api.Endpoints;
using Weir.Core.Configuration;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;
using Weir.Infrastructure.Refiner;
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
        services.AddSingleton<FileLogRetentionTask>();
        services.AddSingleton<IPeriodicTask>(sp => sp.GetRequiredService<FileLogRetentionTask>());
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
        endpoints.MapRefinerOverviewMaintenanceEndpoints();
        endpoints.MapRefinerSettingsEndpoints();
        return endpoints;
    }
}
