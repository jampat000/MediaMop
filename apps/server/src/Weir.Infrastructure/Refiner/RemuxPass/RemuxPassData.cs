using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>Short SQLite writes that retry briefly when another local writer holds the lock (<c>_retry_locked_write</c>).</summary>
public static class LockedWrites
{
    private const int Attempts = 4;

    /// <summary>Run <paramref name="work"/> in its own unit of work and commit, retrying a locked database.</summary>
    public static async Task<T> RunAsync<T>(SqliteDatabase database, Func<UnitOfWork, Task<T>> work, ILogger logger, string label, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(database);
        ArgumentNullException.ThrowIfNull(work);
        ArgumentNullException.ThrowIfNull(logger);
        var delay = TimeSpan.FromSeconds(0.1);
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                var uow = await UnitOfWork.OpenAsync(database, cancellationToken).ConfigureAwait(false);
                await using (uow.ConfigureAwait(false))
                {
                    var result = await work(uow).ConfigureAwait(false);
                    await uow.CommitAsync().ConfigureAwait(false);
                    return result;
                }
            }
            catch (SqliteException exception) when (IsLock(exception) && attempt < Attempts - 1)
            {
                logger.LogWarning("Refiner metadata write is waiting for SQLite ({Label}; retry {Attempt}/{Max}).", label, attempt + 1, Attempts - 1);
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
                delay *= 2;
            }
        }
    }

    public static Task RunAsync(SqliteDatabase database, Func<UnitOfWork, Task> work, ILogger logger, string label, CancellationToken cancellationToken = default) =>
        RunAsync<bool>(
            database,
            async uow =>
            {
                await work(uow).ConfigureAwait(false);
                return true;
            },
            logger,
            label,
            cancellationToken);

    /// <summary><c>database is locked</c> or <c>database table is locked</c>.</summary>
    public static bool IsLock(SqliteException exception) =>
        exception?.SqliteErrorCode is 5 or 6;
}

/// <summary>The pass's database and manager reads and writes over SQLite and the media manager ports.</summary>
public sealed class SqliteRemuxPassData : IRemuxPassFileFacts, IPostSuccessCleanupData
{
    private readonly SqliteDatabase _database;
    private readonly MediaManagerConnectionService _connections;
    private readonly ILogger<SqliteRemuxPassData> _logger;

