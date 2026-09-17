using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>Activity writes for a Pass 4 failure-cleanup sweep (port of <c>refiner_failure_cleanup_activity.py</c>).</summary>
public static class RefinerFailureCleanupActivity
{
    private static string Label(string mediaScope) => mediaScope == "tv" ? "TV" : "Movies";

    private static PyDict WithOutcome(PyDict detail, string result, string? trigger)
    {
        var copy = detail.Copy();
        if (copy.Get("result") is null)
        {
            copy.Set("result", result);
        }

        if (trigger is not null && copy.Get("trigger") is null)
        {
            copy.Set("trigger", trigger);
        }

        return copy;
    }

    public static Task RecordSweepStartedAsync(UnitOfWork uow, string mediaScope, PyDict detail, string? trigger)
    {
        var withOutcome = WithOutcome(detail, "running", trigger);
        return SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
            ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "refiner",
            $"Refiner cleanup started for {Label(mediaScope)}",
            PyStrings.Slice(PyJsonWriter.Dumps(withOutcome, PyJsonFormat.Compact), 10_000)));
    }

    public static Task RecordSweepCompletedAsync(UnitOfWork uow, string mediaScope, PyDict detail, string? trigger)
    {
        var label = Label(mediaScope);
        var status = detail.Get("cleanup_run_status") is PyStr statusValue ? statusValue.Value : null;
        var (title, result) = status switch
        {
            "no_eligible_files" => ($"Refiner cleanup checked {label}: no changes needed", "success"),
            "skipped" => ($"Refiner cleanup skipped {label}", "skipped"),
            _ => ($"Refiner cleaned up after failed files ({label})", "success"),
        };
        var withOutcome = WithOutcome(detail, result, trigger);
        return SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
            ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "refiner", title,
            PyStrings.Slice(PyJsonWriter.Dumps(withOutcome, PyJsonFormat.Compact), 10_000)));
    }
}

/// <summary>
/// Refiner Pass 4: the periodic cleanup sweep for terminal failed remux jobs (port of <c>refiner_failure_cleanup.py</c>).
/// Deletes source (and, for Movies, output) folders left behind by a remux that used up its retries, once no media
/// manager still holds the file open. This sweep deletes folders, so an import check it could not make is a stop, not a
/// shrug: every manager covering the scope has to answer before anything is removed.
/// </summary>
/// <remarks>
/// The queue-block check (<c>HeldByManager</c>) uses <see cref="QueueRowAdapter"/>'s exact output-path match
/// only, matching Python's <c>_held_by_manager</c> — it does not (yet) fall back to the title/year anchor the watched-folder
/// scan port uses elsewhere, since that needs pieces the scan port (#522 part 5) has not landed yet.
/// </remarks>
public sealed class RefinerFailureCleanupSweep
{
    private readonly SqliteDatabase _database;
    private readonly WeirOptions _options;
    private readonly MediaManagerConnectionService _connections;
    private readonly TimeProvider _time;
    private readonly ILogger<RefinerFailureCleanupSweep> _logger;

