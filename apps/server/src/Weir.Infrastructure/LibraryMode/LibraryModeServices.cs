using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// Registers library mode (#505): the #506 safe swap (not wired into anything until now — see
/// <c>apps/server/README.md</c>, "Library mode: safe swap"), its scan and clean job handlers, and the real
/// notify seam (#507, <c>Weir.Infrastructure.MediaManagers.LibraryFileChangeNotifier</c>, registered by
/// <c>AddWeirMediaManagers</c>).
/// </summary>
public static class LibraryModeServices
{
    public static IServiceCollection AddWeirLibraryMode(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddWeirMediaManagers(options);
        services.TryAddSingleton<IMediaToolResolver>(sp => new MediaToolResolver(sp.GetRequiredService<WeirOptions>().WeirHome));
        services.TryAddSingleton<Processes.IProcessRunner, Processes.ProcessRunner>();
        services.TryAddSingleton<MediaTools>();

        // The #506 safe swap: real files, real journal (refiner_jobs.payload_json — no new table), the #500 seam.
        services.TryAddSingleton<ISwapFileSystem>(_ => PhysicalSwapFileSystem.Instance);
        services.TryAddSingleton(sp => new RefinerJobSwapJournal(sp.GetRequiredService<SqliteDatabase>()));
        services.TryAddSingleton<ISwapJournal>(sp => sp.GetRequiredService<RefinerJobSwapJournal>());
        services.TryAddSingleton<ISwapOutputValidator, RemuxOutputSwapValidator>();
        services.TryAddSingleton<SafeSwap>();
        services.TryAddSingleton<SwapRecoverySweep>();

        // #507's notify seam: AddWeirMediaManagers (above) registers the real LibraryFileChangeNotifier.
        services.TryAddSingleton<LibraryScanHandler>();
        services.TryAddSingleton<LibraryCleanHandler>();
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, LibraryScanHandler>(sp => sp.GetRequiredService<LibraryScanHandler>()));
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, LibraryCleanHandler>(sp => sp.GetRequiredService<LibraryCleanHandler>()));
        return services;
    }
}
