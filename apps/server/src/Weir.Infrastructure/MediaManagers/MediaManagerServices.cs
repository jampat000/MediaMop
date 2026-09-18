using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Core.Configuration;
using Weir.Core.Library;
using Weir.Core.MediaManagers;
using Weir.Core.Security;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Library;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>Registers the media manager area (#520): connections, ports, intake, the hand-off ledger and completion reports.</summary>
public static class MediaManagerServices
{
    public static IServiceCollection AddWeirMediaManagers(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddWeirPlatform(options);
        services.TryAddSingleton(sp => new CredentialCipher(
            options.CredentialsSecret, options.SessionSecret, options.PreviousCredentialsSecrets, sp.GetRequiredService<TimeProvider>()));
        services.TryAddSingleton<IManagerHttpHandlerFactory, SocketsManagerHttpHandlerFactory>();
        services.TryAddSingleton<IMediaManagerPorts, HttpMediaManagerPorts>();
        services.TryAddSingleton<MediaManagerConnectionService>();
        services.TryAddSingleton<LibraryDiscoveryService>();
        services.TryAddSingleton<HandoffLedgerStore>();
        services.TryAddSingleton(sp => new ProcessingJobStore(
            sp.GetRequiredService<SqliteDatabase>(), sp.GetRequiredService<TimeProvider>(), sp.GetService<IJobQueueMetrics>()));
        services.TryAddSingleton<MediaManagerIntake>();
        services.TryAddSingleton<HandoffCompletionReporter>();
        services.TryAddSingleton<MetadataProviderService>();
        services.TryAddSingleton<ILibraryFileChangeNotifier, LibraryFileChangeNotifier>();

        // #509: redownloading a title after a removed track can no longer be restored. The store and
        // tracker default to in-memory (see their remarks for why); FileLogRemovedTrackStore is available
        // to opt into instead once a caller wants the payload-backed history to survive a restart.
        services.TryAddSingleton<IManagerRedownload, ArrManagerRedownload>();
        services.TryAddSingleton<IRemovedTrackStore, InMemoryRemovedTrackStore>();
        services.TryAddSingleton<IRedownloadTracker, InMemoryRedownloadTracker>();
        return services;
    }
}