    public RefinerFailureCleanupSweep(SqliteDatabase database, WeirOptions options, MediaManagerConnectionService connections, TimeProvider time, ILogger<RefinerFailureCleanupSweep> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <summary>Exposed so the job handler can write its started/completed Activity rows in their own short
    /// transactions, rather than holding one open across the sweep's filesystem work (deliberately unlike Python's
    /// single enclosing transaction — see the class remarks in <c>RemuxPassHandler</c> for why this codebase never
    /// holds a write transaction across slow I/O).</summary>
    public SqliteDatabase Database => _database;

    public Microsoft.Extensions.Logging.ILogger Logger => _logger;

    public async Task<PyDict> RunForScopeAsync(string mediaScope, CancellationToken cancellationToken)
    {
        var scope = mediaScope == "tv" ? "tv" : "movie";
        var now = _time.GetUtcNow();
        var grace = TimeSpan.FromSeconds(Math.Max(0, scope == "tv" ? _options.RefinerTvFailureCleanupGracePeriodSeconds : _options.RefinerMovieFailureCleanupGracePeriodSeconds));
        var olderThan = now - grace;

        return await LockedWrites.RunAsync(
            _database,
            uow => RunForScopeAsync(uow, scope, olderThan, cancellationToken),
            _logger,
            "failure cleanup sweep",
            cancellationToken).ConfigureAwait(false);
    }

    private async Task<PyDict> RunForScopeAsync(UnitOfWork uow, string scope, DateTimeOffset olderThan, CancellationToken cancellationToken)
    {
        var library = await RemuxPassHandler.ResolveLibraryAsync(uow, null, scope).ConfigureAwait(false);
        string watchedRaw = string.Empty, outputRaw = string.Empty, workRaw = string.Empty;
        if (library is not null)
        {
            watchedRaw = library.WatchedFolder;
            outputRaw = library.OutputFolder;
            var folderRow = new RefinerLibraryFolderRow(library.Id, library.MediaType, 0, library.WorkFolder, library.OutputFolder);
            workRaw = RefinerLibraryFolders.EffectiveWorkFolder(folderRow, _options.WeirHome);
        }

        var workRoot = RemuxPassPaths.Resolve(workRaw.Length == 0 ? "." : workRaw);
        var outResult = new PyDict()
            .Set("media_scope", scope)
            .Set("cleanup_run_status", "started")
            .Set("grace_period_seconds", (long)Math.Max(0, scope == "tv" ? _options.RefinerTvFailureCleanupGracePeriodSeconds : _options.RefinerMovieFailureCleanupGracePeriodSeconds))
            .Set("eligible_failed_jobs", 0L)
            .Set("processed_failed_jobs", 0L)
            .Set("skip_reason", (string?)null)
            .Set("jobs", new PyList());

        if (PyStrings.Strip(watchedRaw).Length == 0 || PyStrings.Strip(outputRaw).Length == 0)
        {
            outResult.Set("cleanup_run_status", "skipped");
            outResult.Set("skip_reason", "Saved watched/output paths are not configured for this scope, so failure cleanup was skipped safely.");
            return outResult;
        }

        var watchedRoot = RemuxPassPaths.Resolve(watchedRaw);
        var outputRoot = RemuxPassPaths.Resolve(outputRaw);
        var failedRows = await FailedJobsForScopeAsync(uow, scope, olderThan).ConfigureAwait(false);
        outResult.Set("eligible_failed_jobs", (long)failedRows.Count);
        if (failedRows.Count == 0)
        {
            outResult.Set("cleanup_run_status", "no_eligible_files");
            outResult.Set("skip_reason", "No eligible failed Refiner jobs were old enough for cleanup.");
            return outResult;
        }

        var signals = await _connections.CollectQueueSignalsAsync(uow, scope, cancellationToken: cancellationToken).ConfigureAwait(false);
        var report = ReportForSignals(signals);
        string? queueUnreachable = null;
        if (report.Consulted == 0)
        {
            var scopeWord = scope == "tv" ? "TV episodes" : "Movies";
            queueUnreachable = $"No media manager is connected for {scopeWord}.";
        }
        else if (!report.AllReported)
        {
            queueUnreachable = report.SilentDetails[0];
        }

        var jobsList = new PyList();
        var processed = 0L;
        foreach (var (jobId, relNorm, legacyDryRun) in failedRows)
        {
            var detail = new PyDict()
                .Set("job_id", jobId)
                .Set("relative_media_path", relNorm)
                .Set($"{scope}_failure_cleanup_ran", false)
                .Set($"{scope}_failure_cleanup_skip_reason", (string?)null)
                .Set($"{scope}_failure_cleanup_dry_run", legacyDryRun)
                .Set($"{scope}_failure_cleanup_queue_check", "skipped")
                .Set($"{scope}_failure_cleanup_temp_files_deleted", new PyList())
                .Set($"{scope}_failure_cleanup_cascade_folders_deleted", new PyList());
            processed++;
            jobsList.Items.Add(detail);

            if (legacyDryRun)
            {
                detail.Set(
                    $"{scope}_failure_cleanup_skip_reason",
                    "Skipped for compatibility: this failed remux row uses legacy dry_run payload format, which is not a current Refiner mode.");
                continue;
            }

            if (queueUnreachable is not null)
            {
                detail.Set($"{scope}_failure_cleanup_skip_reason", $"Weir could not check whether anything is still importing, so nothing was removed. {queueUnreachable}");
                continue;
            }

            var srcFile = RemuxPassPaths.Resolve(Path.Combine(watchedRoot, relNorm));
            var srcFolder = Path.GetDirectoryName(srcFile) ?? watchedRoot;

            if (scope == "movie")
            {
                ProcessMovie(detail, srcFile, srcFolder, relNorm, watchedRoot, outputRoot, workRoot, signals);
            }
            else
            {
                await ProcessTvAsync(uow, detail, srcFolder, relNorm, watchedRoot, outputRoot, workRoot, signals).ConfigureAwait(false);
            }
        }

        outResult.Set("processed_failed_jobs", processed);
        outResult.Set("jobs", jobsList);
        outResult.Set("cleanup_run_status", "completed");
        return outResult;
    }

    private void ProcessMovie(
        PyDict detail, string srcFile, string srcFolder, string relNorm, string watchedRoot, string outputRoot, string workRoot,
        IReadOnlyList<ManagerQueueSignal> signals)
    {
        detail.Set("movie_failure_cleanup_source_folder_deleted", false);
        detail.Set("movie_failure_cleanup_source_folder_path", srcFolder);
        detail.Set("movie_failure_cleanup_output_folder_deleted", false);
        var outFolder = Path.GetDirectoryName(RemuxPassPaths.Resolve(Path.Combine(outputRoot, relNorm))) ?? outputRoot;
        detail.Set("movie_failure_cleanup_output_folder_path", outFolder);

        var holder = HeldByManager(signals, "movie", srcFile);
        if (holder is not null)
        {
            detail.Set("movie_failure_cleanup_queue_check", "blocked_in_queue");
            detail.Set("movie_failure_cleanup_skip_reason", $"{holder} is still importing this file, so failure cleanup skipped.");
            return;
        }

        detail.Set("movie_failure_cleanup_queue_check", "passed_not_in_queue");
        detail.Set("movie_failure_cleanup_ran", true);

        if (RemuxPassPaths.RelativeTo(srcFolder, watchedRoot) is not null && !RemuxPassPaths.SamePath(srcFolder, watchedRoot) && Directory.Exists(srcFolder))
        {
            var (ok, _) = SafeRmTree(srcFolder);
            detail.Set("movie_failure_cleanup_source_folder_deleted", ok);
            if (ok)
            {
                CascadeUnderRoot(Path.GetDirectoryName(srcFolder) ?? watchedRoot, watchedRoot, (PyList)detail.Get("movie_failure_cleanup_cascade_folders_deleted")!);
            }
        }

        if (RemuxPassPaths.RelativeTo(outFolder, outputRoot) is not null && !RemuxPassPaths.SamePath(outFolder, outputRoot) && Directory.Exists(outFolder))
        {
            var (ok, _) = SafeRmTree(outFolder);
            detail.Set("movie_failure_cleanup_output_folder_deleted", ok);
            if (ok)
            {
                CascadeUnderRoot(Path.GetDirectoryName(outFolder) ?? outputRoot, outputRoot, (PyList)detail.Get("movie_failure_cleanup_cascade_folders_deleted")!);
            }
        }

        var tempDeleted = (PyList)detail.Get("movie_failure_cleanup_temp_files_deleted")!;
        foreach (var temp in JobTempCandidates(workRoot, relNorm))
        {
            var (ok, _) = SafeUnlink(temp);
            if (ok)
            {
                tempDeleted.Items.Add(new PyStr(temp));
            }
        }
    }

    private async Task ProcessTvAsync(
        UnitOfWork uow, PyDict detail, string srcSeason, string relNorm, string watchedRoot, string outputRoot, string workRoot,
        IReadOnlyList<ManagerQueueSignal> signals)
    {
        detail.Set("tv_failure_cleanup_season_folder_deleted", false);
        detail.Set("tv_failure_cleanup_output_season_deleted", false);
        detail.Set("tv_failure_cleanup_season_folder_path", srcSeason);
        var relDirectory = Path.GetDirectoryName(relNorm.Replace('/', Path.DirectorySeparatorChar)) ?? string.Empty;
        var outSeason = RemuxPassPaths.Resolve(relDirectory.Length == 0 ? outputRoot : Path.Combine(outputRoot, relDirectory));
        detail.Set("tv_failure_cleanup_output_season_path", outSeason);

        var episodes = new List<string>();
        if (Directory.Exists(srcSeason))
        {
            try
            {
                episodes = [.. Directory.EnumerateFiles(srcSeason)
                    .Where(IntakeRules.IsMediaCandidateName)
                    .OrderBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase)];
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                episodes = [];
            }
        }

        if (episodes.Count == 0)
        {
            detail.Set("tv_failure_cleanup_skip_reason", "No direct-child episode media files were found in this season folder, so Refiner skipped season cleanup.");
            return;
        }

        var blocked = false;
        foreach (var episode in episodes)
        {
            if (HeldByManager(signals, "tv", episode) is not null)
            {
                blocked = true;
                break;
            }

            var rel = RemuxPassPaths.RelativeTo(episode, watchedRoot);
            if (rel is null)
            {
                _logger.LogWarning("Refiner TV failure cleanup skipped episode outside watched root path={Path}", episode);
                continue;
            }

            var relPosix = RemuxPassPaths.Posix(rel);
            if (await ActiveRemuxPassExistsAsync(uow, relPosix, "tv").ConfigureAwait(false))
            {
                blocked = true;
                break;
            }

            if (!await TvHasTerminalFailedRemuxAsync(uow, relPosix).ConfigureAwait(false))
            {
                blocked = true;
                break;
            }
        }

        if (blocked)
        {
            detail.Set("tv_failure_cleanup_queue_check", "blocked_in_queue_or_active_job");
            detail.Set(
                "tv_failure_cleanup_skip_reason",
                "TV season is not clear yet (episode still queued, active TV remux exists, or not every direct-child episode has a terminal failed TV remux outcome), so cleanup skipped.");
            return;
        }

        detail.Set("tv_failure_cleanup_queue_check", "passed_not_in_queue");
        detail.Set("tv_failure_cleanup_ran", true);

        if (RemuxPassPaths.RelativeTo(srcSeason, watchedRoot) is not null && !RemuxPassPaths.SamePath(srcSeason, watchedRoot) && Directory.Exists(srcSeason))
        {
            var (ok, _) = SafeRmTree(srcSeason);
            detail.Set("tv_failure_cleanup_season_folder_deleted", ok);
            if (ok)
            {
                CascadeUnderRoot(Path.GetDirectoryName(srcSeason) ?? watchedRoot, watchedRoot, (PyList)detail.Get("tv_failure_cleanup_cascade_folders_deleted")!);
            }
        }

        if (RemuxPassPaths.RelativeTo(outSeason, outputRoot) is not null && !RemuxPassPaths.SamePath(outSeason, outputRoot) && Directory.Exists(outSeason))
        {
            var (ok, _) = SafeRmTree(outSeason);
            detail.Set("tv_failure_cleanup_output_season_deleted", ok);
            if (ok)
            {
                CascadeUnderRoot(Path.GetDirectoryName(outSeason) ?? outputRoot, outputRoot, (PyList)detail.Get("tv_failure_cleanup_cascade_folders_deleted")!);
            }
        }

        var tempDeleted = (PyList)detail.Get("tv_failure_cleanup_temp_files_deleted")!;
        foreach (var temp in JobTempCandidates(workRoot, relNorm))
        {
            var (ok, _) = SafeUnlink(temp);
            if (ok)
            {
                tempDeleted.Items.Add(new PyStr(temp));
            }
        }
    }

