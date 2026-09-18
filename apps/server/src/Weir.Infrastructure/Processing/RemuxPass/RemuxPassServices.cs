using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Metrics;
using Weir.Core.Processing.RemuxPass;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Processes;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>
/// <c>_record_unhandled_processing_failure</c>'s file half: a handler crash is still a failure, recorded against the file with the
/// retry policy applied, and the library's failure policy acts on it so the file is not stranded (#465).
/// </summary>
public sealed class RemuxPassFailureRecorder : IUnhandledJobFailureRecorder
{
    private readonly SqliteDatabase _database;
    private readonly IFailurePolicy _policy;
    private readonly TimeProvider _time;
    private readonly ILogger<RemuxPassFailureRecorder> _logger;

    public RemuxPassFailureRecorder(SqliteDatabase database, IFailurePolicy policy, TimeProvider time, ILogger<RemuxPassFailureRecorder> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _policy = policy ?? throw new ArgumentNullException(nameof(policy));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public Task<bool?> RecordAsync(UnhandledJobFailure failure, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(failure);
        return LockedWrites.RunAsync<bool?>(
            _database,
            async uow =>
            {
                var library = await RemuxPassHandler.ResolveLibraryAsync(uow, failure.LibraryId, failure.MediaScope).ConfigureAwait(false);
                if (library is null || failure.RelativeMediaPath is null)
                {
                    return null;
                }

                var decision = await RemuxPassFileState.RecordFailureAsync(uow, library, failure.RelativeMediaPath, ProcessingFailureClasses.Unknown, failure.Message, _time.GetUtcNow())
                    .ConfigureAwait(false);
                PyDict? origin = null;
                try
                {
                    origin = PyJsonParser.Parse(failure.Context.PayloadJson ?? "{}") is PyDict payload ? payload.Get("origin") as PyDict : null;
                }
                catch (PyJsonDecodeException)
                {
                }

                await _policy.ApplyFailurePolicyAsync(uow, library, failure.RelativeMediaPath, decision.WillRetry, origin, badRelease: false).ConfigureAwait(false);
                return decision.WillRetry;
            },
            _logger,
            "unhandled failure",
            cancellationToken);
    }
}

/// <summary>Registers the remux pass (#522 part 3): its handler, the failure recorder and the seams it runs through.</summary>
public static class RemuxPassServices
{
    public static IServiceCollection AddWeirRemuxPass(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddWeirPlatform(options);
        services.AddWeirMediaManagers(options);
        services.TryAddSingleton<IMediaToolResolver>(sp => MediaToolResolver.ForCurrentProcess(sp.GetRequiredService<WeirOptions>().WeirHome));
        services.TryAddSingleton<IProcessRunner, ProcessRunner>();
        services.TryAddSingleton<MediaTools>();
        services.TryAddSingleton(sp => new ProcessingJobStore(
            sp.GetRequiredService<SqliteDatabase>(), sp.GetRequiredService<TimeProvider>(), sp.GetService<IJobQueueMetrics>()));
        services.TryAddSingleton<SqliteRemuxPassData>();
        services.TryAddSingleton<IRemuxPassFileFacts>(sp => sp.GetRequiredService<SqliteRemuxPassData>());
        services.TryAddSingleton<IPostSuccessCleanupData>(sp => sp.GetRequiredService<SqliteRemuxPassData>());
        services.TryAddSingleton<ITvSeasonFolderCleanup, TvSeasonFolderCleanup>();
        // Seam for work ported separately: the failure policy's follow-up handlers (pass-through and reject) are
        // registered by AddWeirProcessingFailureFollowUps, which calls this method rather than duplicating it.
        services.TryAddSingleton<IFailurePolicy, QueueingFailurePolicy>();
        services.TryAddSingleton<IOriginalLanguageLookup, MetadataProviderOriginalLanguageLookup>();
        services.TryAddSingleton(new RemuxPassSettings
        {
            ProbeSizeMb = options.ProcessingProbeSizeMb,
            AnalyzeDurationSeconds = options.ProcessingAnalyzeDurationSeconds,
            WatchedFolderMinFileAgeSeconds = options.ProcessingWatchedFolderMinFileAgeSeconds,
            MovieOutputCleanupMinAgeSeconds = options.ProcessingMovieOutputCleanupMinAgeSeconds,
            TvOutputCleanupMinAgeSeconds = options.ProcessingTvOutputCleanupMinAgeSeconds,
        });
        services.TryAddSingleton(sp => new RemuxPassRunner(
            sp.GetRequiredService<MediaTools>(),
            sp.GetRequiredService<IMediaToolResolver>(),
            sp.GetRequiredService<IRemuxPassFileFacts>(),
            sp.GetRequiredService<IPostSuccessCleanupData>(),
            sp.GetRequiredService<ITvSeasonFolderCleanup>(),
            sp.GetRequiredService<IOriginalLanguageLookup>(),
            sp.GetRequiredService<RemuxPassSettings>(),
            sp.GetRequiredService<TimeProvider>(),
            sp.GetRequiredService<ILogger<RemuxPassRunner>>(),
            sp.GetService<RuntimeMetricsStore>(),
            sp.GetService<Weir.Infrastructure.Processing.IOutputOwnership>()));
        services.TryAddSingleton(sp => new RemuxPassHandler(
            sp.GetRequiredService<SqliteDatabase>(),
            sp.GetRequiredService<WeirOptions>(),
            sp.GetRequiredService<RemuxPassRunner>(),
            sp.GetRequiredService<IFailurePolicy>(),
            sp.GetRequiredService<TimeProvider>(),
            sp.GetRequiredService<ILogger<RemuxPassHandler>>(),
            sp.GetService<HandoffCompletionReporter>()));
        services.TryAddEnumerable(ServiceDescriptor.Singleton<IJobHandler, RemuxPassHandler>(sp => sp.GetRequiredService<RemuxPassHandler>()));
        // Replaces the jobs port's placeholder, whichever registration runs first.
        services.Replace(ServiceDescriptor.Singleton<IUnhandledJobFailureRecorder, RemuxPassFailureRecorder>());
        return services;
    }
}
