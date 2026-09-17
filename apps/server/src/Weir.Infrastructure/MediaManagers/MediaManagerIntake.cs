using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>An intake request refused with a status and a detail (FastAPI's <c>HTTPException</c> inside <c>intake_api</c>).</summary>
public sealed class IntakeRefusedException : Exception
{
    public IntakeRefusedException()
    {
    }

    public IntakeRefusedException(string message)
        : base(message)
    {
    }

    public IntakeRefusedException(string message, Exception innerException)
        : base(message, innerException)
    {
    }

    public IntakeRefusedException(int statusCode, string detail)
        : base(detail)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; } = 400;
}

/// <summary>
/// The intake webhook's work (port of <c>intake_api</c>): who may post, which library a hand-off belongs to, which files
/// it means, and the remux jobs and ledger row it leaves behind.
/// </summary>
public sealed class MediaManagerIntake
{
    private readonly WeirOptions _options;
    private readonly MediaManagerConnectionService _connections;
    private readonly HandoffLedgerStore _ledger;
    private readonly RefinerJobStore _jobs;
    private readonly TimeProvider _time;

    public MediaManagerIntake(WeirOptions options, MediaManagerConnectionService connections, HandoffLedgerStore ledger, RefinerJobStore jobs, TimeProvider time)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
        _jobs = jobs ?? throw new ArgumentNullException(nameof(jobs));
        _time = time ?? throw new ArgumentNullException(nameof(time));
    }

    /// <summary>For tests: where fresh dedupe ids come from when a hand-off names none.</summary>
    public Func<Guid> NewGuid { get; init; } = Guid.NewGuid;

    public HandoffLedgerStore Ledger => _ledger;

    public RefinerJobStore Jobs => _jobs;

    /// <summary>
    /// <c>_authorise</c>: this source's own connection secret when it has one, else the instance-wide secret, else no check.
    /// #544 item 6: Python (and the first cut of this port) resolved only the first enabled connection of the kind,
    /// so a second connection of the same kind — a 4K Radarr next to a 1080p one, each with its own secret — could
    /// never authenticate: its secret was never even considered. The presented secret is now matched against every
    /// enabled connection of the kind, and the event is authorised (attributed) as coming from whichever one
    /// matches. The instance-wide secret remains the fallback only when none of them has a secret configured at
    /// all — once any connection of this kind is using its own secret, that connection's callers must present it.
    /// </summary>
    public async Task AuthoriseAsync(UnitOfWork uow, string sourceKey, string? presented)
    {
        var connections = await MediaManagerConnectionStore.ListEnabledForKindAsync(uow, sourceKey).ConfigureAwait(false);
        var withSecret = connections.Where(connection => !string.IsNullOrEmpty(connection.WebhookSecretCiphertext)).ToList();
        if (withSecret.Count > 0)
        {
            if (!withSecret.Any(connection => _connections.WebhookSecretMatches(connection, presented)))
            {
                throw new IntakeRefusedException(401, IntakeRules.MissingSecretDetail);
            }

            return;
        }

        var configured = _options.MediaManagerWebhookSecret;
        if (string.IsNullOrEmpty(configured))
        {
            return;
        }

        var provided = PyStrings.Strip(presented ?? string.Empty);
        if (provided.Length == 0 || !MediaManagerConnectionService.CompareDigest(provided, configured))
        {
            throw new IntakeRefusedException(401, IntakeRules.MissingSecretDetail);
        }
    }

    /// <summary>
    /// <c>_require_secret</c>: the hand-off routes reveal file paths, so unlike the webhook they never run unauthenticated.
    /// </summary>
    public async Task RequireSecretAsync(UnitOfWork uow, string? presented, string? sourceKey)
    {
        var provided = PyStrings.Strip(presented ?? string.Empty);
        var rows = await MediaManagerConnectionStore.ListEnabledWithWebhookSecretAsync(uow).ConfigureAwait(false);
        if (sourceKey is not null)
        {
            rows = [.. rows.Where(row => row.Kind == sourceKey)];
        }

        var configured = _options.MediaManagerWebhookSecret;
        if (rows.Count == 0 && string.IsNullOrEmpty(configured))
        {
            throw new IntakeRefusedException(403, IntakeRules.NeedsSecretDetail);
        }

        if (provided.Length > 0)
        {
            if (rows.Any(row => _connections.WebhookSecretMatches(row, provided)))
            {
                return;
            }

            if (!string.IsNullOrEmpty(configured) && MediaManagerConnectionService.CompareDigest(provided, configured))
            {
                return;
            }
        }

        throw new IntakeRefusedException(401, IntakeRules.MissingSecretDetail);
    }

    /// <summary>Every library's id, media type and watched folder, in display order (<c>list_libraries</c>).</summary>
    public static Task<List<IntakeLibrary>> ListLibrariesAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QueryAsync(
            "SELECT id, media_type, watched_folder FROM refiner_libraries ORDER BY display_order, id",
            reader => new IntakeLibrary(SqliteValues.GetInt64(reader, 0), SqliteValues.GetString(reader, 1), SqliteValues.GetString(reader, 2)));
    }

    /// <summary><c>_library_for_handoff</c>: chosen by folder; nothing containing it explains against the scope's seeded library.</summary>
    public static async Task<(IntakeLibrary? Library, HandoffPathResult Resolved)> LibraryForHandoffAsync(UnitOfWork uow, MediaManagerImportEvent importEvent)
    {
        ArgumentNullException.ThrowIfNull(importEvent);
        var libraries = await ListLibrariesAsync(uow).ConfigureAwait(false);
        if (IntakeRules.ChooseLibrary(libraries, importEvent) is { } chosen)
        {
            return (chosen.Library, chosen.Resolved);
        }

        var scope = RefinerLibraryFolders.NormalizeMediaScope(importEvent.MediaScope);
        var fallback = libraries.FirstOrDefault(library => library.MediaType == scope);
        return (fallback, HandoffPaths.RelativeMediaPathForHandoff(fallback?.WatchedFolder ?? string.Empty, importEvent.FilePath));
    }

    /// <summary>
    /// <c>_handoff_media_files</c>: a file names itself; a folder means the videos inside it with samples left out.
    /// </summary>
    public static List<string> HandoffMediaFiles(IntakeLibrary? library, string relativePath)
    {
        if (library is null || relativePath.Length == 0)
        {
            return [relativePath];
        }

        var windows = OperatingSystem.IsWindows();
        var folder = Path.Join(library.WatchedFolder, relativePath);
        List<IReadOnlyList<string>> videos;
        try
        {
            if (!Directory.Exists(folder))
            {
                return [relativePath];
            }

            videos = [];
            foreach (var file in Directory.EnumerateFiles(folder, "*", new EnumerationOptions { RecurseSubdirectories = true, AttributesToSkip = 0, IgnoreInaccessible = true }))
            {
                if (IntakeRules.IsMediaCandidateName(Path.GetFileName(file)))
                {
                    videos.Add(Path.GetRelativePath(folder, file).Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
                }
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return [relativePath];
        }

        var chosen = IntakeRules.ChooseFolderVideos(videos, windows);
        if (chosen.Count == 0)
        {
            throw new IntakeRefusedException(400, IntakeRules.NoVideoInFolderDetail(relativePath));
        }

        var prefix = relativePath.Replace('\\', '/').TrimEnd('/');
        return [.. chosen.Select(parts => string.Join('/', new[] { prefix }.Concat(parts).Where(part => part.Length > 0 && part != ".")))];
    }

    /// <summary><c>_enqueue_refine</c>: the remux jobs for a hand-off, its ledger row, and (#531) the fingerprint of each file.</summary>
    public async Task<string> EnqueueRefineAsync(UnitOfWork uow, MediaManagerImportEvent importEvent)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(importEvent);
        var (library, resolved) = await LibraryForHandoffAsync(uow, importEvent).ConfigureAwait(false);
        if (!resolved.Ok)
        {
            throw new IntakeRefusedException(400, resolved.Problem!);
        }

        var relativePath = resolved.RelativeMediaPath!;
        var targets = HandoffMediaFiles(library, relativePath);
        var baseKey = IntakeRules.BaseDedupeKey(importEvent, NewGuid);
        foreach (var target in targets)
        {
            var dedupeKey = IntakeRules.DedupeKeyFor(baseKey, targets, target, relativePath);
            var payload = IntakeRules.PayloadJson(IntakeRules.Payload(importEvent, library, relativePath, target));
            _jobs.EnqueueOrGet(uow.Connection, uow.WriteTransaction(), dedupeKey, IntakeRules.RemuxPassJobKind, payload, JobQueueRules.DefaultMaxAttempts, 0, 0);
        }

        if (!string.IsNullOrEmpty(importEvent.HandoffId))
        {
            await _ledger.RecordReceivedAsync(uow, importEvent.SourceKey, importEvent.HandoffId, library?.Id, relativePath).ConfigureAwait(false);
        }

        if (library is not null)
        {
            foreach (var target in targets)
            {
                await RecordFingerprintAsync(uow, library, target).ConfigureAwait(false);
            }
        }

        return IntakeRules.RemuxPassJobKind;
    }

    /// <summary>
    /// Deliberate fix (#531): record a handed-over file's size when it arrives. Python first saw the size at the next
    /// watched-folder scan, which read the zero a failure had left on the row as a change and reset the failure count,
    /// so the retry limit and the hold after repeated failures never applied. A file that is missing, or a row that
    /// already has a size, is left alone; a later scan still sees a genuinely changed file as changed.
    /// </summary>
    private async Task RecordFingerprintAsync(UnitOfWork uow, IntakeLibrary library, string relativePath)
    {
        long size;
        try
        {
            var info = new FileInfo(Path.Join(library.WatchedFolder, relativePath));
            if (!info.Exists)
            {
                return;
            }

            size = info.Length;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return;
        }

        // No status reason: the queued job speaks for the file until a pass or scan records one, and a reason here
        // would change what the hand-off status tells the manager while the file waits.
        await uow.ExecuteAsync(
            "INSERT INTO refiner_files (library_id, relative_path, status, status_reason, size_bytes, last_seen_at) " +
            "VALUES ($library, $path, 'unprocessed', '', $size, $now) " +
            "ON CONFLICT (library_id, relative_path) DO UPDATE SET size_bytes = excluded.size_bytes, updated_at = CURRENT_TIMESTAMP " +
            "WHERE refiner_files.size_bytes = 0 AND excluded.size_bytes <> 0",
            ("$library", library.Id),
            ("$path", relativePath),
            ("$size", size),
            ("$now", PythonTimestamps.Orm(_time.GetUtcNow()))).ConfigureAwait(false);
    }
}