    /// <summary><c>_held_by_manager</c>: the connection whose queue still names this exact file, or null. Path equality only.</summary>
    private static string? HeldByManager(IReadOnlyList<ManagerQueueSignal> signals, string mediaScope, string mediaFile)
    {
        var dialect = QueueRowAdapter.ForScope(mediaScope);
        var candidatePath = RemuxPassPaths.Resolve(mediaFile);
        foreach (var signal in signals)
        {
            if (!signal.IsReported)
            {
                continue;
            }

            foreach (var row in signal.Rows)
            {
                if (row.Scope != mediaScope)
                {
                    continue;
                }

                if (QueueRowAdapter.MapToView(row.Payload, dialect, candidatePath).AppliesToFile)
                {
                    return signal.Connection.Label;
                }
            }
        }

        return null;
    }

    private sealed record SignalReport(int Consulted, bool AllReported, IReadOnlyList<string> SilentDetails);

    /// <summary><c>report_for_signals</c>.</summary>
    private static SignalReport ReportForSignals(IReadOnlyList<ManagerQueueSignal> signals)
    {
        var silentDetails = new List<string>();
        foreach (var signal in signals)
        {
            if (signal.IsReported)
            {
                continue;
            }

            silentDetails.Add(signal.Detail ?? $"{signal.Connection.Label} did not answer.");
        }

        return new SignalReport(signals.Count, silentDetails.Count == 0, silentDetails);
    }

