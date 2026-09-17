using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.MediaManagers;
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
/// Title matching (#551, "Blade Runner 2049 (Radarr)"): for every enabled connection covering the library's media scope,
/// <c>IMediaManagerPort.ListLibraryFilesAsync</c> (#507) is asked which files it knows, then each is matched to one of this
/// scan's own walked files with <see cref="LibraryTitleMatcher.MatchLocalPath"/> (a direct path comparison, or the reverse
/// of the local-&gt;manager path translation #507's notify step already uses). A manager that cannot be reached is recorded
/// as a scan error ("couldn't ask Radarr...") rather than failing the scan; its files, like any file no connection claims,
/// stay unmatched and processable (#505 explicitly allows this).
/// </remarks>
public sealed class LibraryScanHandler : IJobHandler
{
    private readonly SqliteDatabase _database;
    private readonly MediaTools _tools;
    private readonly MediaManagerConnectionService _connections;
    private readonly IHardlinkInspector _hardlinks;
    private readonly TimeProvider _time;

    public LibraryScanHandler(
        SqliteDatabase database,
        MediaTools tools,
        MediaManagerConnectionService connections,
        IHardlinkInspector hardlinks,
        TimeProvider time,
        ILogger<LibraryScanHandler> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _tools = tools ?? throw new ArgumentNullException(nameof(tools));
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _hardlinks = hardlinks ?? throw new ArgumentNullException(nameof(hardlinks));
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
        IReadOnlyList<LibraryScanFileEntry> previousFiles;
        List<ManagerConnection> connections;
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
            previousFiles = await LibraryScanStore.PreviousFilesForCacheAsync(uow, libraryId).ConfigureAwait(false);
            connections = await _connections.ConnectionsForScopeAsync(uow, library.MediaType).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
        }

        var previousByPath = previousFiles.ToDictionary(f => f.Path, StringComparer.Ordinal);

        var entries = new List<LibraryScanFileEntry>();
        var errors = new List<string>();
        foreach (var walked in LibraryFileWalker.Walk(library, settings.Folders))
        {
            cancellationToken.ThrowIfCancellationRequested();
            entries.Add(await ClassifyOneAsync(walked, rules, previousByPath, cancellationToken).ConfigureAwait(false));
        }

        // #551: match each walked file to the title a linked Sonarr/Radarr connection already knows it under.
        errors.AddRange(await MatchManagerTitlesAsync(connections, library.MediaType, settings.Folders, entries, cancellationToken).ConfigureAwait(false));

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
        // #568: how many names share this file's data, recorded per scan so the Problems view can group seeding
        // files in SQL instead of stat()-ing a whole library on every page load. Unknown stays null (see
        // HardlinkPolicy: unknown is never treated as evidence of sharing).
        var linkCount = LinkCountOf(walked.Path);

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
                    null, $"Weir could not read this file: {exception.Message}", 0, 0, null, null, null,
                    ProblemKind: ProblemKindForReadFailure(walked.Path, exception), LinkCount: linkCount);
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
            classification.EstimatedBytesSaved,
            ProblemKind: classification.ProblemKind,
            LinkCount: linkCount);
    }

    private int? LinkCountOf(string path)
    {
        try
        {
            return _hardlinks.LinkCount(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    /// <summary>
    /// Tells "Weir is not allowed to open this" apart from "this file is damaged", since #568's Problems view
    /// gives each a different thing to do (fix the permissions, versus download the title again). The evidence is
    /// whether Weir itself can open the file for reading right now, not the tool's wording, which varies by build.
    /// </summary>
    private static LibraryProblemKind ProblemKindForReadFailure(string path, Exception exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        try
        {
            using var probe = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            return LibraryProblemKind.Unreadable;
        }
        catch (UnauthorizedAccessException)
        {
            return LibraryProblemKind.NoPermission;
        }
        catch (Exception open) when (open is IOException)
        {
            return LibraryProblemKind.Unreadable;
        }
    }

    /// <summary>
    /// #551: asks every connection covering this library's scope which files it knows, matches each to one of
    /// <paramref name="entries"/>' own paths, and mutates the first match's manager fields in place (a path
    /// already claimed by an earlier connection is left alone — first reported match wins). Returns one plain
    /// note per connection Weir could not ask, for the scan's own error list ("couldn't ask Radarr..."); an
    /// unreachable manager never fails the scan, and every file it would have covered simply stays unmatched.
    /// </summary>
    private async Task<List<string>> MatchManagerTitlesAsync(
        List<ManagerConnection> connections,
        string mediaScope,
        IReadOnlyList<string> localFolders,
        List<LibraryScanFileEntry> entries,
        CancellationToken cancellationToken)
    {
        var notes = new List<string>();
        if (entries.Count == 0 || connections.Count == 0)
        {
            return notes;
        }

        var localPaths = entries.Select(e => e.Path).ToList();
        var matchedPaths = new HashSet<string>(StringComparer.Ordinal);
        var indexByPath = entries
            .Select((entry, index) => (entry.Path, index))
            .ToDictionary(pair => pair.Path, pair => pair.index, StringComparer.Ordinal);

        foreach (var connection in connections)
        {
            if (_connections.Ports.PortForKind(connection.Kind) is not { } port)
            {
                continue;
            }

            ManagerLibraryFilesSignal signal;
            try
            {
                signal = await port.ListLibraryFilesAsync(connection, mediaScope, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
            {
                notes.Add($"Weir couldn't ask {connection.Label} which titles it manages: {exception.Message}");
                continue;
            }

            if (signal.Status == SignalStatus.Unreachable)
            {
                notes.Add($"Weir couldn't ask {connection.Label} which titles it manages: {signal.Detail}");
                continue;
            }

            if (signal.Status != SignalStatus.Reported || signal.Files.Count == 0)
            {
                continue;
            }

            var description = await port.DescribeAsync(connection, cancellationToken).ConfigureAwait(false);
            var managerLibraries = description.Status == SignalStatus.Reported ? description.Libraries : [];

            foreach (var file in signal.Files)
            {
                var localPath = LibraryTitleMatcher.MatchLocalPath(file.FilePath, localPaths, managerLibraries, localFolders);
                if (localPath is null || !matchedPaths.Add(localPath))
                {
                    continue;
                }

                var index = indexByPath[localPath];
                entries[index] = entries[index] with
                {
                    ManagerKind = connection.Kind,
                    ManagerTitle = file.TitleName,
                    ManagerConnectionId = connection.ConnectionId,
                    ManagerTitleId = file.TitleId,
                    ManagerFileId = file.FileId,
                    ManagerQualityProfileId = file.QualityProfileId,
                };
            }
        }

        return notes;
    }
}
