using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Core.Processing;
using Weir.Core.Rules;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Processing.RemuxPass;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// Worker handler for <see cref="LibraryModeJobKinds.CleanKind"/> (#505 point 8): probes and plans one library file exactly
/// as the scan did, then — when the plan actually changes something — remuxes it to a temp file beside the original
/// (<c>mode: library</c>) and hands it to the #506 safe swap. Never calls <see cref="IFailurePolicy"/>: a library failure is
/// recorded and reported, but never queues a reject or pass-through job, and the original is always left untouched on
/// anything short of a committed swap.
/// </summary>
public sealed class LibraryCleanHandler : IJobHandler
{
    private readonly SqliteDatabase _database;
    private readonly MediaTools _tools;
    private readonly SafeSwap _swap;
    private readonly ILibraryFileChangeNotifier _notifier;
    private readonly IHardlinkInspector _hardlinkInspector;
    private readonly Weir.Core.Library.IRemovedTrackStore _removedTrackStore;
    private readonly TimeProvider _time;
    private readonly ILogger<LibraryCleanHandler> _logger;

    public LibraryCleanHandler(
        SqliteDatabase database,
        MediaTools tools,
        SafeSwap swap,
        ILibraryFileChangeNotifier notifier,
        IHardlinkInspector hardlinkInspector,
        Weir.Core.Library.IRemovedTrackStore removedTrackStore,
        TimeProvider time,
        ILogger<LibraryCleanHandler> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _tools = tools ?? throw new ArgumentNullException(nameof(tools));
        _swap = swap ?? throw new ArgumentNullException(nameof(swap));
        _notifier = notifier ?? throw new ArgumentNullException(nameof(notifier));
        _hardlinkInspector = hardlinkInspector ?? throw new ArgumentNullException(nameof(hardlinkInspector));
        _removedTrackStore = removedTrackStore ?? throw new ArgumentNullException(nameof(removedTrackStore));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public string JobKind => LibraryModeJobKinds.CleanKind;

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        PyDict payload;
        try
        {
            payload = string.IsNullOrWhiteSpace(context.PayloadJson) ? new PyDict() : PyJsonParser.Parse(context.PayloadJson) as PyDict ?? new PyDict();
        }
        catch (PyJsonDecodeException)
        {
            payload = new PyDict();
        }

        var libraryId = payload.Get("library_id") is PyInt idValue ? (long)idValue.Value : 0;
        var path = payload.Get("path") is PyStr { Value.Length: > 0 } pathValue ? pathValue.Value : string.Empty;
        var trigger = payload.Get("trigger") is PyStr { Value.Length: > 0 } triggerValue ? triggerValue.Value : "manual";
        var confirmed = payload.Get("confirm_final_removal") is PyBool { Value: true };
        var inUseAttempts = payload.Get("in_use_attempts") is PyInt attemptsValue ? (int)attemptsValue.Value : 0;

        if (path.Length == 0)
        {
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, "This job's payload has no file path.").ConfigureAwait(false);
            return;
        }