    private async Task<List<(long JobId, string Rel, bool LegacyDryRun)>> FailedJobsForScopeAsync(UnitOfWork uow, string mediaScope, DateTimeOffset olderThan)
    {
        var rows = await uow.QueryAsync(
            "SELECT id, payload_json, updated_at FROM refiner_jobs WHERE job_kind = $kind AND status = $status",
            reader => (Id: reader.GetInt64(0), Payload: reader.IsDBNull(1) ? null : reader.GetString(1), UpdatedAt: reader.IsDBNull(2) ? null : reader.GetValue(2)),
            ("$kind", RemuxPassOutcomes.JobKind),
            ("$status", RefinerJobStatus.Failed)).ConfigureAwait(false);

        var result = new List<(long, string, bool)>();
        foreach (var row in rows)
        {
            var updatedAt = PythonTimestamps.Parse(row.UpdatedAt) ?? DateTimeOffset.MinValue;
            if (updatedAt >= olderThan)
            {
                continue;
            }

            (string Rel, string Scope, bool LegacyDryRun)? parsed;
            try
            {
                parsed = ParseFailedJobPayload(row.Payload);
            }
            catch (Exception exception) when (exception is FormatException or PyJsonDecodeException)
            {
                _logger.LogDebug(exception, "Refiner failure cleanup ignored malformed failed-job payload job_id={JobId}", row.Id);
                continue;
            }

            if (parsed.Value.Scope != mediaScope)
            {
                continue;
            }

            result.Add((row.Id, parsed.Value.Rel, parsed.Value.LegacyDryRun));
        }

        return result;
    }

