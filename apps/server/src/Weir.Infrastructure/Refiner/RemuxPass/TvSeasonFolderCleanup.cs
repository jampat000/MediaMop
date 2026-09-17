using System.Globalization;
using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// TV-only post-success watched-folder season cleanup (port of <c>refiner_tv_season_folder_cleanup.py</c>'s
/// <c>handle_tv_cleanup_after_success</c>). Movies release-folder cleanup lives only in
/// <see cref="RemuxPassRunner"/>; the two paths are not merged, matching Python's own module note. Deleting
/// a whole season folder is not something to do on a guess: this refuses to run when any manager covering
/// TV could not answer (<see cref="ManagerQueueSignals"/>, already ported for #522's queue-signal work), and
/// checks every direct-child episode against the same manager queue signals, any other pending/running
/// Refiner TV job, and either the pass that just finished or a prior recorded success, before removing
/// anything.
/// </summary>
public sealed class TvSeasonFolderCleanup : ITvSeasonFolderCleanup
{
    private readonly SqliteDatabase _database;
    private readonly MediaManagerConnectionService _connections;
    private readonly TimeProvider _time;
    private readonly ILogger<TvSeasonFolderCleanup> _logger;

    public TvSeasonFolderCleanup(SqliteDatabase database, MediaManagerConnectionService connections, TimeProvider time, ILogger<TvSeasonFolderCleanup> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <summary><c>get_tv_episode_set_media_files</c>: direct-child media candidates only, in filename order.</summary>
    public static List<string> GetTvEpisodeSetMediaFiles(string seasonFolder)
    {
        if (!Directory.Exists(seasonFolder))
        {
            return [];
        }

        try
        {
            return [.. Directory.EnumerateFiles(seasonFolder)
                .Where(WatchedFolderScanOps.IsRefinerMediaCandidate)
                .OrderBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase)];
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return [];
        }
    }

    public async Task RunAsync(TvSeasonCleanupContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var output = context.Output;
        SkippedTvSeasonFolderCleanup.InitFields(output);
        var summary = (PyList)output.Get("tv_episode_check_summary")!;
        var completeness = (PyDict)output.Get("tv_output_completeness_check")!;
        var cascade = (PyList)output.Get("tv_cascade_folders_deleted")!;

        void AddSummary(string line) => summary.Items.Add(new PyStr(line));

        var watchedResolved = RemuxPassPaths.Resolve(context.WatchedRoot);
        var srcResolved = RemuxPassPaths.Resolve(context.Source);
        if (!RemuxPassPaths.IsUnder(srcResolved, watchedResolved))
        {
            output.Set("tv_season_folder_skip_reason", "The video file is not under the saved TV watched folder, so nothing was removed.");
            AddSummary("Stopped: the processed file is not under the TV watched folder.");
            return;
        }

        var seasonFolder = Path.GetDirectoryName(srcResolved)!;
        if (!RemuxPassPaths.IsUnder(seasonFolder, watchedResolved))
        {
            output.Set("tv_season_folder_skip_reason", "The season folder would sit outside the TV watched folder, so nothing was done.");
            AddSummary("Stopped: season folder is outside the TV watched folder.");
            return;
        }

        if (RemuxPassPaths.SamePath(seasonFolder, watchedResolved))
        {
            output.Set("tv_season_folder_skip_reason",
                "The video file sits directly in the TV watched folder root. This does not delete the watched folder or " +
                "treat the whole library as one season.");
            AddSummary("Stopped: the season folder is the same as the TV watched folder root — nothing removed.");
            return;
        }

        output.Set("tv_season_folder_path", seasonFolder);

        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);

        // Deleting a whole season folder is not something to do on a guess, so unlike the watched-folder
        // scan this gate refuses to run when any manager could not answer.
        var signals = await _connections.CollectQueueSignalsAsync(uow, RefinerMediaScopes.Tv, connectionIds: null, cancellationToken).ConfigureAwait(false);
        var report = ManagerQueueSignals.ReportForSignals(signals);
        if (report.Consulted == 0)
        {
            output.Set("tv_manager_queue_unavailable", true);
            output.Set("tv_season_folder_skip_reason",
                "No media manager is connected for TV episodes, so Weir could not check whether anything is " +
                "still importing. TV season cleanup was skipped so nothing was removed by mistake.");
            AddSummary("Stopped: no media manager is connected for TV episodes.");
            return;
        }

        if (!report.AllReported)
        {
            var note = report.SilentDetails[0];
            output.Set("tv_manager_queue_unavailable", true);
            output.Set("tv_season_folder_skip_reason", $"{note} TV season cleanup was skipped so nothing was removed by mistake.");
            AddSummary($"Stopped: import check failed — {note}");
            return;
        }

        var episodes = GetTvEpisodeSetMediaFiles(seasonFolder);
        if (episodes.Count == 0)
        {
            output.Set("tv_season_folder_skip_reason", "This season folder has no direct video files treated as episodes, so nothing was removed.");
            AddSummary("Stopped: no episode media files found as direct children of the season folder.");
            return;
        }

