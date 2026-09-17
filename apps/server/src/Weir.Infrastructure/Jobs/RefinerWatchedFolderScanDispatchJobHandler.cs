using System.Globalization;
using Weir.Core.Activity;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Settings;
using Weir.Core.Time;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Settings;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// In-process worker handler for <c>refiner.watched_folder.remux_scan_dispatch.v1</c> (port of
/// <c>refiner_watched_folder_remux_scan_dispatch_handlers.py</c>'s <c>_run</c>): scan the library's watched
/// folder, decide each candidate file's state, and — when asked — enqueue
/// <c>refiner.file.remux_pass.v1</c> jobs for it with payload JSON and dedupe keys identical to Python's.
/// </summary>
/// <remarks>
/// Per-file attribution to a specific media-manager queue row (path/id/title-year matching a manager's
/// raw JSON to a candidate) is <see cref="ManagerQueueSignals.AttributedRowsForFile"/>, applied through
/// <see cref="WatchedFileDispatch"/> exactly as the "why held" diagnostic applies it.
/// </remarks>
public sealed class RefinerWatchedFolderScanDispatchJobHandler : IJobHandler
{
    private readonly SqliteDatabase _database;
    private readonly TimeProvider _time;
    private readonly WeirOptions _options;
    private readonly RefinerJobStore _jobStore;
    private readonly MediaManagerConnectionService _managerConnections;