    private static async Task<bool> TvHasTerminalFailedRemuxAsync(UnitOfWork uow, string relativePosix)
    {
        var want = NormRel(relativePosix);
        var rows = await uow.QueryAsync(
            "SELECT payload_json FROM refiner_jobs WHERE job_kind = $kind AND status = $status",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("$kind", RemuxPassOutcomes.JobKind),
            ("$status", RefinerJobStatus.Failed)).ConfigureAwait(false);
        foreach (var payload in rows)
        {
            (string Rel, string Scope, bool LegacyDryRun)? parsed;
            try
            {
                parsed = ParseFailedJobPayload(payload);
            }
            catch (Exception exception) when (exception is FormatException or PyJsonDecodeException)
            {
                continue;
            }

            if (parsed.Value.Scope == "tv" && parsed.Value.Rel == want)
            {
                return true;
            }
        }

        return false;
    }

    private static async Task<bool> ActiveRemuxPassExistsAsync(UnitOfWork uow, string relativePosix, string mediaScope)
    {
        var wantScope = mediaScope is "movie" or "tv" ? mediaScope : "movie";
        var rows = await uow.QueryAsync(
            "SELECT payload_json FROM refiner_jobs WHERE job_kind = $kind AND status IN ($pending, $leased)",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("$kind", RemuxPassOutcomes.JobKind),
            ("$pending", RefinerJobStatus.Pending),
            ("$leased", RefinerJobStatus.Leased)).ConfigureAwait(false);
        foreach (var payload in rows)
        {
            var raw = PyStrings.Strip(payload ?? string.Empty);
            if (raw.Length == 0)
            {
                continue;
            }

            PyJson parsedJson;
            try
            {
                parsedJson = PyJsonParser.Parse(raw);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (parsedJson is not PyDict data)
            {
                continue;
            }

            var rel = data.Get("relative_media_path") is PyStr relStr ? relStr.Value : null;
            var jobScope = data.Get("media_scope") is PyStr scopeStr && scopeStr.Value is "movie" or "tv" ? scopeStr.Value : "movie";
            if (rel is not null && PyStrings.Strip(rel) == relativePosix && jobScope == wantScope)
            {
                return true;
            }
        }

        return false;
    }

    private static (string Rel, string Scope, bool LegacyDryRun) ParseFailedJobPayload(string? payloadJson)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            throw new FormatException("missing payload_json");
        }

