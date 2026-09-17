using System.Globalization;
using Microsoft.Extensions.Logging;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>A pending or leased remux job, as the cleanup gates read it.</summary>
public sealed record ActiveRemuxJob(long Id, string? PayloadJson);

/// <summary>What the post-success cleanups need from the database and the managers, so the file logic stays testable.</summary>
public interface IPostSuccessCleanupData
{
    /// <summary><c>collect_library_truth</c> for the scope.</summary>
    Task<IReadOnlyList<ManagerLibraryTruth>> CollectLibraryTruthAsync(string mediaScope, CancellationToken cancellationToken);

    /// <summary>Every pending or leased <c>refiner.file.remux_pass.v1</c> row.</summary>
    Task<IReadOnlyList<ActiveRemuxJob>> ActiveRemuxJobsAsync(CancellationToken cancellationToken);
}

/// <summary>
/// Output-folder cleanup after a successful pass: Movies' per-title folder (Pass 3a, <c>refiner_movie_output_cleanup.py</c>)
/// and TV's season folder (Pass 3b, <c>refiner_tv_output_cleanup.py</c>), each deleted only when every covering manager
/// answered and none keeps a library file inside it, nothing under it is too new, and no other pass is heading there.
/// </summary>
public sealed class OutputFolderCleanup
{
    private readonly IPostSuccessCleanupData _data;
    private readonly TimeProvider _time;
    private readonly ILogger _logger;
    private readonly int _movieMinAgeSeconds;
    private readonly int _tvMinAgeSeconds;

    public OutputFolderCleanup(IPostSuccessCleanupData data, TimeProvider time, ILogger logger, int movieMinAgeSeconds, int tvMinAgeSeconds)
    {
        _data = data ?? throw new ArgumentNullException(nameof(data));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _movieMinAgeSeconds = movieMinAgeSeconds;
        _tvMinAgeSeconds = tvMinAgeSeconds;
    }

    /// <summary><c>normalize_relative_media_path_for_match</c>: a stable posix path for comparing job payloads.</summary>
    public static string NormalizeRelativeForMatch(string rel)
    {
        var parts = PyStrings.Strip(rel ?? string.Empty).Replace('\\', '/').Split('/').Where(part => part is not ("." or "")).ToList();
        if (rel is not null && PyStrings.Strip(rel).Replace('\\', '/').StartsWith('/'))
        {
            return "/" + string.Join('/', parts);
        }

        return string.Join('/', parts);
    }

    /// <summary><c>maybe_run_movie_output_folder_cleanup_after_remux</c>.</summary>
    public async Task RunMovieAsync(PyDict output, RefinerPathRuntime runtime, string watchedRoot, string source, string? finalOutputFile, string relativeMediaPath, long? currentJobId, string mediaScope, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(runtime);
        const string Prefix = "movie_output";
        InitFields(output, Prefix, "movie_output_folder_deleted", "movie_output_folder_path", "movie_output_folder_skip_reason", "movie_output_cascade_folders_deleted");
        output.Set("movie_output_dry_run", false);

        if (mediaScope != "movie")
        {
            Skip(output, Prefix, "movie_output_folder_skip_reason", "This cleanup step applies only to Movies. TV output cleanup is separate and was not run here.");
            return;
        }

        var located = LocateTitleFolder(output, runtime, watchedRoot, source, finalOutputFile, "movie_output_folder_skip_reason", Prefix, tv: false);
        if (located is not { } place)
        {
            return;
        }

        output.Set("movie_output_folder_path", place.Folder);
        var relNorm = NormalizeRelativeForMatch(relativeMediaPath);
        if (relNorm.Length > 0 && await MovieJobBlocksAsync(relNorm, currentJobId, cancellationToken).ConfigureAwait(false))
        {
            Skip(output, Prefix, "movie_output_folder_skip_reason",
                "Another Movies Refiner video pass is already waiting or running for this same watched file path, " +
                "so output-folder cleanup was skipped to avoid racing another remux.");
            return;
        }

        var minAge = Math.Max(0, _movieMinAgeSeconds);
        var newest = NewestModifiedUnderTree(place.Folder);
        if (newest is null)
        {
            Skip(output, Prefix, "movie_output_folder_skip_reason",
                "Refiner could not read file timestamps under the movie output folder, so nothing was removed for safety.");
            return;
        }

        var age = Now() - newest.Value;
        output.Set("movie_output_age_seconds", (long)Math.Max(0.0, age));
        if (age < minAge)
        {
            Skip(output, Prefix, "movie_output_folder_skip_reason",
                $"This movie output folder was changed too recently (everything under it must be at least {minAge.ToString(CultureInfo.InvariantCulture)}s old; " +
                $"newest file age is about {((long)Math.Max(0, age)).ToString(CultureInfo.InvariantCulture)}s).");
            return;
        }

        await DeleteWhenTruthClearsAsync(output, Prefix, "movie_output_folder_skip_reason", "movie_output_folder_deleted", "movie_output_cascade_folders_deleted", "movie", place, "movie output folder", "Movies", cancellationToken)
            .ConfigureAwait(false);
    }

