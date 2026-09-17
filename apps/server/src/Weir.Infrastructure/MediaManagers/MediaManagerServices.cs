using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Core.Configuration;
using Weir.Core.MediaManagers;
using Weir.Core.Security;
using Weir.Infrastructure.Jobs;
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
        services.TryAddSingleton<HandoffLedgerStore>();
        services.TryAddSingleton(sp => new RefinerJobStore(
            sp.GetRequiredService<SqliteDatabase>(), sp.GetRequiredService<TimeProvider>(), sp.GetService<IJobQueueMetrics>()));
        services.TryAddSingleton<MediaManagerIntake>();
        services.TryAddSingleton<HandoffCompletionReporter>();
        services.TryAddSingleton<MetadataProviderService>();
        services.TryAddSingleton<ILibraryFileChangeNotifier, LibraryFileChangeNotifier>();
        return services;
    }
}