        if (PyJsonParser.Parse(payloadJson) is not PyDict data)
        {
            throw new FormatException("payload_json must be object");
        }

        if (data.Get("relative_media_path") is not PyStr relStr || PyStrings.Strip(relStr.Value).Length == 0)
        {
            throw new FormatException("payload missing relative_media_path");
        }

        var scope = data.Get("media_scope") is PyStr scopeStr && string.Equals(PyStrings.Strip(scopeStr.Value), "tv", StringComparison.OrdinalIgnoreCase)
            ? "tv"
            : "movie";
        var legacyDryRun = data.Get("dry_run") is { IsTruthy: true };
        return (NormRel(relStr.Value), scope, legacyDryRun);
    }

    /// <summary><c>_norm_rel</c>.</summary>
    private static string NormRel(string raw)
    {
        var trimmed = PyStrings.Strip(raw).Replace('\\', '/');
        var parts = trimmed.Split('/').Where(part => part.Length > 0 && part != ".").ToArray();
        return parts.Length == 0 ? string.Empty : string.Join('/', parts);
    }

    /// <summary><c>_job_temp_candidates</c>.</summary>
    private static List<string> JobTempCandidates(string workRoot, string relNorm)
    {
        var result = new List<string>();
        if (!Directory.Exists(workRoot))
        {
            return result;
        }

        var stem = Path.GetFileNameWithoutExtension(relNorm).ToLowerInvariant();
        List<string> files;
        try
        {
            files = [.. Directory.EnumerateFiles(workRoot)];
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return result;
        }

        foreach (var child in files.OrderBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase))
        {
            var name = Path.GetFileName(child).ToLowerInvariant();
            if (!name.Contains(".refiner.", StringComparison.Ordinal))
            {
                continue;
            }

            if (stem.Length > 0 && name.Contains(stem, StringComparison.Ordinal))
            {
                result.Add(child);
            }
        }

        return result;
    }

    /// <summary><c>_cascade_under_root</c>: remove now-empty ancestor folders, up to (not including) the root.</summary>
    private static void CascadeUnderRoot(string firstParent, string root, PyList deletedOut)
    {
        var current = RemuxPassPaths.Resolve(firstParent);
        var rr = RemuxPassPaths.Resolve(root);
        while (!RemuxPassPaths.SamePath(current, rr))
        {
            if (RemuxPassPaths.RelativeTo(current, rr) is null || !Directory.Exists(current))
            {
                break;
            }

            try
            {
                if (Directory.EnumerateFileSystemEntries(current).Any())
                {
                    break;
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                break;
            }

            try
            {
                Directory.Delete(current);
                deletedOut.Items.Add(new PyStr(current));
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                break;
            }

            var parent = Path.GetDirectoryName(current);
            if (parent is null)
            {
                break;
            }

            current = parent;
        }
    }

    private (bool Ok, string? Error) SafeRmTree(string path)
    {
        try
        {
            Directory.Delete(path, recursive: true);
            return (true, null);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            var message = $"Could not remove {path} because it is in use or blocked ({exception.Message}).";
            _logger.LogWarning("Refiner failure cleanup: {Message}", message);
            return (false, message);
        }
    }

    private (bool Ok, string? Error) SafeUnlink(string path)
    {
        try
        {
            File.Delete(path);
            return (true, null);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            var message = $"Could not remove temp file {path} because it is in use or blocked ({exception.Message}).";
            _logger.LogWarning("Refiner failure cleanup: {Message}", message);
            return (false, message);
        }
    }
}