        ProcessingLibraryRecord? library;
        ProcessingRulesConfig rules;
        LibrarySettings settings;
        await using (var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false))
        {
            library = libraryId > 0 ? await LibraryStore.GetAsync(uow, libraryId).ConfigureAwait(false) : null;
            if (library is null)
            {
                await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, "This library no longer exists.").ConfigureAwait(false);
                await uow.CommitAsync().ConfigureAwait(false);
                return;
            }

            var ruleSet = library.RuleSetId is { } ruleSetId ? await LibraryStore.GetRuleSetAsync(uow, ruleSetId).ConfigureAwait(false) : null;
            rules = ruleSet is not null ? RemuxPassPaths.RulesConfigFor(ruleSet) : RuleSetConversion.ToRulesConfig(null);
            settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
        }

        // #508 step 1: a file another name still shares data with (almost always a download client still seeding
        // it) is skipped before any read/plan/write work, unless the library allows cleaning hardlinked files. An
        // unreadable link count (no such file, an unsupported volume) is treated as "cannot tell", which
        // HardlinkPolicy already resolves to "do not block" rather than guessing.
        int? linkCount;
        try
        {
            linkCount = _hardlinkInspector.LinkCount(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            linkCount = null;
        }

        var hardlinkDecision = HardlinkPolicy.Evaluate(linkCount, settings.CleanHardlinkedFiles);
        if (hardlinkDecision.Skip)
        {
            var preflight = LibraryCleanPreflight.Evaluate(path, hardlinkDecision, redownloadRisk: null);
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileSkipped, string.Join(" ", preflight.SkipReasons)).ConfigureAwait(false);
            return;
        }

        ProbeResult probe;
        try
        {
            var probed = await _tools.FfprobeJsonAsync(path, cancellationToken: cancellationToken).ConfigureAwait(false);
            probe = ProbeResult.Parse(probed.GetRawText());
        }
        catch (Exception exception) when (exception is MediaToolException or MediaToolTimeoutException)
        {
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, $"Weir could not read this file: {exception.Message}").ConfigureAwait(false);
            return;
        }

        LibraryFilePlanResult plan;
        try
        {
            plan = LibraryFilePlanner.Classify(probe, rules);
        }
        catch (RulesInputException exception)
        {
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, $"Weir could not plan this file: {exception.Message}").ConfigureAwait(false);
            return;
        }

        if (plan.Classification == LibraryFileClassification.Matches)
        {
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileSkipped, "This file already matches the library's rules; nothing to clean.").ConfigureAwait(false);
            return;
        }

        if (plan.Classification == LibraryFileClassification.CannotProcess)
        {
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, plan.Reason ?? "Weir cannot process this file.").ConfigureAwait(false);
            return;
        }

        var removesTracks = plan.RemovedAudioCount + plan.RemovedSubtitleCount > 0;
        if (removesTracks && !confirmed)
        {
            // Belt and braces: the API refuses this before the job is ever queued (400 without confirm_final_removal).
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, "Removing tracks was not confirmed, so Weir left this file untouched.").ConfigureAwait(false);
            return;
        }

        double? durationSeconds = null;
        if (probe.Json.TryGetProperty("format", out var format) && format.TryGetProperty("duration", out var durationText) &&
            double.TryParse(durationText.GetString(), System.Globalization.CultureInfo.InvariantCulture, out var parsedDuration))
        {
            durationSeconds = parsedDuration;
        }

        var sourceWarnings = await _tools.ProbeWarningLinesAsync(path, cancellationToken).ConfigureAwait(false);

        var result = await _swap.RunAsync(
            context.Id,
            path,
            async (tempPath, ct) =>
            {
                var workDir = Path.GetDirectoryName(tempPath) is { Length: > 0 } dir ? dir : ".";
                var written = await _tools.RemuxToTempFileAsync(path, workDir, plan.Plan!, probe.Json, sourceWarnings, durationSeconds: durationSeconds, cancellationToken: ct).ConfigureAwait(false);
                try
                {
                    File.Move(written, tempPath, overwrite: false);
                }
                catch
                {
                    TryDelete(written);
                    throw;
                }
            },
            SwapOptions.Default,
            cancellationToken).ConfigureAwait(false);

        switch (result.Outcome)
        {
            case Weir.Core.LibraryMode.SwapOutcome.Committed:
                await OnCommittedAsync(library, path, plan, result, cancellationToken).ConfigureAwait(false);
                return;
            case Weir.Core.LibraryMode.SwapOutcome.InUse:
                await OnInUseAsync(context, payload, libraryId, path, trigger, inUseAttempts).ConfigureAwait(false);
                return;
            default:
                await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, result.Message).ConfigureAwait(false);
                return;
        }
    }

    private async Task OnCommittedAsync(ProcessingLibraryRecord library, string path, LibraryFilePlanResult plan, SwapResult result, CancellationToken cancellationToken)
    {
        // #509 step 1: record what this clean removed for good, keyed the same way library mode identifies the
        // file everywhere else (library id + this path). A future rule change can then ask #509's diff whether
        // any of it would now be kept. Best-effort: a store failure here must never undo an already-committed swap.
        if (plan.Plan is { RemovedTrackRecords.Count: > 0 } committedPlan)
        {
            try
            {
                var key = new Weir.Core.Library.RemovedTrackFileKey(library.Id, path);
                await _removedTrackStore.RecordAsync(key, committedPlan.RemovedTrackRecords, cancellationToken).ConfigureAwait(false);
            }
#pragma warning disable CA1031 // Best-effort, like the notify step below: recording removed tracks must never fail a committed clean.
            catch (Exception exception)
#pragma warning restore CA1031
            {
                _logger.LogWarning(exception, "Library clean committed but recording its removed tracks (#509) failed.");
            }
        }

        // #507 (telling the manager) records its own Activity entries for a notify failure or warning; this handler's own
        // "cleaned" entry below never depends on how that call went.
        try
        {
            var reason = $"removed {plan.RemovedAudioCount} audio and {plan.RemovedSubtitleCount} subtitle track(s)";
            await _notifier.NotifyAsync(new LibraryFileChange(library.MediaType, path, Reason: reason), cancellationToken).ConfigureAwait(false);
        }
#pragma warning disable CA1031 // The notify step is best-effort and must never fail a committed clean.
        catch (Exception exception)
#pragma warning restore CA1031
        {
            _logger.LogWarning(exception, "Library clean committed but the manager notify step (#507) failed to run.");
        }

        var warnings = result.Warnings;
        var detail = $"Cleaned {Path.GetFileName(path)}: removed {plan.RemovedAudioCount} audio and {plan.RemovedSubtitleCount} subtitle track(s)." +
                     (warnings.Count > 0 ? " " + string.Join(" ", warnings) : string.Empty);
        await RecordAsync(library.Id, path, null, LibraryActivityEventTypes.FileCleaned, detail, "success").ConfigureAwait(false);
    }

    /// <summary>
    /// A locked file is not a failure (#506): back off 5, 15 then 60 minutes by putting the row back to <c>pending</c> with a
    /// future <c>not_before</c> and clearing the lease ourselves — <see cref="ProcessingJobStore.CompleteClaimedAsync"/>'s own
    /// lease check then finds the lease already gone and leaves this update alone. After the third attempt, report it as
    /// given up and let the job complete normally.
    /// </summary>
    private async Task OnInUseAsync(JobWorkContext context, PyDict payload, long libraryId, string path, string trigger, int inUseAttempts)
    {
        var attempt = inUseAttempts + 1;
        var delay = Weir.Core.LibraryMode.SafeSwapRules.InUseRetryDelay(attempt);
        if (delay is null)
        {
            await RecordAsync(libraryId, path, trigger, LibraryActivityEventTypes.FileFailed, Weir.Core.LibraryMode.SafeSwapRules.InUseGaveUpMessage).ConfigureAwait(false);
            return;
        }

        payload.Set("in_use_attempts", attempt);
        var notBefore = _time.GetUtcNow() + delay.Value;
        await using var uow = await UnitOfWork.OpenAsync(_database, CancellationToken.None).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "UPDATE jobs SET payload_json = @payload, status = @pending, lease_owner = NULL, lease_expires_at = NULL, not_before = @notBefore, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
            ("@payload", PyJsonWriter.Dumps(payload, PyJsonFormat.Compact)),
            ("@pending", ProcessingJobStatus.Pending),
            ("@notBefore", notBefore.UtcDateTime),
            ("@id", context.Id)).ConfigureAwait(false);
        await uow.CommitAsync().ConfigureAwait(false);
        _logger.LogInformation("Library clean postponed (in use, attempt {Attempt}) job_id={JobId} path={Path}", attempt, context.Id, path);
    }

    private async Task RecordAsync(long libraryId, string path, string? trigger, string eventType, string detail, string? result = null)
    {
        try
        {
            await using var uow = await UnitOfWork.OpenAsync(_database, CancellationToken.None).ConfigureAwait(false);
            var extra = new PyDict().Set("library_id", libraryId).Set("relative_path", path);
            if (trigger is not null)
            {
                extra.Set("trigger", trigger);
            }

            if (result is not null)
            {
                extra.Set("result", result);
            }

            await SqliteActivityWriter.RecordAsync(
                    uow,
                    new ActivityEventDraft(eventType, "library", detail, PyJsonWriter.Dumps(extra, PyJsonFormat.Compact)))
                .ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is Microsoft.Data.Sqlite.SqliteException or InvalidOperationException)
        {
            _logger.LogWarning(exception, "Library mode could not record its activity entry; the outcome remains only in the job row.");
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }
}