    public SqliteRemuxPassData(SqliteDatabase database, MediaManagerConnectionService connections, ILogger<SqliteRemuxPassData> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public Task RecordMeasuredMediaFactsAsync(MeasuredMediaFacts facts, CancellationToken cancellationToken) =>
        BestEffortAsync(uow => RemuxPassFileState.RecordMeasuredMediaFactsAsync(uow, facts), "measured media facts", cancellationToken);

    public Task RecordOutputCollisionAsync(string relativePath, CollisionDecision decision, CancellationToken cancellationToken) =>
        BestEffortAsync(uow => RemuxPassFileState.RecordOutputCollisionAsync(uow, relativePath, decision), "output collision", cancellationToken);

    public async Task<IReadOnlyList<ManagerLibraryTruth>> CollectLibraryTruthAsync(string mediaScope, CancellationToken cancellationToken)
    {
        var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            return await _connections.CollectLibraryTruthAsync(uow, mediaScope, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
    }

    public async Task<IReadOnlyList<ActiveRemuxJob>> ActiveRemuxJobsAsync(CancellationToken cancellationToken)
    {
        var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            return await uow.QueryAsync(
                "SELECT id, payload_json FROM refiner_jobs WHERE job_kind = $kind AND status IN ('pending', 'leased') ORDER BY id",
                reader => new ActiveRemuxJob(reader.GetInt64(0), reader.IsDBNull(1) ? null : reader.GetString(1)),
                ("$kind", RemuxPassOutcomes.JobKind)).ConfigureAwait(false);
        }
    }

    /// <summary><c>_commit_cleanup_session</c>: optional metadata must never make a safe file mutation look like a failed remux.</summary>
    private async Task BestEffortAsync(Func<UnitOfWork, Task> work, string label, CancellationToken cancellationToken)
    {
        try
        {
            await LockedWrites.RunAsync(_database, work, _logger, label, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is SqliteException or InvalidOperationException)
        {
            _logger.LogWarning(exception, "Refiner could not commit optional file metadata ({Label}); continuing the media pass.", label);
        }
    }
}

/// <summary>
/// #537 item 4: the original language from the configured metadata provider. Movies only, because the provider port asks
/// about movies; a TV episode, an unconfigured provider or an unreadable name declines, and the language preferences decide.
/// </summary>
public sealed class MetadataProviderOriginalLanguageLookup : IOriginalLanguageLookup
{
    private readonly SqliteDatabase _database;
    private readonly MetadataProviderService _providers;

    public MetadataProviderOriginalLanguageLookup(SqliteDatabase database, MetadataProviderService providers)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _providers = providers ?? throw new ArgumentNullException(nameof(providers));
    }

    public async Task<LookupResult> LookupAsync(string mediaScope, string relativeMediaPath, HandoffOrigin? origin, CancellationToken cancellationToken)
    {
        if (mediaScope == "tv")
        {
            return new LookupResult
            {
                Status = LookupResult.StatusNoMatch,
                Detail = "Weir only looks up films with the metadata provider, so TV episodes use the language preferences",
            };
        }

        IMetadataProvider? provider;
        var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            provider = await _providers.BuildProviderAsync(uow).ConfigureAwait(false);
        }

        if (provider is null)
        {
            return new LookupResult
            {
                Status = LookupResult.StatusNotConfigured,
                Detail = "no metadata provider is configured",
            };
        }

        var parsed = TitleFor(relativeMediaPath, origin);
        if (parsed is not { } title)
        {
            return new LookupResult { Status = LookupResult.StatusNoMatch, Detail = "Weir could not read a film title from the file name" };
        }

        return await provider.LookupMovieAsync(title.Title, title.Year, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>The hand-off's release name first, then the release folder, then the file's own name.</summary>
    public static (string Title, int? Year)? TitleFor(string relativeMediaPath, HandoffOrigin? origin)
    {
        var parts = (relativeMediaPath ?? string.Empty).Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries);
        var candidates = new List<string?> { origin?.ReleaseName };
        if (parts.Length > 1)
        {
            candidates.Add(parts[^2]);
        }

        if (parts.Length > 0)
        {
            candidates.Add(Path.GetFileNameWithoutExtension(parts[^1]));
        }

        foreach (var candidate in candidates)
        {
            if (ReleaseTitle.Parse(candidate) is { } title)
            {
                return title;
            }
        }

        return null;
    }
}

/// <summary>
/// #531 item 2: a retry or requeue of a handed-over file must still carry the hand-off origin, so the final completion,
/// hold or pass-through is reported to the manager with its output path. The origin is found on the most recent job for
/// the same file that carried one, and only while that hand-off has not already been answered.
/// </summary>
public static class HandoffOriginCarry
{
    private static readonly string[] Kinds = [RemuxPassOutcomes.JobKind, IntakeRules.PassThroughJobKind, IntakeRules.RejectJobKind];

    /// <summary>The origin to carry for this file, or null.</summary>
    public static async Task<PyDict?> FindAsync(UnitOfWork uow, long? libraryId, string relativePath, long? excludeJobId = null)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync(
            "SELECT id, payload_json FROM refiner_jobs WHERE job_kind IN ($a, $b, $c) AND payload_json LIKE '%\"origin\"%' ORDER BY id DESC LIMIT 500",
            reader => (Id: reader.GetInt64(0), Payload: reader.IsDBNull(1) ? null : reader.GetString(1)),
            ("$a", Kinds[0]),
            ("$b", Kinds[1]),
            ("$c", Kinds[2])).ConfigureAwait(false);
        foreach (var (id, payload) in rows)
        {
            if (id == excludeJobId || payload is null)
            {
                continue;
            }

            PyJson parsed;
            try
            {
                parsed = PyJsonParser.Parse(payload);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (parsed is not PyDict dict ||
                dict.Get("relative_media_path") is not PyStr path || PyStrings.Strip(path.Value) != PyStrings.Strip(relativePath) ||
                dict.Get("origin") is not PyDict origin)
            {
                continue;
            }

            if (libraryId is { } wanted && dict.Get("library_id") is PyInt jobLibrary && jobLibrary.Value != wanted)
            {
                continue;
            }

            if (HandoffOrigin.FromPayload(dict) is not { HandoffId: { } handoffId } parsedOrigin)
            {
                continue;
            }

            var ledger = await HandoffLedgerStore.FindAsync(uow, parsedOrigin.SourceKey, handoffId).ConfigureAwait(false);
            if (ledger is null || ledger.State is HandoffLedgerRules.Completed or HandoffLedgerRules.PassedThrough or HandoffLedgerRules.Rejected or HandoffLedgerRules.Cancelled)
            {
                return null;
            }

            return origin;
        }

        return null;
    }
}