        var outputFolderRaw = PyStrings.Strip(context.Runtime.OutputFolder ?? string.Empty);
        if (outputFolderRaw.Length == 0)
        {
            output.Set("tv_season_folder_skip_reason", "No TV output folder is configured, so season cleanup was skipped.");
            AddSummary("Stopped: TV output folder is not configured.");
            return;
        }

        var outDir = RemuxPassPaths.Resolve(outputFolderRaw);
        var remuxRel = PyStrings.Strip(context.RemuxContext.Get("relative_media_path") is PyStr rmp ? rmp.Value : string.Empty);
        var liveOk =
            context.RemuxContext.Get("ok") is PyBool { Value: true } &&
            context.RemuxContext.Get("dry_run") is PyBool { Value: false } &&
            context.RemuxContext.Get("outcome") is PyStr outcomeStr &&
            (outcomeStr.Value == RemuxPassOutcomes.LiveOutputWritten || outcomeStr.Value == RemuxPassOutcomes.LiveSkippedNotRequired);

        foreach (var episode in episodes)
        {
            var name = Path.GetFileName(episode);
            var rel = WatchedFolderScanOps.RelativePosixPathUnderWatched(watchedResolved, episode);
            var lineParts = new List<string> { $"{name}:" };

            var holder = EpisodeHeldByAnyManager(signals, episode);
            if (holder is not null)
            {
                output.Set("tv_season_folder_skip_reason",
                    $"{holder} is still working on at least one episode in this season ({name}), so the whole season folder was left in place.");
                lineParts.Add($"Import check failed — {holder} still lists this episode.");
                AddSummary(string.Join(" ", lineParts));
                return;
            }

            lineParts.Add("Import check passed — no connected media manager still lists this episode.");

            if (await WatchedFolderScanOps.ActiveRemuxPassExistsForRelativePathAsync(uow, rel, RefinerMediaScopes.Tv, libraryId: null, excludeJobId: context.CurrentJobId).ConfigureAwait(false))
            {
                output.Set("tv_season_folder_skip_reason", $"Another TV job is already queued or running for {name}, so the whole season folder was left in place.");
                lineParts.Add("Active TV job check failed — a TV remux job is pending or running for this path.");
                AddSummary(string.Join(" ", lineParts));
                return;
            }

            lineParts.Add("Active TV job check passed — no other pending or running TV remux job for this path.");

            var relEq = rel == remuxRel;
            if (relEq && liveOk)
            {
                var expectedOut = ExpectedOutputFile(context.FinalOutputFile, context.RemuxContext, outDir, rel, relEq);
                var check = RemuxPassRunner.CheckOutputFileCompleteness(expectedOut, episode, tv: true);
                if (!RecordCompleteness(completeness, output, name, check,
                        "Output completeness check failed for this TV pass", lineParts, AddSummary))
                {
                    return;
                }

                lineParts.Add("Processed check passed — this episode is the pass that just finished, and the output file passed the size checks.");
            }
            else if (await ActivityDocumentsTvLiveSuccessAsync(uow, rel, cancellationToken).ConfigureAwait(false))
            {
                var expectedOut = RemuxPassPaths.Resolve(Path.Join(outDir, rel));
                var check = RemuxPassRunner.CheckOutputFileCompleteness(expectedOut, episode, tv: true);
                if (!RecordCompleteness(completeness, output, name, check,
                        "Output completeness check failed for a previously finished TV pass", lineParts, AddSummary))
                {
                    return;
                }

                lineParts.Add("Processed check passed — a successful live TV pass is on record and the output file passed the size checks.");
            }
            else
            {
                double ageSeconds;
                try
                {
                    ageSeconds = (_time.GetUtcNow() - File.GetLastWriteTimeUtc(episode)).TotalSeconds;
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    ageSeconds = -1;
                }

                var minAge = Math.Max(0, context.MinFileAgeSeconds);
                if (minAge > 0 && ageSeconds < minAge)
                {
                    output.Set("tv_season_folder_skip_reason",
                        $"Episode {name} was never finished in TV mode and is newer than the minimum age " +
                        $"({minAge.ToString(CultureInfo.InvariantCulture)}s), so the season folder was left in place.");
                    lineParts.Add($"Never-processed check failed — file is not old enough yet (minimum {minAge.ToString(CultureInfo.InvariantCulture)}s since last change).");
                    AddSummary(string.Join(" ", lineParts));
                    return;
                }

                completeness.Set(name, "skipped");
                lineParts.Add(
                    "Never-processed check passed — Weir has no successful live TV pass on record for this file, " +
                    "no connected media manager still lists it, and the file is old enough under your minimum-age setting.");
            }

            AddSummary(string.Join(" ", lineParts));
        }

