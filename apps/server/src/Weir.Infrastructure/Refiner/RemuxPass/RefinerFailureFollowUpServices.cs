using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// Registers #522 part 4: what happens once a failure policy has decided (pass-through, reject), the opt-in reject
/// policy's support gate, and the Pass 4 failure-cleanup sweep — completing the seams <c>AddWeirRemuxPass</c> left open.
/// </summary>
public static class RefinerFailureFollowUpServices
{
    public static IServiceCollection AddWeirRefinerFailureFollowUps(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddWeirRemuxPass(options);

        services.TryAddSingleton<RejectSupportEvaluator>();
        services.TryAddSingleton<RejectPacing>();

        services.TryAddSingleton<RefinerPassThroughHandler>();
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, RefinerPassThroughHandler>(sp => sp.GetRequiredService<RefinerPassThroughHandler>()));

        services.TryAddSingleton<RefinerRejectHandler>();
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, RefinerRejectHandler>(sp => sp.GetRequiredService<RefinerRejectHandler>()));

        services.TryAddSingleton<RefinerFailureCleanupSweep>();
        services.TryAddSingleton<MovieFailureCleanupSweepHandler>();
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, MovieFailureCleanupSweepHandler>(sp => sp.GetRequiredService<MovieFailureCleanupSweepHandler>()));
        services.TryAddSingleton<TvFailureCleanupSweepHandler>();
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, TvFailureCleanupSweepHandler>(sp => sp.GetRequiredService<TvFailureCleanupSweepHandler>()));

        return services;
    }
}