    public RefinerWatchedFolderScanDispatchJobHandler(
        SqliteDatabase database, TimeProvider time, WeirOptions options, RefinerJobStore jobStore, MediaManagerConnectionService managerConnections)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _jobStore = jobStore ?? throw new ArgumentNullException(nameof(jobStore));
        _managerConnections = managerConnections ?? throw new ArgumentNullException(nameof(managerConnections));
    }

    public string JobKind => RefinerWatchedFolderScanDispatchJobKinds.ScanDispatch;

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var body = ParsePayload(context.PayloadJson);
        var enqueueRemuxJobs = body.Get("enqueue_remux_jobs") is PyJson v && v.IsTruthy;
        var scanTriggerRaw = body.Get("scan_trigger") is PyStr triggerStr ? triggerStr.Value : "manual";
        var scanTrigger = ScanDispatchJobPayload.NormalizeTrigger(scanTriggerRaw);
        var mediaScope = RefinerMediaScopes.Normalize(body.Get("media_scope") is PyStr scopeStr ? scopeStr.Value : null);
        var libraryId = body.Get("library_id") is PyInt idValue && idValue.Value > 0 ? (long)idValue.Value : (long?)null;

        var now = _time.GetUtcNow();

        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);

        var library = libraryId is { } wantedId ? await LibraryStore.GetAsync(uow, wantedId).ConfigureAwait(false) : null;
        library ??= await LibraryStore.SeededForScopeAsync(uow, mediaScope).ConfigureAwait(false);
        if (library is null)
        {
            var label = mediaScope == RefinerMediaScopes.Tv ? "TV" : "Movies";
            throw new InvalidOperationException($"No library covers {label}. Add one in Processing → Libraries, then queue this work again.");
        }

        var (runtime, pathError) = WatchedFolderScanOps.ResolvePathRuntimeForLibrary(library, _options.WeirHome);
        if (runtime is null)
        {
            throw new InvalidOperationException(pathError ?? "Path settings are incomplete for this scan.");
        }

        // Manager queue signals: ask every manager linked to this library, and note who did not answer.
        // Always the library's own linked connections (even when that is none): Python passes
        // manager_connection_ids_for(...) — an empty tuple, not None, when the library links nothing —
        // and an empty selector must mean "ask nobody", not "fall back to every connection for the scope".
        var connectionIds = await LibraryStore.ManagerConnectionIdsAsync(uow, library.Id).ConfigureAwait(false);
        var signals = await _managerConnections.CollectQueueSignalsAsync(uow, mediaScope, connectionIds, cancellationToken).ConfigureAwait(false);

        var operatorSettings = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var suite = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var pause = PauseState.Resolve(suite, now.UtcDateTime);
        var timezoneName = string.IsNullOrWhiteSpace(suite.AppTimezone) ? "UTC" : suite.AppTimezone.Trim();
        var pauseReason = pause.Paused ? pause.Reason : null;
        var pauseUntil = pause.Paused && pause.PausedUntil is { } pu ? new DateTimeOffset(pu.AsUtc) : (DateTimeOffset?)null;

        var admissionSnapshot = new LibraryAdmissionSnapshot(
            library.Id, library.Enabled, library.ScheduleEnabled, library.ScheduleGrid, library.ScheduleHoursLimited,
            library.ScheduleDays, library.ScheduleStart, library.ScheduleEnd, library.MaxConcurrentFiles);
        var inWindow = WorkAdmissionRules.LibraryWindowOpen(admissionSnapshot, timezoneName, now);
        var reopensAt = inWindow ? null : WorkAdmissionRules.LibraryWindowReopensAt(admissionSnapshot, timezoneName, now);

        var rules = LibraryAdmissionRules.For(library);
        var effectiveMinAgeSeconds = Math.Max(operatorSettings.MinFileAgeSeconds, rules.MinFileAgeSeconds);

        var candidates = WatchedFolderScanOps.IterWatchedFolderMediaCandidates(
            runtime.WatchedFolder,
            rules.MediaExtensions.Count > 0 ? rules.MediaExtensions : null,
            rules.ExcludeMarkers,
            rules.ExcludeHidden,
            rules.TopLevelOnly);

        var relThisRun = new HashSet<string>(StringComparer.Ordinal);
        var pendingRejectedCleanups = new List<(string RelativePath, string FilePath, string Reason, string Action)>();

        foreach (var filePath in candidates.Files)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!File.Exists(filePath))
            {
                // A successful Movies cleanup can remove a release folder while this scan still holds a
                // candidate for one of its extras. Do not turn a stale entry into new state or a job.
                continue;
            }

            var rel = WatchedFolderScanOps.RelativePosixPathUnderWatched(runtime.WatchedFolder, filePath);
            // `evaluate_watched_media_file_for_dispatch`: the candidate anchor is this file's own stem
            // (not the library's name), so anchor matching only ever compares one release title to another.
            var candidate = new FileAnchorCandidate(Path.GetFileNameWithoutExtension(filePath));
            var attributedRows = ManagerQueueSignals.AttributedRowsForFile(signals, mediaScope, Path.GetFullPath(filePath));
            var outcome = WatchedFileDispatch.Evaluate(attributedRows, candidate);

            var observedSize = FileSizeBytes(filePath);
            var previous = await FileStateStore.ExistingFileRowAsync(uow, library.Id, rel).ConfigureAwait(false);

            if (previous is not null && previous.SizeBytes != observedSize)
            {
                // A changed source is a new processing opportunity: do not carry a failure/quarantine
                // counter from the old bytes into the new file. Applied on the next record_file_state.
                previous = previous with
                {
                    FailureClass = null,
                    FailureAttempts = 0,
                    NextRetryAt = null,
                    Status = previous.Status is RefinerFileStatuses.ProcessingFailed or RefinerFileStatuses.OnHold
                        or RefinerFileStatuses.PassedThrough or RefinerFileStatuses.Rejected
                        ? RefinerFileStatuses.Unprocessed
                        : previous.Status,
                };
                await ResetFailureBookkeepingAsync(uow, previous).ConfigureAwait(false);
            }

            if (previous is not null && previous.SizeBytes == observedSize)
            {
                if (previous.Status is RefinerFileStatuses.PassedThrough or RefinerFileStatuses.Rejected)
                {
                    await uow.ExecuteAsync(
                        "UPDATE refiner_files SET last_seen_at = @seen WHERE id = @id",
                        ("@seen", SqliteValues.ToSqlite(PyDateTime.FromDateTimeOffset(now))), ("@id", previous.Id)).ConfigureAwait(false);
                    continue;
                }

                if (previous.Status == RefinerFileStatuses.ProcessingFailed)
                {
                    var retryAt = previous.NextRetryAt?.AsUtc;
                    if (retryAt is { } r && r <= now.UtcDateTime)
                    {
                        // Automatic retry: enqueue the same way a fresh candidate would, not through
                        // RequeueStore — that store's reset (failure_attempts back to 0, backoff cleared)
                        // is deliberately for a human's "retry now"; RequeueStore's own docs say the
                        // automatic, policy-governed half belongs to record_failure/RetryPolicy alone. Using
                        // it here wiped the counter every scan cycle, so a file could never accumulate
                        // enough consecutive failures to quarantine — RecordFailureAsync (run when the new
                        // attempt's own outcome comes back) is the only thing that should touch these fields.
                        // Same cross-connection deadlock hazard as the fresh-candidate path below: release
                        // uow's write lock before RefinerJobStore opens its own connection.
                        await uow.CommitAsync().ConfigureAwait(false);
                        await EnqueueRemuxPassAsync(uow, context, library, mediaScope, rel, scanTrigger, previous).ConfigureAwait(false);
                        continue;
                    }

                    await uow.ExecuteAsync(
                        "UPDATE refiner_files SET last_seen_at = @seen WHERE id = @id",
                        ("@seen", SqliteValues.ToSqlite(PyDateTime.FromDateTimeOffset(now))), ("@id", previous.Id)).ConfigureAwait(false);
                    continue;
                }

                if (previous.Status == RefinerFileStatuses.OnHold && previous.FailureAttempts >= 3)
                {
                    await uow.ExecuteAsync(
                        "UPDATE refiner_files SET last_seen_at = @seen WHERE id = @id",
                        ("@seen", SqliteValues.ToSqlite(PyDateTime.FromDateTimeOffset(now))), ("@id", previous.Id)).ConfigureAwait(false);
                    continue;
                }
            }

            var settling = FileSettling.ObserveSizeSettling(
                library,
                previous?.SizeBytes,
                previous?.SizeChangedAt?.AsUtc,
                observedSize,
                now);

            var access = settling.IsSettling
                ? (Ok: true, Problem: (string?)null)
                : WatchedFolderScanOps.CheckFileAccess(library.SkipAccessTests, filePath, runtime.OutputFolder);

            var verdict = FileStateDecision.DecideFileState(
                library,
                inWindow,
                FileAgeSeconds(filePath, now),
                pauseReason,
                pauseUntil,
                reopensAt,
                settling.IsSettling,
                settling.Reason,
                settling.StableAt,
                access.Problem,
                outcome.BlockedConnection,
                effectiveMinAgeSeconds,
                now);

            await FileStateStore.RecordFileStateAsync(
                uow, library.Id, rel, verdict, observedSize, settling.SizeChangedAt, now).ConfigureAwait(false);

            var cleanupRetryReady = !settling.IsSettling && access.Problem is null;
            var noActivePass = !await WatchedFolderScanOps.ActiveRemuxPassExistsForRelativePathAsync(uow, rel, mediaScope, library.Id).ConfigureAwait(false);
            if (mediaScope == RefinerMediaScopes.Movie && cleanupRetryReady && noActivePass &&
                await WatchedFolderScanOps.CompletedRemuxOutputExistsForRelativePathAsync(uow, rel, mediaScope, library.Id, runtime.OutputFolder, filePath).ConfigureAwait(false))
            {
                await RetryCompletedMovieCleanupAsync(uow, library.Id, runtime.WatchedFolder, filePath, rel, observedSize, settling, now).ConfigureAwait(false);
                continue;
            }

            if (!verdict.Eligible)
            {
                continue;
            }

            var facts = new CandidateFileFacts(observedSize, CreatedAtUtc(filePath), ModifiedAtUtc(filePath));
            var rejection = LibraryAdmission.Rejection(rel, Path.GetFileName(filePath), facts, rules);
            if (rejection is not null)
            {
                var reason = rejection.Reason;
                if (rules.RejectedFileAction == "delete_file")
                {
                    pendingRejectedCleanups.Add((rel, filePath, reason, rules.RejectedFileAction));
                    reason = $"{reason} This library is set to delete rejected files; Weir will record this decision before removing only this file.";
                }

                await FileStateStore.RecordFileStateAsync(
                    uow, library.Id, rel, new FileStateVerdict(RefinerFileStatuses.Skipped, reason), observedSize, settling.SizeChangedAt, now).ConfigureAwait(false);
                continue;
            }

            if (outcome.Verdict != WatchedFileDispatchOutcome.Proceed || !enqueueRemuxJobs)
            {
                continue;
            }

            if (!relThisRun.Add(rel))
            {
                continue;
            }

            if (await WatchedFolderScanOps.ActiveRemuxPassExistsForRelativePathAsync(uow, rel, mediaScope, library.Id).ConfigureAwait(false))
            {
                continue;
            }

            if (await WatchedFolderScanOps.CompletedRemuxOutputExistsForRelativePathAsync(uow, rel, mediaScope, library.Id, runtime.OutputFolder, filePath).ConfigureAwait(false))
            {
                if (mediaScope == RefinerMediaScopes.Movie)
                {
                    WatchedFolderScanOps.RetryCompletedMovieSourceCleanup(runtime.WatchedFolder, filePath);
                }

                continue;
            }

            // Same cross-connection deadlock hazard as the automatic-retry path above: release uow's
            // write lock before RefinerJobStore opens its own connection to insert the remux-pass row.
            await uow.CommitAsync().ConfigureAwait(false);
            await EnqueueRemuxPassAsync(uow, context, library, mediaScope, rel, scanTrigger, previous).ConfigureAwait(false);
        }

        await uow.CommitAsync().ConfigureAwait(false);

        // The SKIPPED decision above committed before this mutation. If the process stops between the
        // two, the source remains and the next scan safely retries.
        foreach (var (relativePath, filePath, reason, action) in pendingRejectedCleanups)
        {
            var (deleted, detail) = WatchedFolderScanOps.CleanupRejectedFile(runtime.WatchedFolder, filePath, action);
            _ = deleted;
            await using var cleanupUow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
            await FileStateStore.MarkFileStatusAsync(cleanupUow, library.Id, relativePath, RefinerFileStatuses.Skipped, $"{reason} {detail}").ConfigureAwait(false);
            await cleanupUow.CommitAsync().ConfigureAwait(false);
        }
    }

    private static async Task ResetFailureBookkeepingAsync(UnitOfWork uow, RefinerFileRecord previous)
    {
        await uow.ExecuteAsync(
            "UPDATE refiner_files SET failure_class = NULL, failure_attempts = 0, next_retry_at = NULL, status = @status WHERE id = @id",
            ("@status", previous.Status), ("@id", previous.Id)).ConfigureAwait(false);
    }

    private static async Task RetryCompletedMovieCleanupAsync(
        UnitOfWork uow, long libraryId, string watchedRoot, string filePath, string rel, long observedSize, SettlingObservation settling, DateTimeOffset now)
    {
        var (cleanupOk, cleanupReason) = WatchedFolderScanOps.RetryCompletedMovieSourceCleanup(watchedRoot, filePath);
        if (cleanupOk)
        {
            var releaseParent = PosixParent(rel);
            var siblings = await uow.QueryAsync(
                "SELECT id, relative_path FROM refiner_files WHERE library_id = @lib",
                reader => (Id: reader.GetInt64(0), RelativePath: reader.GetString(1)),
                ("@lib", libraryId)).ConfigureAwait(false);
            foreach (var (id, siblingPath) in siblings)
            {
                if (PosixParent(siblingPath) != releaseParent)
                {
                    continue;
                }

                await uow.ExecuteAsync(
                    "UPDATE refiner_files SET status = @status, status_reason = @reason, blocked_by_connection = NULL, hold_until = NULL WHERE id = @id",
                    ("@status", RefinerFileStatuses.Processed),
                    ("@reason", "Weir removed this file with its release folder after the validated movie output completed. No separate output was created for this extra file."),
                    ("@id", id)).ConfigureAwait(false);
            }

            await FileStateStore.RecordFileStateAsync(
                uow, libraryId, rel,
                new FileStateVerdict(RefinerFileStatuses.Processed, "The output was already complete. The temporary lock cleared, so Weir finished removing the source release folder."),
                observedSize, settling.SizeChangedAt, now).ConfigureAwait(false);
        }
        else
        {
            var retryReason = cleanupReason ?? "The source release folder is still locked.";
            await FileStateStore.RecordFileStateAsync(
                uow, libraryId, rel,
                new FileStateVerdict(RefinerFileStatuses.OnHold, $"The output is complete, but source cleanup is waiting: {retryReason} Weir will try again automatically."),
                observedSize, settling.SizeChangedAt, now).ConfigureAwait(false);
        }
    }

    private async Task EnqueueRemuxPassAsync(
        UnitOfWork uow, JobWorkContext context, RefinerLibraryRecord library, string mediaScope, string rel, string scanTrigger, RefinerFileRecord? previousRow)
    {
        var payload = new PyDict()
            .Set("relative_media_path", rel)
            .Set("media_scope", mediaScope)
            .Set("trigger", ActivityProvenance.ScanTriggerToTrigger.GetValueOrDefault(scanTrigger, "manual"))
            .Set("run_id", $"scan-{context.Id.ToString(CultureInfo.InvariantCulture)}")
            .Set("library_id", library.Id);
        // Deliberate fix (#531 item 2): a scan-driven retry (this is also how a failed hand-off's file gets
        // requeued automatically, not just a fresh candidate) keeps the hand-off's origin, so a pass-through
        // or reject reached after such a retry still has an output path to report and a callback to send —
        // same fix as RequeueStore.RequeueFileAsync's manual half.
        if (await HandoffOriginCarry.FindAsync(uow, library.Id, rel).ConfigureAwait(false) is { } origin)
        {
            payload.Set("origin", origin);
        }

        var dedupe = $"{RequeueStore.RemuxPassJobKind}:scan:{Guid.NewGuid():N}";
        var resolutionClass = RunnerUnits.ResolutionClassForDimensions(previousRow?.VideoWidth, previousRow?.VideoHeight);

        // The runner-cost weighting needs the operator settings row already loaded for this job run.
        var operatorSettings = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var budget = RunnerBudget.FromSettings(
            operatorSettings.RunnerCapacity, operatorSettings.RunnerCostSd, operatorSettings.RunnerCost720P,
            operatorSettings.RunnerCost1080P, operatorSettings.RunnerCost4K, operatorSettings.RunnerCostUndetermined);

        await _jobStore.EnqueueOrGetAsync(
            dedupe,
            RequeueStore.RemuxPassJobKind,
            PyJsonWriter.Dumps(payload, PyJsonFormat.Compact),
            runnerCost: budget.CostFor(resolutionClass),
            priority: (int)library.Priority).ConfigureAwait(false);
    }

    private static string PosixParent(string relativePosix)
    {
        var idx = relativePosix.LastIndexOf('/');
        return idx < 0 ? string.Empty : relativePosix[..idx];
    }

    private static long FileSizeBytes(string path)
    {
        try
        {
            return new FileInfo(path).Length;
        }
        catch (IOException)
        {
            return 0;
        }
        catch (UnauthorizedAccessException)
        {
            return 0;
        }
    }

    private static double? FileAgeSeconds(string path, DateTimeOffset now)
    {
        try
        {
            var mtime = File.GetLastWriteTimeUtc(path);
            return Math.Max(0.0, (now.UtcDateTime - mtime).TotalSeconds);
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    private static DateTimeOffset? CreatedAtUtc(string path)
    {
        try
        {
            return new DateTimeOffset(File.GetCreationTimeUtc(path), TimeSpan.Zero);
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    private static DateTimeOffset? ModifiedAtUtc(string path)
    {
        try
        {
            return new DateTimeOffset(File.GetLastWriteTimeUtc(path), TimeSpan.Zero);
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    private static PyDict ParsePayload(string? payloadJson)
    {
        var raw = (payloadJson ?? string.Empty).Trim();
        if (raw.Length == 0)
        {
            return new PyDict();
        }

        PyJson data;
        try
        {
            data = PyJsonParser.Parse(raw);
        }
        catch (PyJsonDecodeException exception)
        {
            throw new ArgumentException("watched-folder remux scan dispatch payload must be a JSON object", exception);
        }

        if (data is not PyDict dict)
        {
            throw new ArgumentException("watched-folder remux scan dispatch payload must be a JSON object");
        }

        return dict;
    }
}