        try
        {
            Directory.Delete(seasonFolder, recursive: true);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            var human = $"A file or folder could not be removed because the system reported it is in use or locked: {seasonFolder}. The whole season folder was left in place.";
            output.Set("tv_season_folder_skip_reason", human);
            AddSummary($"Deletion failed: {human}");
            _logger.LogWarning("TV cleanup: {Reason}", human);
            return;
        }

        output.Set("tv_season_folder_deleted", true);
        output.Set("source_deleted_after_success", true);
        output.Set("tv_season_folder_skip_reason", PyNull.Instance);
        AddSummary($"Removed the whole season folder: {seasonFolder}");

        OutputFolderCleanup.CascadeDeleteEmptyParents(Path.GetDirectoryName(seasonFolder)!, watchedResolved, cascade, _logger);
    }

    private static string ExpectedOutputFile(string? finalOutputFile, PyDict remuxContext, string outDir, string rel, bool relEq)
    {
        if (relEq && finalOutputFile is { } finalFile && File.Exists(finalFile))
        {
            return RemuxPassPaths.Resolve(finalFile);
        }

        if (remuxContext.Get("output_file") is PyStr of && PyStrings.Strip(of.Value).Length > 0)
        {
            return RemuxPassPaths.Resolve(of.Value);
        }

        return RemuxPassPaths.Resolve(Path.Join(outDir, rel));
    }

    /// <summary>Records the completeness check and the failure reason/summary line; returns false when the caller must stop.</summary>
    private static bool RecordCompleteness(PyDict completeness, PyDict output, string name, PyDict check, string failurePrefix, List<string> lineParts, Action<string> addSummary)
    {
        var status = ((PyStr)check.Get("output_completeness_check")!).Value;
        completeness.Set(name, status);
        if (status == "passed")
        {
            return true;
        }

        var note = check.Get("output_completeness_note") is PyStr n && n.Value.Length > 0
            ? n.Value
            : $"Weir expected a finished output file for {name}, but the safety check did not pass.";
        output.Set("tv_season_folder_skip_reason", note);
        lineParts.Add($"{failurePrefix} — {note}.");
        addSummary(string.Join(" ", lineParts));
        return false;
    }

    /// <summary>
    /// <c>_episode_held_by_any_manager</c>: the connection still holding this episode, or null. Ownership only
    /// (not <c>is_upstream_active</c>) — deleting a whole season is more consequential than blocking one
    /// file, so any queue presence at all is enough to hold off.
    /// </summary>
    private static string? EpisodeHeldByAnyManager(IReadOnlyList<ManagerQueueSignal> signals, string episodePath)
    {
        var resolved = RemuxPassPaths.Resolve(episodePath);
        var rows = ManagerQueueSignals.AttributedRowsForFile(signals, RefinerMediaScopes.Tv, resolved);
        var candidate = new FileAnchorCandidate(Path.GetFileNameWithoutExtension(episodePath));
        foreach (var row in rows)
        {
            if (ManagerQueueSignals.FileIsOwnedByAnyManager([row], candidate))
            {
                return row.ConnectionLabel;
            }
        }

        return null;
    }

    /// <summary>
    /// <c>_activity_documents_tv_live_success</c>: true when Activity retains a completed TV live pass with a
    /// successful terminal outcome for this path. <c>refiner_jobs</c> rows only carry the enqueue payload;
    /// terminal outcomes live in <c>activity_events.detail</c> JSON.
    /// </summary>
    private static async Task<bool> ActivityDocumentsTvLiveSuccessAsync(UnitOfWork uow, string relativePosix, CancellationToken cancellationToken)
    {
        var rows = await uow.QueryAsync(
            "SELECT detail FROM activity_events WHERE event_type = @type AND module = @module ORDER BY id DESC LIMIT 4000",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@type", ActivityEventTypes.RefinerFileRemuxPassCompleted),
            ("@module", "refiner")).ConfigureAwait(false);

        foreach (var raw in rows)
        {
            var trimmed = (raw ?? string.Empty).Trim();
            if (trimmed.Length == 0)
            {
                continue;
            }

            PyJson data;
            try
            {
                data = PyJsonParser.Parse(trimmed);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (data is not PyDict dict)
            {
                continue;
            }

            if (dict.Get("relative_media_path") is not PyStr relStr || PyStrings.Strip(relStr.Value) != relativePosix)
            {
                continue;
            }

            var scope = dict.Get("media_scope") is PyStr scopeStr ? PyStrings.Strip(scopeStr.Value).ToLowerInvariant() : "movie";
            if (scope != "tv")
            {
                continue;
            }

            if (dict.Get("dry_run") is PyBool { Value: true })
            {
                continue;
            }

            if (dict.Get("ok") is not PyBool { Value: true })
            {
                continue;
            }

            var outcome = dict.Get("outcome") is PyStr outcomeStr ? outcomeStr.Value : null;
            if (outcome != RemuxPassOutcomes.LiveOutputWritten && outcome != RemuxPassOutcomes.LiveSkippedNotRequired)
            {
                continue;
            }

            return true;
        }

        return false;
    }
}
