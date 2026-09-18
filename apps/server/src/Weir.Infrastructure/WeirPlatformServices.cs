using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Configuration;
using Weir.Core.Processing;
using Weir.Core.Time;
using Weir.Core.Workers;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure;

/// <summary>The singletons every area shares, registered once whichever area adds them first.</summary>
public static class WeirPlatformServices
{
    /// <summary>Options, the clock, the database, worker heartbeats, time zones and the Activity writer.</summary>
    public static IServiceCollection AddWeirPlatform(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.TryAddSingleton(options);
        services.TryAddSingleton(TimeProvider.System);
        services.TryAddSingleton(_ => new SqliteDatabase(options.DbPath));
        services.TryAddSingleton<WorkerHeartbeats>();
        services.TryAddSingleton<WatcherStateStore>();
        services.TryAddSingleton<ITimeZoneResolver, IanaTimeZoneResolver>();
        services.TryAddSingleton<IActivityWriter, SqliteActivityWriter>();
        services.TryAddSingleton(sp => ActivityNotifications.For(sp.GetRequiredService<SqliteDatabase>()));

        // #555: WEIR_CHOWN_OUTPUT/WEIR_FILE_MODE_OUTPUT/WEIR_DIR_MODE_OUTPUT. Windows gets a no-op tools
        // implementation (there is no POSIX owner or mode there) and, when an operator actually set one of these,
        // a one-time warning at startup rather than a silent no-op.
        services.TryAddSingleton<IOutputOwnershipTools>(sp =>
        {
            if (!OperatingSystem.IsWindows())
            {
                return new LinuxOutputOwnershipTools();
            }

            if (options.OutputOwnershipChownEnabled || options.OutputOwnershipFileMode is not null || options.OutputOwnershipDirectoryMode is not null)
            {
                sp.GetRequiredService<ILogger<WindowsOutputOwnershipTools>>().LogWarning(
                    "WEIR_CHOWN_OUTPUT / WEIR_FILE_MODE_OUTPUT / WEIR_DIR_MODE_OUTPUT are set, but Windows has no " +
                    "POSIX owner or mode bits to apply them to. Weir is ignoring them.");
            }

            return new WindowsOutputOwnershipTools();
        });
        services.TryAddSingleton<IOutputOwnership, OutputOwnership>();
        return services;
    }

    /// <summary>
    /// Hosts every registered <see cref="IPeriodicTask"/>. Added by the job host after startup recovery,
    /// so, as in Python's lifespan, no periodic work starts before interrupted jobs are recovered.
    /// </summary>
    public static IServiceCollection AddWeirPeriodicTasks(this IServiceCollection services)
    {
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IHostedService, PeriodicTaskService>());
        return services;
    }
}
