using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Core.Media;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// Worker handler for <see cref="LibraryModeJobKinds.ScanKind"/> (#505 point 2): walks a library's library folders,
/// probes new or changed files (cached by path, size and mtime), and classifies each against the library's rules with the
/// exact same engine the download pipeline plans with. Read-only: no file is written, moved or queued for cleaning by a scan.
/// </summary>
/// <remarks>
/// Title matching (#505: "Blade Runner 2049 (Radarr)") needs <c>IMediaManagerPort.ListLibraryFilesAsync</c>, which is being
/// added on the separate <c>feat/507-file-changed</c> branch with a different shape than a first draft here used
/// (<c>Task&lt;ManagerLibraryFilesSignal&gt; ListLibraryFilesAsync(connection, mediaScope, ct)</c>). Wiring it in before that
/// branch lands would invent a seam #507 does not share, so every file is reported unmatched for now — #505 explicitly
/// allows that ("An unmatched file is still processable") — and the manager/title columns are wired up once #507 merges.
/// </remarks>
public sealed class LibraryScanHandler : IJobHandler
{
    private readonly SqliteDatabase _database;
    private readonly MediaTools _tools;
    private readonly TimeProvider _time;

    public LibraryScanHandler(
        SqliteDatabase database,
        MediaTools tools,
        TimeProvider time,
        ILogger<LibraryScanHandler> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _tools = tools ?? throw new ArgumentNullException(nameof(tools));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        // Kept in the constructor for DI symmetry with LibraryCleanHandler; nothing here logs yet.
        ArgumentNullException.ThrowIfNull(logger);
    }

    public string JobKind => LibraryModeJobKinds.ScanKind;

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        long libraryId;
        string trigger;
        RefinerLibraryRecord? library;
        LibrarySettings settings;
        RefinerRulesConfig rules;
        LibraryScanSnapshot? previous;
        await using (uow.ConfigureAwait(false))
        {
            PyDict payload;
            try
            {
                payload = string.IsNullOrWhiteSpace(context.PayloadJson) ? new PyDict() : PyJsonParser.Parse(context.PayloadJson) as PyDict ?? new PyDict();
            }
            catch (PyJsonDecodeException)
            {
                payload = new PyDict();
            }

            libraryId = payload.Get("library_id") is PyInt idValue ? (long)idValue.Value : 0;
            trigger = payload.Get("trigger") is PyStr { Value.Length: > 0 } triggerValue ? triggerValue.Value : "manual";
            library = libraryId > 0 ? await LibraryStore.GetAsync(uow, libraryId).ConfigureAwait(false) : null;
            if (library is null)
            {
                await LibraryScanStore.RecordResultAsync(uow, context.Id, new LibraryScanSnapshot(libraryId, _time.GetUtcNow(), [], []), false, "This library no longer exists.")
                    .ConfigureAwait(false);
                await uow.CommitAsync().ConfigureAwait(false);
                return;
            }

            settings = await LibrarySettingsStore.GetAsync(uow, libraryId).ConfigureAwait(false);
            if (settings.Folders.Count == 0)
            {
                await LibraryScanStore.RecordResultAsync(
                        uow, context.Id, new LibraryScanSnapshot(libraryId, _time.GetUtcNow(), [], []), false,
                        "No library folders are configured for this library yet. Add one in Library settings, then scan again.")
                    .ConfigureAwait(false);
                await uow.CommitAsync().ConfigureAwait(false);
                return;
            }

            var ruleSet = library.RuleSetId is { } ruleSetId ? await LibraryStore.GetRuleSetAsync(uow, ruleSetId).ConfigureAwait(false) : null;
            rules = ruleSet is not null ? RemuxPassPaths.RulesConfigFor(ruleSet) : RuleSetConversion.ToRulesConfig(null);
            previous = await LibraryScanStore.PreviousSnapshotForCacheAsync(uow, libraryId, context.Id).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
        }

        var previousByPath = (previous?.Files ?? []).ToDictionary(f => f.Path, StringComparer.Ordinal);

        var entries = new List<LibraryScanFileEntry>();
        var errors = new List<string>();
        foreach (var walked in LibraryFileWalker.Walk(library, settings.Folders))
        {
            cancellationToken.ThrowIfCancellationRequested();
            entries.Add(await ClassifyOneAsync(walked, rules, previousByPath, cancellationToken).ConfigureAwait(false));
        }

        var snapshot = new LibraryScanSnapshot(libraryId, _time.GetUtcNow(), entries, errors);
        var wouldChange = entries.Count(e => e.Classification == LibraryFileClassification.WouldChange);
        var cannotProcess = entries.Count(e => e.Classification == LibraryFileClassification.CannotProcess);

        await using (var recordUow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false))
        {
            await LibraryScanStore.RecordResultAsync(recordUow, context.Id, snapshot, true, null).ConfigureAwait(false);
            await SqliteActivityWriter.RecordAsync(
                    recordUow,
                    new ActivityEventDraft(
                        LibraryActivityEventTypes.ScanCompleted,
                        "library",
                        $"Scanned {library.Name}: {entries.Count} file(s), {wouldChange} would change, {cannotProcess} could not be processed",
                        PyJsonWriter.Dumps(
                            new PyDict().Set("trigger", trigger).Set("library_id", libraryId).Set("result", "success"),
                            PyJsonFormat.Compact)))
                .ConfigureAwait(false);
            await recordUow.CommitAsync().ConfigureAwait(false);
        }
    }

    private async Task<LibraryScanFileEntry> ClassifyOneAsync(
        LibraryWalkedFile walked,
        RefinerRulesConfig rules,
        Dictionary<string, LibraryScanFileEntry> previousByPath,
        CancellationToken cancellationToken)
    {
        string probeJson;
        if (previousByPath.TryGetValue(walked.Path, out var cached) && cached.MatchesFile(walked.Path, walked.SizeBytes, walked.ModifiedTimeUnixSeconds) && cached.ProbeJson is { Length: > 0 })
        {
            probeJson = cached.ProbeJson;
        }
        else
        {
            try
            {
                var probed = await _tools.FfprobeJsonAsync(walked.Path, cancellationToken: cancellationToken).ConfigureAwait(false);
                probeJson = probed.GetRawText();
            }
            catch (Exception exception) when (exception is MediaToolException or MediaToolTimeoutException)
            {
                return new LibraryScanFileEntry(
                    walked.Path, walked.SizeBytes, walked.ModifiedTimeUnixSeconds, LibraryFileClassification.CannotProcess,
                    null, $"Weir could not read this file: {exception.Message}", 0, 0, null, null, null);
            }
        }

        LibraryFilePlanResult classification;
        try
        {
            classification = LibraryFilePlanner.Classify(ProbeResult.Parse(probeJson), rules);
        }
        catch (Exception exception) when (exception is RulesInputException)
        {
            classification = LibraryFilePlanResult.CannotProcess($"Weir could not plan this file: {exception.Message}");
        }

        return new LibraryScanFileEntry(
            walked.Path,
            walked.SizeBytes,
            walked.ModifiedTimeUnixSeconds,
            classification.Classification,
            classification.Summary,
            classification.Reason,
            classification.RemovedAudioCount,
            classification.RemovedSubtitleCount,
            null,
            null,
            probeJson,
            classification.EstimatedBytesSaved);
    }
}