    /// <summary><c>maybe_run_tv_output_season_folder_cleanup_after_remux</c>.</summary>
    public async Task RunTvAsync(PyDict output, RefinerPathRuntime runtime, string watchedRoot, string source, string? finalOutputFile, long? currentJobId, string mediaScope, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(output);
        ArgumentNullException.ThrowIfNull(runtime);
        const string Prefix = "tv_output";
        InitFields(output, Prefix, "tv_output_season_folder_deleted", "tv_output_season_folder_path", "tv_output_season_folder_skip_reason", "tv_output_cascade_folders_deleted");
        output.Set("tv_output_dry_run", false);

        if (mediaScope != "tv")
        {
            Skip(output, Prefix, "tv_output_season_folder_skip_reason", "This cleanup step applies only to TV. Movies output-folder cleanup is separate and was not run here.");
            return;
        }

        var located = LocateTitleFolder(output, runtime, watchedRoot, source, finalOutputFile, "tv_output_season_folder_skip_reason", Prefix, tv: true);
        if (located is not { } place)
        {
            return;
        }

        output.Set("tv_output_season_folder_path", place.Folder);
        if (await TvJobBlocksAsync(place.OutputRoot, place.Folder, currentJobId, cancellationToken).ConfigureAwait(false))
        {
            Skip(output, Prefix, "tv_output_season_folder_skip_reason",
                "Another TV Refiner video pass is already waiting or running for an episode whose output maps to this same " +
                "season folder under your TV output library, so TV output-folder cleanup was skipped to avoid racing another remux.");
            return;
        }

        var episodes = DirectChildMediaCandidates(place.Folder);
        if (episodes.Count == 0)
        {
            Skip(output, Prefix, "tv_output_season_folder_skip_reason",
                "Refiner did not find any supported episode media file as a direct child of this season output folder, " +
                "so it could not apply the minimum-age gate for TV output cleanup. The folder was left in place.");
            return;
        }

        var minAge = Math.Max(0, _tvMinAgeSeconds);
        double? newest = null;
        foreach (var episode in episodes)
        {
            try
            {
                var modified = Seconds(File.GetLastWriteTimeUtc(episode));
                newest = newest is null ? modified : Math.Max(newest.Value, modified);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
        }

        if (newest is null)
        {
            Skip(output, Prefix, "tv_output_season_folder_skip_reason",
                "Refiner could not read timestamps for direct-child episode files in this season output folder, so nothing was removed for safety.");
            return;
        }

        var age = Now() - newest.Value;
        output.Set("tv_output_age_seconds", (long)Math.Max(0.0, age));
        if (age < minAge)
        {
            Skip(output, Prefix, "tv_output_season_folder_skip_reason",
                $"Direct-child episode media in this TV season output folder was modified too recently " +
                $"(each must be at least {minAge.ToString(CultureInfo.InvariantCulture)}s old by newest file; newest is about {((long)Math.Max(0, age)).ToString(CultureInfo.InvariantCulture)}s).");
            return;
        }

        await DeleteWhenTruthClearsAsync(output, Prefix, "tv_output_season_folder_skip_reason", "tv_output_season_folder_deleted", "tv_output_cascade_folders_deleted", "tv", place, "TV season output folder", "TV", cancellationToken)
            .ConfigureAwait(false);
    }

    private readonly record struct TitleFolder(string OutputRoot, string Folder);

    private static TitleFolder? LocateTitleFolder(PyDict output, RefinerPathRuntime runtime, string watchedRoot, string source, string? finalOutputFile, string skipKey, string prefix, bool tv)
    {
        var label = tv ? "TV" : "Movies";
        var rootRaw = PyStrings.Strip(runtime.OutputFolder ?? string.Empty);
        if (rootRaw.Length == 0)
        {
            Skip(output, prefix, skipKey, tv
                ? "No TV output folder is configured, so Refiner did not evaluate TV output-folder cleanup."
                : "No Movies output folder is configured, so Refiner did not evaluate output-folder cleanup.");
            return null;
        }

        var outputRoot = RemuxPassPaths.Resolve(rootRaw);
        if (!Directory.Exists(outputRoot))
        {
            Skip(output, prefix, skipKey, tv
                ? "The TV output folder is missing on disk, so TV output-folder cleanup was skipped."
                : "The Movies output folder is missing on disk, so output-folder cleanup was skipped.");
            return null;
        }

        var watched = RemuxPassPaths.Resolve(watchedRoot);
        var src = RemuxPassPaths.Resolve(source);
        var relUnderWatched = RemuxPassPaths.RelativeTo(src, watched);
        if (relUnderWatched is null)
        {
            Skip(output, prefix, skipKey, tv
                ? "The source file is not under the saved TV watched folder, so TV output-folder cleanup was skipped."
                : $"The source file is not under the saved {label} watched folder, so output-folder cleanup was skipped.");
            return null;
        }

        var mediaOut = finalOutputFile is not null ? RemuxPassPaths.Resolve(finalOutputFile) : RemuxPassPaths.Resolve(Path.Join(outputRoot, relUnderWatched));
        if (!RemuxPassPaths.IsUnder(mediaOut, outputRoot))
        {
            Skip(output, prefix, skipKey, tv
                ? "The expected TV episode file path would sit outside the TV output folder, so TV output-folder cleanup was skipped."
                : "The expected movie file path would sit outside the Movies output folder, so output-folder cleanup was skipped.");
            return null;
        }

        var folder = Path.GetDirectoryName(mediaOut) ?? mediaOut;
        if (!RemuxPassPaths.IsUnder(folder, outputRoot))
        {
            Skip(output, prefix, skipKey, tv
                ? "The TV season output folder would sit outside the TV output root, so Refiner did not change it."
                : "The movie output folder would sit outside the Movies output root, so Refiner did not change it.");
            return null;
        }

        if (RemuxPassPaths.SamePath(folder, outputRoot))
        {
            Skip(output, prefix, skipKey, tv
                ? "The episode file sits directly in the TV output folder root, so Refiner does not remove a season folder here."
                : "The movie file sits directly in the Movies output folder root, so Refiner does not remove a per-title folder here.");
            return null;
        }

        return new TitleFolder(outputRoot, folder);
    }

    private async Task DeleteWhenTruthClearsAsync(PyDict output, string prefix, string skipKey, string deletedKey, string cascadeKey, string scope, TitleFolder place, string noun, string logLabel, CancellationToken cancellationToken)
    {
        var answers = await _data.CollectLibraryTruthAsync(scope, cancellationToken).ConfigureAwait(false);
        var truth = LibraryTruthGate.EvaluateForFolder(answers, place.Folder, scope, ResolveOrNull, OperatingSystem.IsWindows());
        output.Set($"{prefix}_truth_check", truth.Check);
        output.Set($"{prefix}_truth_note", truth.Note);
        if (!truth.ClearsDelete)
        {
            output.Set(skipKey, truth.Note);
            if (truth.Check == LibraryTruthVerdict.Skipped)
            {
                _logger.LogWarning("Refiner {Label} output cleanup: {Note}", logLabel, truth.Note);
            }

            return;
        }

        try
        {
            Directory.Delete(place.Folder, recursive: true);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            var human = $"Refiner could not remove the {noun} because a file or folder was in use or blocked ({exception.Message}).";
            output.Set(skipKey, human);
            output.Set(deletedKey, false);
            output.Set($"{prefix}_truth_check", LibraryTruthVerdict.Skipped);
            output.Set($"{prefix}_truth_note", human);
            _logger.LogWarning("Refiner {Label} output cleanup: {Reason}", logLabel, human);
            return;
        }

        output.Set(deletedKey, true);
        output.Set(skipKey, PyNull.Instance);
        var cascade = output.Get(cascadeKey) as PyList ?? new PyList();
        CascadeDeleteEmptyParents(Path.GetDirectoryName(place.Folder)!, place.OutputRoot, cascade, _logger);
        output.Set(cascadeKey, cascade);
    }

    /// <summary><c>_cascade_delete_empty_parents*</c>: remove empty parents up to, never including, <paramref name="root"/>.</summary>
    public static void CascadeDeleteEmptyParents(string firstParent, string root, PyList deleted, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(deleted);
        ArgumentNullException.ThrowIfNull(logger);
        var resolvedRoot = RemuxPassPaths.Resolve(root);
        var current = RemuxPassPaths.Resolve(firstParent);
        while (!RemuxPassPaths.SamePath(current, resolvedRoot))
        {
            if (!RemuxPassPaths.IsUnder(current, resolvedRoot))
            {
                logger.LogWarning("Refiner cleanup: stopped cascade because folder is outside the root ({Folder}).", current);
                break;
            }

            if (!Directory.Exists(current))
            {
                break;
            }

            try
            {
                if (Directory.EnumerateFileSystemEntries(current).Any())
                {
                    break;
                }

                Directory.Delete(current, recursive: false);
                deleted.Items.Add(new PyStr(current));
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                logger.LogWarning("Refiner cleanup: could not remove an empty parent folder ({Folder}): {Error}", current, exception.Message);
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

    private async Task<bool> MovieJobBlocksAsync(string relNorm, long? currentJobId, CancellationToken cancellationToken)
    {
        foreach (var job in await _data.ActiveRemuxJobsAsync(cancellationToken).ConfigureAwait(false))
        {
            if (currentJobId is { } exclude && job.Id == exclude)
            {
                continue;
            }

            var scope = "movie";
            var jobRel = string.Empty;
            if (job.PayloadJson is { } raw && PyStrings.Strip(raw).Length > 0)
            {
                PyJson data;
                try
                {
                    data = PyJsonParser.Parse(raw);
                }
                catch (PyJsonDecodeException)
                {
                    continue;
                }

                if (data is PyDict dict)
                {
                    scope = NormalizeScope(dict.Get("media_scope"));
                    if (dict.Get("relative_media_path") is PyStr jr && PyStrings.Strip(jr.Value).Length > 0)
                    {
                        jobRel = NormalizeRelativeForMatch(jr.Value);
                    }
                }
            }

            if (scope == "tv")
            {
                continue;
            }

            if (jobRel.Length > 0 && jobRel == relNorm)
            {
                return true;
            }
        }

        return false;
    }

    private async Task<bool> TvJobBlocksAsync(string outputRoot, string seasonFolder, long? currentJobId, CancellationToken cancellationToken)
    {
        foreach (var job in await _data.ActiveRemuxJobsAsync(cancellationToken).ConfigureAwait(false))
        {
            if (currentJobId is { } exclude && job.Id == exclude)
            {
                continue;
            }

            var scope = "movie";
            var jobRel = string.Empty;
            if (job.PayloadJson is { } raw && PyStrings.Strip(raw).Length > 0)
            {
                PyJson data;
                try
                {
                    data = PyJsonParser.Parse(raw);
                }
                catch (PyJsonDecodeException)
                {
                    continue;
                }

                if (data is PyDict dict)
                {
                    scope = dict.Get("media_scope") is PyStr js && string.Equals(PyStrings.Strip(js.Value), "tv", StringComparison.OrdinalIgnoreCase) ? "tv" : "movie";
                    if (dict.Get("relative_media_path") is PyStr jr && PyStrings.Strip(jr.Value).Length > 0)
                    {
                        jobRel = PyStrings.Strip(jr.Value);
                    }
                }
            }

            if (scope != "tv")
            {
                continue;
            }

            var relNorm = NormalizeRelativeForMatch(jobRel);
            if (relNorm.Length == 0)
            {
                continue;
            }

            var expected = RemuxPassPaths.Resolve(Path.Join(outputRoot, relNorm));
            if (!RemuxPassPaths.IsUnder(expected, outputRoot))
            {
                continue;
            }

            if (Path.GetDirectoryName(expected) is { } jobSeason && RemuxPassPaths.SamePath(jobSeason, seasonFolder))
            {
                return true;
            }
        }

        return false;
    }

    private static string NormalizeScope(PyJson? raw) =>
        raw is PyStr text && string.Equals(PyStrings.Strip(text.Value), "tv", StringComparison.OrdinalIgnoreCase) ? "tv" : "movie";

    /// <summary><c>iter_direct_child_refiner_media_candidates</c>, in name order.</summary>
    public static IReadOnlyList<string> DirectChildMediaCandidates(string folder)
    {
        try
        {
            return [.. Directory.EnumerateFiles(folder)
                .Where(path => RemuxRules.MediaExtensions.Contains(Path.GetExtension(path).ToLowerInvariant()))
                .Order(StringComparer.Ordinal)];
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return [];
        }
    }

    /// <summary><c>newest_mtime_seconds_under_tree</c>.</summary>
    public static double? NewestModifiedUnderTree(string root)
    {
        double? newest = null;
        try
        {
            foreach (var file in Directory.EnumerateFiles(root, "*", new EnumerationOptions { RecurseSubdirectories = true, AttributesToSkip = 0, IgnoreInaccessible = true }))
            {
                try
                {
                    var modified = Seconds(File.GetLastWriteTimeUtc(file));
                    newest = newest is null ? modified : Math.Max(newest.Value, modified);
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                }
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }

        return newest;
    }

    private double Now() => (_time.GetUtcNow() - DateTimeOffset.UnixEpoch).TotalSeconds;

    private static double Seconds(DateTime utc) => (utc - DateTime.UnixEpoch).TotalSeconds;

    private static string? ResolveOrNull(string raw)
    {
        try
        {
            return RemuxPassPaths.Resolve(raw);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException or System.Security.SecurityException)
        {
            return null;
        }
    }

    private static void InitFields(PyDict output, string prefix, string deleted, string path, string skip, string cascade)
    {
        SetDefault(output, deleted, PyBool.False);
        SetDefault(output, path, PyNull.Instance);
        SetDefault(output, skip, PyNull.Instance);
        SetDefault(output, $"{prefix}_truth_check", PyNull.Instance);
        SetDefault(output, $"{prefix}_truth_note", PyNull.Instance);
        SetDefault(output, $"{prefix}_age_seconds", PyNull.Instance);
        SetDefault(output, cascade, new PyList());
        SetDefault(output, $"{prefix}_dry_run", PyNull.Instance);
    }

    private static void Skip(PyDict output, string prefix, string skipKey, string reason)
    {
        output.Set(skipKey, reason);
        output.Set($"{prefix}_truth_check", LibraryTruthVerdict.Skipped);
        output.Set($"{prefix}_truth_note", reason);
    }

    /// <summary><c>dict.setdefault</c>.</summary>
    public static void SetDefault(PyDict output, string key, PyJson value)
    {
        ArgumentNullException.ThrowIfNull(output);
        if (!output.ContainsKey(key))
        {
            output.Set(key, value);
        }
    }
}
