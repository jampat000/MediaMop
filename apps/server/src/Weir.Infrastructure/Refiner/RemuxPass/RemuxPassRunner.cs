using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Core.Metrics;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>One pass's inputs (the keyword arguments of <c>run_refiner_file_remux_pass</c>).</summary>
public sealed record RemuxPassRequest
{
    public required RefinerPathRuntime Runtime { get; init; }
    public required string RelativeMediaPath { get; init; }

    /// <summary>Issue #545 item 5: which library this pass belongs to, so its file-row writes never touch another library's row.</summary>
    public long? LibraryId { get; init; }

    public RefinerRulesConfig? RulesConfig { get; init; }
    public long? MinFileAgeSeconds { get; init; }
    public string? MediaScope { get; init; } = "movie";
    public long? CurrentJobId { get; init; }
    public Action<PyDict>? ProgressReporter { get; init; }
    public long MinInputFileSizeMb { get; init; }
    public long MinimumFreeDiskSpaceMb { get; init; }
    public bool PassThroughUnchanged { get; init; }

    /// <summary>The hand-off this file came from, when it did: its release name feeds the original-language lookup.</summary>
    public HandoffOrigin? Origin { get; init; }

    /// <summary>
    /// An operator's hand-picked track choice (issue #501). When set, the pass re-probes, checks the source fingerprint
    /// and every kept index against <see cref="ManualPlanFingerprint"/>, and builds the plan straight from the choice
    /// instead of calling <see cref="RemuxRules.PlanRemux"/>.
    /// </summary>
    public ManualPlanChoice? ManualPlan { get; init; }

    /// <summary>The source fingerprint recorded when the operator chose the tracks in <see cref="ManualPlan"/>.</summary>
    public SourceFingerprint? ManualPlanFingerprint { get; init; }
}

/// <summary>
/// Per-file ffprobe, plan, optional ffmpeg remux, publish and post-success cleanup (port of <c>file_remux_pass/run.py</c>).
/// Returns the result dictionary the handler records, in the reference's key order.
/// </summary>
/// <remarks>
/// Deliberate differences from the reference, each tied to an issue:
/// <list type="bullet">
/// <item>#539 item 5: the full-read integrity check runs on every platform, not only off Windows, with the probed duration so a
/// truncated Matroska file is caught (#539 item 3).</item>
/// <item>#539 item 2: the acceleration flags decided here reach the executed ffmpeg command, not only the recorded argv.</item>
/// <item>#537 item 4: when the rule set keeps the original language, the metadata lookup decides the preferred audio.</item>
/// </list>
/// </remarks>
public sealed class RemuxPassRunner
{
    private const string PlaceholderName = "planned-ffmpeg-destination-placeholder.mkv";

    private readonly MediaTools _tools;
    private readonly IMediaToolResolver _resolver;
    private readonly IRemuxPassFileFacts _facts;
    private readonly OutputFolderCleanup _outputCleanup;
    private readonly ITvSeasonFolderCleanup _tvSeasonCleanup;
    private readonly IOriginalLanguageLookup _originalLanguage;
    private readonly RuntimeMetricsStore? _metrics;
    private readonly RemuxPassSettings _settings;
    private readonly TimeProvider _time;
    private readonly ILogger _logger;
    private readonly IOutputOwnership? _ownership;

    public RemuxPassRunner(
        MediaTools tools,
        IMediaToolResolver resolver,
        IRemuxPassFileFacts facts,
        IPostSuccessCleanupData cleanupData,
        ITvSeasonFolderCleanup tvSeasonCleanup,
        IOriginalLanguageLookup originalLanguage,
        RemuxPassSettings settings,
        TimeProvider time,
        ILogger<RemuxPassRunner> logger,
        RuntimeMetricsStore? metrics = null,
        IOutputOwnership? ownership = null)
    {
        _tools = tools ?? throw new ArgumentNullException(nameof(tools));
        _resolver = resolver ?? throw new ArgumentNullException(nameof(resolver));
        _facts = facts ?? throw new ArgumentNullException(nameof(facts));
        _tvSeasonCleanup = tvSeasonCleanup ?? throw new ArgumentNullException(nameof(tvSeasonCleanup));
        _originalLanguage = originalLanguage ?? throw new ArgumentNullException(nameof(originalLanguage));
        _settings = settings ?? throw new ArgumentNullException(nameof(settings));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _metrics = metrics;
        _ownership = ownership;
        _outputCleanup = new OutputFolderCleanup(cleanupData, time, logger, settings.MovieOutputCleanupMinAgeSeconds, settings.TvOutputCleanupMinAgeSeconds);
    }

    /// <summary>Test seam: whether the Windows hard-link fast path is used (<c>_hardlink_fast_path_supported</c>).</summary>
    internal bool HardlinkFastPathSupported { get; init; } = OperatingSystem.IsWindows();

    /// <summary>Test seam: free bytes on the volume holding a path.</summary>
    internal Func<string, long>? FreeBytes { get; init; }

    /// <summary><c>run_refiner_file_remux_pass</c>: reserve the source against writers for the complete pass, then run it.</summary>
    public async Task<PyDict> RunAsync(RemuxPassRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        string? source;
        try
        {
            source = RemuxPassPaths.ResolveMediaFileUnderRoot(request.Runtime.WatchedFolder, request.RelativeMediaPath);
        }
        catch (ArgumentException)
        {
            source = null;
        }

        if (source is null || !File.Exists(source))
        {
            return await RunInnerAsync(request, new SourceFingerprint(0, 0, 0, 0), cancellationToken).ConfigureAwait(false);
        }

        var (guard, problem) = SourceFiles.AcquireReadGuard(source);
        if (guard is null)
        {
            return SourceNotReady(request.RelativeMediaPath, problem ?? "Weir is waiting until no other program is writing this file.", source);
        }

        using (guard)
        {
            SourceFingerprint fingerprint;
            try
            {
                fingerprint = SourceFiles.Fingerprint(source);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                return SourceNotReady(request.RelativeMediaPath, $"Weir could not read this file safely ({exception.Message}), so it will wait.", source);
            }

            return await RunInnerAsync(request, fingerprint, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task<PyDict> RunInnerAsync(RemuxPassRequest request, SourceFingerprint expected, CancellationToken cancellationToken)
    {
        var relativeMediaPath = request.RelativeMediaPath;
        var runtime = request.Runtime;
        var scope = NormalizeScope(request.MediaScope);
        var passThrough = request.PassThroughUnchanged;
        var report = request.ProgressReporter;

        string src;
        try
        {
            src = RemuxPassPaths.ResolveMediaFileUnderRoot(runtime.WatchedFolder, relativeMediaPath);
        }
        catch (ArgumentException exception)
        {
            return FailBefore(relativeMediaPath, exception.Message);
        }

        var inspected = src;
        var exists = File.Exists(src) || Directory.Exists(src);
        var isFile = File.Exists(src);
        var suffix = Path.GetExtension(src).ToLowerInvariant();
        if (!exists)
        {
            return FailBefore(
                relativeMediaPath,
                "Weir could not find this file under the saved watched folder. Check the library path or restore the file, then try again.",
                inspected);
        }

        if (!isFile)
        {
            return FailBefore(
                relativeMediaPath,
                "This path is not a regular media file under the saved watched folder. Choose a file, then try again.",
                inspected);
        }

        if (!RemuxRules.MediaExtensions.Contains(suffix))
        {
            return FailBefore(
                relativeMediaPath,
                $"Refiner does not process {(suffix.Length > 0 ? suffix : "this")} files in this pass. " +
                "Use a supported media file or update the library's media types, then try again.",
                inspected);
        }

        var minSizeMb = Math.Max(0, request.MinInputFileSizeMb);
        if (minSizeMb > 0 && !passThrough)
        {
            long sourceSize;
            try
            {
                sourceSize = new FileInfo(src).Length;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                return FailBefore(relativeMediaPath, $"Refiner could not read the source file size: {exception.Message}", inspected);
            }

            var sourceMb = FileLifecycle.BytesToMb(sourceSize);
            if (sourceSize < minSizeMb * 1024 * 1024)
            {
                return SkipGuardrail(
                    relativeMediaPath,
                    $"Skipped: file below minimum size ({sourceMb.ToString("F1", CultureInfo.InvariantCulture)} MB < {minSizeMb.ToString(CultureInfo.InvariantCulture)} MB).",
                    "minimum_input_file_size",
                    inspected,
                    new PyDict()
                        .Set("source_size_bytes", sourceSize)
                        .Set("source_size_mb", Math.Round(sourceMb, 1, MidpointRounding.ToEven))
                        .Set("minimum_input_file_size_mb", minSizeMb)
                        .Set("media_scope", scope));
            }
        }

        var minAge = Math.Max(0, request.MinFileAgeSeconds ?? _settings.WatchedFolderMinFileAgeSeconds);
        if (minAge > 0)
        {
            double age;
            try
            {
                age = (_time.GetUtcNow() - new DateTimeOffset(File.GetLastWriteTimeUtc(src))).TotalSeconds;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                age = -1;
            }

            if (age < minAge)
            {
                return FailBefore(
                    relativeMediaPath,
                    "file was modified too recently for Refiner safety guardrails " +
                    $"(minimum age {minAge.ToString(CultureInfo.InvariantCulture)}s, current age {((long)Math.Max(0, Math.Truncate(age))).ToString(CultureInfo.InvariantCulture)}s)",
                    inspected);
            }
        }

        JsonElement probeJson;
        try
        {
            probeJson = await _tools.FfprobeJsonAsync(src, probeSizeMb: _settings.ProbeSizeMb, analyzeDurationSeconds: _settings.AnalyzeDurationSeconds, cancellationToken: cancellationToken)
                .ConfigureAwait(false);
        }
        catch (MediaUnreadableException exception)
        {
            return FailBefore(
                relativeMediaPath,
                $"Weir could not read this file's contents, so the file itself looks damaged: {exception.Message}",
                inspected,
                // Evidence the release is bad, so a library set to reject can act on it (#471).
                new PyDict().Set("content_unusable", true));
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return FailBefore(relativeMediaPath, $"ffprobe failed: {exception.Message}", inspected);
        }

        IReadOnlyList<string> sourceWarnings;
        try
        {
            sourceWarnings = await _tools.ProbeWarningLinesAsync(src, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            // #500: a baseline that could not be read is treated as "no known warnings", so a genuine new warning on
            // the output still fails validation instead of being silently accepted.
            _logger.LogWarning(exception, "Refiner could not read the source file's ffprobe warnings for {Path}.", relativeMediaPath);
            sourceWarnings = [];
        }

        var probe = new ProbeResult(probeJson);
        var (video, audio, subtitles) = RemuxRules.SplitStreams(probe);
        var watchedRoot = RemuxPassPaths.Resolve(runtime.WatchedFolder);
        if (video.Count == 0)
        {
            return FailBefore(
                relativeMediaPath,
                "Refiner only processes movie and TV files that contain a video stream. " +
                "This file contains no video, so it was rejected before any output was written.",
                inspected,
                new PyDict()
                    .Set("rejection_kind", "no_video_stream")
                    .Set("media_scope", scope)
                    .Set("refiner_watched_folder_resolved", watchedRoot));
        }

        // Measured once and recorded, so the next enqueue can weight this file (#338).
        var (width, height) = RemuxPassMedia.VideoDimensions(video);
        var duration = RemuxPassMedia.ProbeDurationSeconds(probe);
        var codec = PyStrings.Strip(video[0].CodecName);
        await _facts.RecordMeasuredMediaFactsAsync(
            new MeasuredMediaFacts(
                relativeMediaPath,
                width,
                height,
                codec.Length > 0 ? codec : null,
                audio.Count,
                subtitles.Count,
                duration,
                [.. audio.Select(stream => RemuxPassMedia.TruthyText(stream.Get("codec_name")))],
                RemuxPassMedia.VideoBitDepth(video[0]),
                request.LibraryId),
            cancellationToken).ConfigureAwait(false);

        try
        {
            // Deliberate divergence (#539 item 5): read the whole primary video on every platform, not only off Windows.
            await _tools.ValidateMediaIntegrityAsync(src, duration, cancellationToken).ConfigureAwait(false);
            AssertSourceUnchanged(src, expected);
        }
        catch (MediaCompletenessException exception)
        {
            return SourceNotReady(relativeMediaPath, exception.Message, inspected);
        }

        var config = request.RulesConfig ?? RemuxRules.DefaultConfig();
        PyDict? originalLanguage = null;
        if (!passThrough && request.ManualPlan is null && config.OriginalLanguage is { Enabled: true } originalRules)
        {
            (config, originalLanguage) = await ApplyOriginalLanguageAsync(config, originalRules, scope, relativeMediaPath, request.Origin, audio, cancellationToken)
                .ConfigureAwait(false);
        }

        RemuxPlan? plan;
        if (request.ManualPlan is { } manualChoice)
        {
            // Issue #501: the operator's choice is authoritative. A stale fingerprint or an index that no longer
            // exists (or changed type) both mean the same thing to the operator, so both fail with the same sentence.
            var splitForManual = new SplitProbeStreams(video, audio, subtitles);
            var kinds = ManualTrackPlan.ClassifyIndices(splitForManual);
            var stillValid = request.ManualPlanFingerprint is { } expectedManualFingerprint
                && expectedManualFingerprint == expected
                && ManualTrackPlan.TryValidate(manualChoice, kinds, out _);
            if (!stillValid)
            {
                return FailBefore(relativeMediaPath, ManualTrackPlan.ChangedMessage, inspected);
            }

            plan = ManualTrackPlan.BuildPlan(splitForManual, manualChoice);
        }
        else
        {
            plan = passThrough
                ? RemuxPassMedia.PassThroughPlan(video, audio, subtitles)
                : RemuxRules.PlanRemux(video, audio, subtitles, config, RemuxRules.AttachmentStreams(probe));
        }

        if (plan is null)
        {
            return FailBefore(
                relativeMediaPath,
                "remux plan could not be built (no retainable audio)",
                inspected,
                new PyDict()
                    .Set("rejection_kind", "no_retainable_audio")
                    .Set("media_scope", scope)
                    .Set("refiner_watched_folder_resolved", watchedRoot));
        }

        var remuxNeeded = !passThrough && RemuxRules.IsRemuxRequired(plan, audio, subtitles);
        var audioBefore = RemuxDisplay.AudioBeforeLineFromProbe(audio);
        var audioAfter = RemuxDisplay.AudioAfterLineFromPlan(plan);
        var metadataRemoved = RemuxDisplay.MetadataRemovedLineFromPlan(plan);
        var subsBefore = RemuxDisplay.SubtitleBeforeLineFromProbe(subtitles);
        var subsAfter = RemuxDisplay.SubtitleAfterLineFromPlan(plan, !passThrough && config.SubtitleMode == RemuxRuleValues.SubtitleModeRemoveAll);

        var workDir = runtime.WorkFolderEffective;
        AccelerationDecision? hardware = null;
        IReadOnlyList<string> argv = [];
        if (!passThrough)
        {
            var (_, ffmpeg) = _resolver.Resolve();
            // Decided before the argv is built, because the flags go into it; a device that is busy or absent falls back (#345).
            hardware = HardwareAcceleration.Decide(
                new HardwareSettings
                {
                    Mode = HardwareAcceleration.NormalizeDecodeMode(runtime.HardwareDecodeMode),
                    Device = runtime.HardwareDevice ?? string.Empty,
                    DisabledVendors = HardwareAcceleration.ParseDisabledVendors(runtime.HardwareDisabledVendorsCsv),
                    Strictness = HardwareAcceleration.NormalizeStrictness(runtime.FfmpegStrictness),
                },
                await _tools.DetectAccelerationAsync(ffmpeg, cancellationToken).ConfigureAwait(false));
            argv = FfmpegCommands.BuildRemuxArgv(ffmpeg, src, Path.Join(workDir, PlaceholderName), plan, hardware.ArgvFlags);
        }

        var output = new PyDict()
            .Set("ok", true)
            .Set("outcome", RemuxPassOutcomes.LiveOutputWritten)
            .Set("relative_media_path", relativeMediaPath)
            .Set("inspected_source_path", inspected)
            .Set("refiner_watched_folder_resolved", watchedRoot)
            .Set("stream_counts", new PyDict().Set("video", video.Count).Set("audio", audio.Count).Set("subtitle", subtitles.Count))
            .Set("preflight_status", "ok")
            .Set("preflight_reason", passThrough
                ? "ffprobe completed and the operator's pass-through request was validated"
                : "ffprobe completed and remux plan was evaluated")
            .Set("preflight_probe_settings", new PyDict().Set("probe_size_mb", _settings.ProbeSizeMb).Set("analyze_duration_seconds", _settings.AnalyzeDurationSeconds))
            .Set("plan_summary", RemuxPassVisibility.SummarizeRemuxPlan(plan))
            .Set("audio_before", audioBefore)
            .Set("audio_after", audioAfter)
            .Set("subs_before", subsBefore)
            .Set("subs_after", subsAfter)
            .Set("removed_audio", StringList(plan.RemovedAudio))
            .Set("removed_subtitles", StringList(plan.RemovedSubtitles))
            .Set("removed_images", StringList(plan.RemovedImages))
            .Set("removed_attachments", StringList(plan.RemovedAttachments))
            .Set("metadata_removed", metadataRemoved)
            .Set("remux_required", remuxNeeded)
            .Set("pass_through_unchanged", passThrough)
            .Set("ffmpeg_argv", StringList(argv))
            .Set("audio_selection_notes", StringList(plan.AudioSelectionNotes))
            .Set("media_scope", scope)
            .Set("source_fingerprint", new PyDict()
                .Set("device", new PyInt(expected.Device))
                .Set("inode", new PyInt(expected.Inode))
                .Set("size_bytes", expected.SizeBytes)
                .Set("modified_time_ns", expected.ModifiedTimeNs));
        if (originalLanguage is not null)
        {
            output.Set("original_language", originalLanguage);
        }

        var collisionPolicy = OutputCollision.NormalizePolicy(runtime.OutputCollisionPolicy);
        var sidecarPatterns = SidecarMigration.ParsePatterns(runtime.SidecarPatternsCsv);
        var outDir = RemuxPassPaths.Resolve(runtime.OutputFolder);

        if (runtime.WorkFolderIsDefault)
        {
            Directory.CreateDirectory(workDir);
        }
        else if (!Directory.Exists(workDir))
        {
            return FailBefore(relativeMediaPath, "Refiner work/temp folder is missing on disk (custom path must exist before a live pass).", inspected);
        }

        var relative = RemuxPassPaths.RelativeTo(src, watchedRoot)!;
        var context = new PassContext(request, src, inspected, scope, watchedRoot, outDir, expected, audio.Count, duration, minAge, plan, probeJson, sourceWarnings);
        if (!remuxNeeded)
        {
            return await PlaceUnchangedAsync(context, output, plan, argv, audioBefore, audioAfter, subsBefore, subsAfter, relative, collisionPolicy, sidecarPatterns, cancellationToken)
                .ConfigureAwait(false);
        }

        return await RemuxAndPublishAsync(context, output, plan, argv, hardware!, audioBefore, audioAfter, subsBefore, subsAfter, relative, collisionPolicy, sidecarPatterns, cancellationToken)
            .ConfigureAwait(false);
    }

    private sealed record PassContext(
        RemuxPassRequest Request,
        string Source,
        string Inspected,
        string Scope,
        string WatchedRoot,
        string OutputDirectory,
        SourceFingerprint Expected,
        int ExpectedAudio,
        double? Duration,
        long MinAge,
        RemuxPlan Plan,
        JsonElement SourceProbe,
        IReadOnlyList<string> SourceWarnings)
    {
        public string RelativeMediaPath => Request.RelativeMediaPath;
    }

    private async Task<PyDict> PlaceUnchangedAsync(
        PassContext context,
        PyDict output,
        RemuxPlan plan,
        IReadOnlyList<string> argv,
        string audioBefore,
        string audioAfter,
        string subsBefore,
        string subsAfter,
        string relative,
        string collisionPolicy,
        IReadOnlyList<string> sidecarPatterns,
        CancellationToken cancellationToken)
    {
        var request = context.Request;
        var passThrough = request.PassThroughUnchanged;
        var report = request.ProgressReporter;
        var relativeMediaPath = context.RelativeMediaPath;
        output.Set("outcome", RemuxPassOutcomes.LiveSkippedNotRequired);
        output.Set("refiner_output_folder_resolved", context.OutputDirectory);
        if (passThrough)
        {
            output.Set("after_track_lines_meaning", "No audio, subtitle, or metadata rules were applied because the operator chose Pass through unchanged.");
            output.Set("reason",
                "The operator bypassed Refiner rules for this edge case. Weir validated and placed the unchanged file " +
                "in the output folder before running normal post-success source cleanup.");
        }
        else
        {
            output.Set("after_track_lines_meaning", "No ffmpeg run was needed because the file already matched the saved Refiner rules.");
            output.Set("reason", "The file already matched the saved Refiner rules, so Refiner placed it in the output folder without rewriting it.");
        }

        var finalSkip = Path.Join(context.OutputDirectory, relative);
        var disk = FileLifecycle.CheckMinimumFreeDiskSpace(finalSkip, request.MinimumFreeDiskSpaceMb, FreeBytes);
        if (!disk.Ok)
        {
            return SkipGuardrail(
                relativeMediaPath,
                disk.Message,
                "minimum_free_disk_space",
                context.Inspected,
                new PyDict()
                    .Set("disk_checked_path", disk.CheckedPath)
                    .Set("disk_free_mb", Math.Round(disk.FreeMb, 1, MidpointRounding.ToEven))
                    .Set("minimum_free_disk_space_mb", disk.RequiredMb)
                    .Set("media_scope", context.Scope)
                    .Set("refiner_output_folder_resolved", context.OutputDirectory)
                    .Set("stream_counts", output["stream_counts"])
                    .Set("plan_summary", output["plan_summary"])
                    .Set("audio_before", audioBefore)
                    .Set("audio_after", audioAfter)
                    .Set("subs_before", subsBefore)
                    .Set("subs_after", subsAfter)
                    .Set("remux_required", false));
        }

        // The unchanged-copy path collides exactly like the remux path does.
        var collision = OutputCollision.Decide(finalSkip, context.Source, context.Source, collisionPolicy);
        var copyStarted = _time.GetTimestamp();
        var lastPercent = -1.0;
        var lastAt = copyStarted;
        void ReportCopyProgress(long copied, long total)
        {
            if (report is null)
            {
                return;
            }

            var now = _time.GetTimestamp();
            var elapsed = Math.Max(0.001, _time.GetElapsedTime(copyStarted, now).TotalSeconds);
            var percent = total <= 0 ? 100.0 : Math.Min(100.0, copied * 100.0 / total);
            if (percent < 100.0 && percent - lastPercent < 1.0 && _time.GetElapsedTime(lastAt, now).TotalSeconds < 2.0)
            {
                return;
            }

            lastPercent = percent;
            lastAt = now;
            var bytesPerSecond = copied / elapsed;
            var remaining = Math.Max(0, total - copied);
            report(new PyDict()
                .Set("status", "processing")
                .Set("percent", percent)
                .Set("eta_seconds", bytesPerSecond > 0 ? PyJson.Of(remaining / bytesPerSecond) : PyNull.Instance)
                .Set("elapsed_seconds", elapsed)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("media_scope", context.Scope)
                .Set("processed_bytes", copied)
                .Set("total_bytes", total)
                .Set("speed", $"{(bytesPerSecond / (1024 * 1024)).ToString("F1", CultureInfo.InvariantCulture)} MB/s")
                .Set("message", passThrough
                    ? "Weir is passing this file through unchanged."
                    : "Weir is copying the unchanged file to the output folder."));
        }

        bool replacedExisting;
        string method;
        try
        {
            if (collision.Wrote)
            {
                finalSkip = collision.Destination;
                (replacedExisting, method) = await CopyUnchangedSourceToOutputAsync(context, finalSkip, ReportCopyProgress, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                (replacedExisting, method) = (false, "skipped_by_collision_policy");
            }
        }
        catch (MediaCompletenessException exception)
        {
            return SourceNotReady(relativeMediaPath, exception.Message, context.Inspected);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            report?.Invoke(new PyDict()
                .Set("status", "failed")
                .Set("percent", PyNull.Instance)
                .Set("eta_seconds", PyNull.Instance)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("media_scope", context.Scope)
                .Set("message", "Refiner could not copy this unchanged file to the output folder.")
                .Set("reason", exception.Message));
            return new PyDict()
                .Set("ok", false)
                .Set("outcome", RemuxPassOutcomes.FailedDuringExecution)
                .Set("preflight_status", "ok")
                .Set("preflight_reason", "ffprobe completed and remux plan was evaluated")
                .Set("reason", exception.Message)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("refiner_watched_folder_resolved", context.WatchedRoot)
                .Set("refiner_output_folder_resolved", context.OutputDirectory)
                .Set("stream_counts", output["stream_counts"])
                .Set("plan_summary", output["plan_summary"])
                .Set("audio_before", audioBefore)
                .Set("audio_after", audioAfter)
                .Set("subs_before", subsBefore)
                .Set("subs_after", subsAfter)
                .Set("remux_required", false)
                .Set("ffmpeg_argv", StringList(argv))
                .Set("audio_selection_notes", StringList(plan.AudioSelectionNotes));
        }

        output.Set("output_file", RemuxPassPaths.Resolve(finalSkip));
        output.Set("output_replaced_existing", replacedExisting);
        output.Set("output_collision_policy", collision.Policy);
        output.Set("output_collision_action", collision.Action);
        output.Set("output_collision_reason", collision.Reason);
        await _facts.RecordOutputCollisionAsync(relativeMediaPath, collision, request.LibraryId, cancellationToken).ConfigureAwait(false);
        output.Set("output_copied_without_remux", true);
        output.Set("unchanged_output_method", method);
        output.Set("live_mutations_skipped", false);
        await MigrateSidecarsBeforeCleanupAsync(context.Source, finalSkip, sidecarPatterns, request.Runtime.PreserveOriginalTimestamps, output).ConfigureAwait(false);
        await HandleCleanupAfterSuccessAsync(context, output, finalSkip, cancellationToken).ConfigureAwait(false);
        try
        {
            output.Set("unchanged_output_method", await DetachHardlinkedOutputIfSourceRemainsAsync(context, finalSkip, method, ReportCopyProgress).ConfigureAwait(false));
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            FileLifecycle.BestEffortDelete(finalSkip);
            output.Set("ok", false);
            output.Set("outcome", RemuxPassOutcomes.FailedDuringExecution);
            output.Set("reason",
                "Weir preserved the watched source because cleanup could not finish, but could not detach the " +
                $"validated output from that source safely. The unsafe output link was removed. The system reported: {exception.Message}");
            output.Remove("output_file");
            return output;
        }

        await RunScopeOutputCleanupAsync(context, output, finalSkip, cancellationToken).ConfigureAwait(false);
        return output;
    }

    private async Task<PyDict> RemuxAndPublishAsync(
        PassContext context,
        PyDict output,
        RemuxPlan plan,
        IReadOnlyList<string> argv,
        AccelerationDecision hardware,
        string audioBefore,
        string audioAfter,
        string subsBefore,
        string subsAfter,
        string relative,
        string collisionPolicy,
        IReadOnlyList<string> sidecarPatterns,
        CancellationToken cancellationToken)
    {
        var request = context.Request;
        var report = request.ProgressReporter;
        var relativeMediaPath = context.RelativeMediaPath;
        var src = context.Source;
        var workDir = request.Runtime.WorkFolderEffective;
        string final;
        CollisionDecision collision;
        bool replacedExisting;
        try
        {
            var workDisk = FileLifecycle.CheckMinimumFreeDiskSpace(Path.Join(workDir, $".{Path.GetFileName(src)}.work-preflight"), request.MinimumFreeDiskSpaceMb, FreeBytes);
            if (!workDisk.Ok)
            {
                return SkipGuardrail(
                    relativeMediaPath,
                    workDisk.Message,
                    "minimum_free_disk_space",
                    context.Inspected,
                    new PyDict()
                        .Set("disk_checked_path", workDisk.CheckedPath)
                        .Set("disk_free_mb", Math.Round(workDisk.FreeMb, 1, MidpointRounding.ToEven))
                        .Set("minimum_free_disk_space_mb", workDisk.RequiredMb)
                        .Set("media_scope", context.Scope)
                        .Set("stream_counts", output["stream_counts"])
                        .Set("plan_summary", output["plan_summary"])
                        .Set("audio_before", audioBefore)
                        .Set("audio_after", audioAfter)
                        .Set("subs_before", subsBefore)
                        .Set("subs_after", subsAfter)
                        .Set("remux_required", true));
            }

            report?.Invoke(new PyDict()
                .Set("status", "processing")
                .Set("percent", 0.0)
                .Set("eta_seconds", PyNull.Instance)
                .Set("elapsed_seconds", 0L)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("media_scope", context.Scope)
                .Set("stream_counts", output["stream_counts"])
                .Set("duration_seconds", NullableFloat(context.Duration))
                .Set("message", "Refiner has started writing the cleaned-up file."));
            var tmp = await _tools.RemuxToTempFileAsync(
                src,
                workDir,
                plan,
                context.SourceProbe,
                context.SourceWarnings,
                report is null
                    ? null
                    : update => report(ProgressWithUpdate(
                        new PyDict()
                            .Set("status", "processing")
                            .Set("relative_media_path", relativeMediaPath)
                            .Set("inspected_source_path", context.Inspected)
                            .Set("media_scope", context.Scope)
                            .Set("stream_counts", output["stream_counts"])
                            .Set("duration_seconds", NullableFloat(context.Duration))
                            .Set("message", "Refiner is writing the cleaned-up file."),
                        update)),
                context.Duration,
                hardware,
                cancellationToken).ConfigureAwait(false);
            try
            {
                AssertSourceUnchanged(src, context.Expected);
            }
            catch (MediaCompletenessException)
            {
                FileLifecycle.BestEffortDelete(tmp);
                throw;
            }

            final = Path.Join(context.OutputDirectory, relative);
            var outputDisk = FileLifecycle.CheckMinimumFreeDiskSpace(final, request.MinimumFreeDiskSpaceMb, FreeBytes);
            if (!outputDisk.Ok)
            {
                FileLifecycle.BestEffortDelete(tmp);
                return SkipGuardrail(
                    relativeMediaPath,
                    outputDisk.Message,
                    "minimum_free_disk_space",
                    context.Inspected,
                    new PyDict()
                        .Set("disk_checked_path", outputDisk.CheckedPath)
                        .Set("disk_free_mb", Math.Round(outputDisk.FreeMb, 1, MidpointRounding.ToEven))
                        .Set("minimum_free_disk_space_mb", outputDisk.RequiredMb)
                        .Set("media_scope", context.Scope)
                        .Set("refiner_output_folder_resolved", context.OutputDirectory)
                        .Set("stream_counts", output["stream_counts"])
                        .Set("plan_summary", output["plan_summary"])
                        .Set("audio_before", audioBefore)
                        .Set("audio_after", audioAfter)
                        .Set("subs_before", subsBefore)
                        .Set("subs_after", subsAfter)
                        .Set("remux_required", true));
            }

            Directory.CreateDirectory(Path.GetDirectoryName(final)!);
            // A collision used to be silent; the policy and the decision are both recorded now (#349).
            collision = OutputCollision.Decide(final, src, tmp, collisionPolicy);
            replacedExisting = collision.ReplacedExisting;
            if (collision.Wrote)
            {
                final = collision.Destination;
                Directory.CreateDirectory(Path.GetDirectoryName(final)!);
                FileLifecycle.SafeFinalizeFile(tmp, final, _ownership);
            }
        }
        catch (MediaCompletenessException exception)
        {
            report?.Invoke(new PyDict()
                .Set("status", "waiting")
                .Set("percent", PyNull.Instance)
                .Set("eta_seconds", PyNull.Instance)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("media_scope", context.Scope)
                .Set("message", "Refiner is waiting for this file to finish downloading.")
                .Set("reason", exception.Message));
            return SourceNotReady(relativeMediaPath, exception.Message, context.Inspected);
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            report?.Invoke(new PyDict()
                .Set("status", "failed")
                .Set("percent", PyNull.Instance)
                .Set("eta_seconds", PyNull.Instance)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("media_scope", context.Scope)
                .Set("message", "Refiner could not finish this file.")
                .Set("reason", exception.Message));
            return new PyDict()
                .Set("ok", false)
                .Set("outcome", RemuxPassOutcomes.FailedDuringExecution)
                .Set("preflight_status", "ok")
                .Set("preflight_reason", "ffprobe completed and remux plan was evaluated")
                .Set("reason", exception.Message)
                .Set("relative_media_path", relativeMediaPath)
                .Set("inspected_source_path", context.Inspected)
                .Set("refiner_watched_folder_resolved", context.WatchedRoot)
                .Set("stream_counts", output["stream_counts"])
                .Set("plan_summary", output["plan_summary"])
                .Set("audio_before", audioBefore)
                .Set("audio_after", audioAfter)
                .Set("subs_before", subsBefore)
                .Set("subs_after", subsAfter)
                .Set("remux_required", true)
                .Set("ffmpeg_argv", StringList(argv))
                .Set("audio_selection_notes", StringList(plan.AudioSelectionNotes))
                .Set("after_track_lines_meaning", "Remux failed partway; lines above were computed before ffmpeg — output file was not committed.");
        }

        var resolvedFinal = RemuxPassPaths.Resolve(final);
        output.Set("output_file", resolvedFinal);
        output.Set("output_replaced_existing", replacedExisting);
        output.Set("refiner_output_folder_resolved", context.OutputDirectory);
        output.Set("hardware_method", hardware.Method.Length > 0 ? hardware.Method : null);
        output.Set("hardware_fell_back_to_software", hardware.FellBackToSoftware);
        output.Set("hardware_reason", hardware.Reason);
        output.Set("output_collision_policy", collision.Policy);
        output.Set("output_collision_action", collision.Action);
        // For the person asking "why is there no new output for this file".
        output.Set("output_collision_reason", collision.Reason);
        await _facts.RecordOutputCollisionAsync(relativeMediaPath, collision, context.Request.LibraryId, cancellationToken).ConfigureAwait(false);
        if (!collision.Wrote || replacedExisting)
        {
            output.Set("output_replacement_note", collision.Reason);
        }

        output.Set("after_track_lines_meaning",
            "Live remux finished; before = source probe; after = planned disposition (copy remux — " +
            "ffprobe of the written file was used for validation only).");
        try
        {
            var saved = new FileInfo(src).Length - new FileInfo(final).Length;
            if (saved > 0)
            {
                _metrics?.RecordModuleSavings("refiner", saved);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }

        report?.Invoke(new PyDict()
            .Set("status", "finishing")
            .Set("percent", 100.0)
            .Set("eta_seconds", 0L)
            .Set("relative_media_path", relativeMediaPath)
            .Set("inspected_source_path", context.Inspected)
            .Set("output_file", resolvedFinal)
            .Set("media_scope", context.Scope)
            .Set("message", "The cleaned-up file was written. Refiner is doing final safety checks."));
        await MigrateSidecarsBeforeCleanupAsync(src, final, sidecarPatterns, request.Runtime.PreserveOriginalTimestamps, output).ConfigureAwait(false);
        await HandleCleanupAfterSuccessAsync(context, output, final, cancellationToken).ConfigureAwait(false);
        await RunScopeOutputCleanupAsync(context, output, final, cancellationToken).ConfigureAwait(false);
        report?.Invoke(new PyDict()
            .Set("status", "finished")
            .Set("percent", 100.0)
            .Set("eta_seconds", 0L)
            .Set("relative_media_path", relativeMediaPath)
            .Set("inspected_source_path", context.Inspected)
            .Set("output_file", resolvedFinal)
            .Set("media_scope", context.Scope)
            .Set("message", "Refiner finished processing this file."));
        return output;
    }

    /// <summary><c>{**base, **update}</c> for an ffmpeg progress block.</summary>
    private static PyDict ProgressWithUpdate(PyDict body, FfmpegProgressUpdate update) =>
        body
            .Set("percent", NullableFloat(update.Percent))
            .Set("eta_seconds", update.EtaSeconds)
            .Set("elapsed_seconds", update.ElapsedSeconds)
            .Set("processed_seconds", NullableFloat(update.ProcessedSeconds))
            .Set("speed", update.Speed)
            .Set("progress", update.Progress);

    /// <summary><c>_copy_unchanged_source_to_output</c>: the Windows hard link when it can be one, else a validated copy.</summary>
    private async Task<(bool ReplacedExisting, string Method)> CopyUnchangedSourceToOutputAsync(PassContext context, string final, Action<long, long> progress, CancellationToken cancellationToken)
    {
        var src = context.Source;
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(final))!);
        var replacedExisting = File.Exists(final) || Directory.Exists(final);
        if (replacedExisting && RemuxPassPaths.SamePath(RemuxPassPaths.Resolve(final), src))
        {
            throw new InvalidOperationException("Refiner output path resolves to the watched source file; output and watched folders must differ.");
        }

        async Task ValidateStaged(string staged)
        {
            await _tools.ValidateStagedOutputAsync(staged, src, context.SourceProbe, context.Plan, context.SourceWarnings, cancellationToken).ConfigureAwait(false);
            AssertSourceUnchanged(src, context.Expected);
        }

        // Windows' held source handle denies writers for the complete pass, which makes a staged hard link safe and turns a
        // same-volume no-change file into metadata work. Elsewhere locks are advisory, so the independent copy stays.
        if (HardlinkFastPathSupported && await FileLifecycle.TryHardlinkToFinalAsync(src, final, ValidateStaged, _ownership).ConfigureAwait(false))
        {
            var size = new FileInfo(src).Length;
            progress(size, size);
            return (replacedExisting, "validated_hardlink");
        }

        await FileLifecycle.SafeCopyToFinalAsync(src, final, ValidateStaged, progress, ownership: _ownership).ConfigureAwait(false);
        return (replacedExisting, "validated_copy");
    }

    /// <summary>
    /// <c>_detach_hardlinked_output_if_source_remains</c>: when a safety gate kept the watched source, break the shared file so a
    /// later writer cannot change the published output through the watched name.
    /// </summary>
    private async Task<string> DetachHardlinkedOutputIfSourceRemainsAsync(PassContext context, string final, string method, Action<long, long> progress)
    {
        if (method != "validated_hardlink" || !File.Exists(context.Source))
        {
            return method;
        }

        await FileLifecycle.SafeCopyToFinalAsync(
            final,
            final,
            async staged =>
            {
                await _tools.ValidateStagedOutputAsync(staged, context.Source, context.SourceProbe, context.Plan, context.SourceWarnings).ConfigureAwait(false);
                AssertSourceUnchanged(context.Source, context.Expected);
            },
            progress,
            ownership: _ownership).ConfigureAwait(false);
        return "validated_hardlink_detached_copy";
    }

    /// <summary><c>_migrate_sidecars_before_cleanup</c>.</summary>
    private async Task MigrateSidecarsBeforeCleanupAsync(string src, string? finalOutputFile, IReadOnlyList<string> patterns, bool preserveTimestamps, PyDict output)
    {
        OutputFolderCleanup.SetDefault(output, "sidecars_migrated", new PyList());
        OutputFolderCleanup.SetDefault(output, "sidecars_skipped", new PyList());
        OutputFolderCleanup.SetDefault(output, "sidecar_migration_blocked", PyBool.False);
        OutputFolderCleanup.SetDefault(output, "sidecar_migration_blocked_reason", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "original_timestamps_note", PyNull.Instance);
        if (finalOutputFile is null || patterns.Count == 0)
        {
            return;
        }

        var result = await SidecarMigration.MigrateAsync(src, finalOutputFile, patterns, preserveTimestamps).ConfigureAwait(false);
        output.Set("sidecars_migrated", StringList(result.Migrated.Select(m => Path.GetFileName(m.Destination))));
        output.Set("sidecars_skipped", StringList(result.Skipped));
        if (result.BlocksSourceDeletion)
        {
            output.Set("sidecar_migration_blocked", true);
            output.Set("sidecar_migration_blocked_reason", result.BlockingReason);
            _logger.LogWarning("Refiner sidecar migration: {Reason}", result.BlockingReason);
        }

        if (preserveTimestamps && SidecarMigration.ApplyOriginalTimestamps(src, finalOutputFile) is { } problem)
        {
            // Never fatal: the output is correct either way.
            output.Set("original_timestamps_note", problem);
            _logger.LogInformation("Refiner timestamps: {Problem}", problem);
        }
    }

    private static void InitFolderCleanupFields(PyDict output)
    {
        OutputFolderCleanup.SetDefault(output, "source_folder_deleted", PyBool.False);
        OutputFolderCleanup.SetDefault(output, "source_folder_path", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "source_folder_skip_reason", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "output_completeness_check", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "output_size_bytes", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "source_size_bytes", PyNull.Instance);
        OutputFolderCleanup.SetDefault(output, "cascade_folders_deleted", new PyList());
        OutputFolderCleanup.SetDefault(output, "output_completeness_note", PyNull.Instance);
    }

    /// <summary>
    /// <c>_handle_refiner_cleanup_after_success</c>: Movies may remove the whole release folder and its empty parents; TV hands
    /// over to the season-folder cleanup.
    /// </summary>
    private async Task HandleCleanupAfterSuccessAsync(PassContext context, PyDict output, string? finalOutputFile, CancellationToken cancellationToken)
    {
        if (output.Get("sidecar_migration_blocked") is { IsTruthy: true })
        {
            InitFolderCleanupFields(output);
            output.Set("source_deleted_after_success", false);
            output.Set("source_folder_skip_reason", output.Get("sidecar_migration_blocked_reason") is { IsTruthy: true } blocked
                ? blocked
                : new PyStr("Weir did not remove the source folder because a file set to travel with the video could not be copied."));
            _logger.LogWarning("Refiner cleanup blocked by sidecar migration: {Reason}", PyConvert.Str(output["source_folder_skip_reason"]));
            return;
        }

        if (context.Scope == "tv")
        {
            await _tvSeasonCleanup.RunAsync(
                new TvSeasonCleanupContext(output, context.Request.Runtime, context.Source, context.WatchedRoot, context.MinAge, context.Request.CurrentJobId, output.Copy(), finalOutputFile),
                cancellationToken).ConfigureAwait(false);
            return;
        }

        InitFolderCleanupFields(output);
        var src = context.Source;
        var watched = context.WatchedRoot;
        if (!RemuxPassPaths.IsUnder(src, watched))
        {
            output.Set("source_folder_skip_reason", "The video file is not under the saved watched folder, so nothing was removed.");
            output.Set("source_deleted_after_success", false);
            return;
        }

        var movieFolder = Path.GetDirectoryName(src)!;
        if (!RemuxPassPaths.IsUnder(movieFolder, watched))
        {
            output.Set("source_folder_skip_reason", "The release folder would sit outside the watched folder, so Refiner did not change it.");
            output.Set("source_deleted_after_success", false);
            return;
        }

        if (RemuxPassPaths.SamePath(movieFolder, watched))
        {
            output.Set("source_folder_skip_reason", "The video file sits directly in the watched folder root, so Refiner does not remove a release folder here.");
            output.Set("source_deleted_after_success", false);
            _logger.LogWarning("Refiner Movies cleanup: immediate parent is watched root ({Root}).", watched);
            return;
        }

        output.Set("source_folder_path", movieFolder);
        if (PyStrings.Strip(context.Request.Runtime.OutputFolder ?? string.Empty).Length == 0)
        {
            const string NoOutput = "No output folder is configured for Movies, so the release folder was not removed.";
            output.Set("output_completeness_check", "skipped");
            output.Set("source_folder_skip_reason", NoOutput);
            output.Set("output_completeness_note", NoOutput);
            output.Set("source_deleted_after_success", false);
            return;
        }

        var outputFile = finalOutputFile ?? Path.Join(context.OutputDirectory, RemuxPassPaths.RelativeTo(src, watched)!);
        var check = CheckOutputFileCompleteness(outputFile, src);
        foreach (var (key, value) in check.Items)
        {
            if (key != "output_completeness_note" || value.IsTruthy)
            {
                output.Set(key, value);
            }
        }

        if (check.Get("output_completeness_check") is not PyStr { Value: "passed" })
        {
            output.Set("source_folder_skip_reason", check.Get("output_completeness_note") is { IsTruthy: true } note
                ? note
                : new PyStr("The output file did not pass the safety check, so the release folder was not removed."));
            output.Set("source_deleted_after_success", false);
            _logger.LogWarning("Refiner Movies cleanup: skipped — {Reason}", PyConvert.Str(output["source_folder_skip_reason"]));
            return;
        }

        try
        {
            Directory.Delete(movieFolder, recursive: true);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            var message = $"Refiner could not remove the release folder ({movieFolder}): {exception.Message}";
            _logger.LogWarning("Refiner Movies cleanup: {Message}", message);
            output.Set("source_folder_skip_reason", message);
            output.Set("source_deleted_after_success", false);
            output.Set("source_folder_deleted", false);
            return;
        }

        output.Set("source_folder_deleted", true);
        output.Set("source_deleted_after_success", true);
        output.Set("source_folder_skip_reason", PyNull.Instance);
        var cascade = output.Get("cascade_folders_deleted") as PyList ?? new PyList();
        OutputFolderCleanup.CascadeDeleteEmptyParents(Path.GetDirectoryName(movieFolder)!, watched, cascade, _logger);
        output.Set("cascade_folders_deleted", cascade);
    }

    /// <summary><c>_check_output_file_completeness</c>: exists, not empty, not under 1% of the source.</summary>
    public static PyDict CheckOutputFileCompleteness(string outputFile, string sourceFile, bool tv = false)
    {
        if (!File.Exists(outputFile))
        {
            return Completeness("failed", null, null, "The output file is missing at the path Refiner expected.");
        }

        long outSize;
        long srcSize;
        try
        {
            outSize = new FileInfo(outputFile).Length;
            srcSize = new FileInfo(sourceFile).Length;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return Completeness("failed", null, null, $"Refiner could not read the file size ({exception.Message}).");
        }

        if (outSize <= 0)
        {
            return Completeness("failed", outSize, srcSize, "The output file is empty (zero bytes).");
        }

        if (srcSize > 0 && outSize < Math.Max(1, srcSize / 100))
        {
            return Completeness(
                "failed",
                outSize,
                srcSize,
                tv
                    ? "The output file is much smaller than the source (under 1% of source size), so Refiner blocked TV season cleanup as a safety step."
                    : "The output file is much smaller than the source (under 1% of source size), so Refiner skipped removing the release folder as a safety step.");
        }

        return Completeness("passed", outSize, srcSize, null);

        static PyDict Completeness(string check, long? output, long? source, string? note) => new PyDict()
            .Set("output_completeness_check", check)
            .Set("output_size_bytes", output)
            .Set("source_size_bytes", source)
            .Set("output_completeness_note", note);
    }

    private Task RunScopeOutputCleanupAsync(PassContext context, PyDict output, string? finalOutputFile, CancellationToken cancellationToken) =>
        context.Scope == "tv"
            ? _outputCleanup.RunTvAsync(output, context.Request.Runtime, context.WatchedRoot, context.Source, finalOutputFile, context.Request.CurrentJobId, context.Scope, context.Request.Origin, cancellationToken)
            : _outputCleanup.RunMovieAsync(output, context.Request.Runtime, context.WatchedRoot, context.Source, finalOutputFile, context.RelativeMediaPath, context.Request.CurrentJobId, context.Scope, context.Request.Origin, cancellationToken);

    /// <summary>
    /// #537 item 4: the metadata lookup decides which audio the planner prefers. Declining (no provider, no match, unreachable)
    /// leaves the language preferences in charge, with a note saying so.
    /// </summary>
    private async Task<(RefinerRulesConfig Config, PyDict Record)> ApplyOriginalLanguageAsync(
        RefinerRulesConfig config,
        OriginalLanguageRules rules,
        string scope,
        string relativeMediaPath,
        HandoffOrigin? origin,
        IReadOnlyList<ProbeStreamInfo> audio,
        CancellationToken cancellationToken)
    {
        LookupResult lookup;
        try
        {
            lookup = await _originalLanguage.LookupAsync(scope, relativeMediaPath, origin, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "Refiner original-language lookup failed for {Path}.", relativeMediaPath);
            lookup = new LookupResult { Status = LookupResult.StatusUnreachable, Detail = $"The metadata lookup failed ({exception.Message})." };
        }

        var tracks = audio
            .Where(stream => stream.Index is not null)
            .Select(stream => new OriginalLanguageTrack((int)stream.Index!.Value, stream.Tag("language") ?? string.Empty))
            .ToList();
        var outcome = OriginalLanguage.SelectTracks(rules, lookup, tracks);
        var record = new PyDict()
            .Set("lookup_status", lookup.Status)
            .Set("lookup_detail", lookup.Detail)
            .Set("original_language", lookup.Metadata?.OriginalLanguage)
            .Set("preferred_audio_indices", new PyList(outcome.PreferredIndices.Select(index => (PyJson)new PyInt(index))))
            .Set("note", outcome.Note);
        return (config.WithOriginalLanguage(outcome), record);
    }

    /// <summary><c>_assert_source_unchanged</c>.</summary>
    private static void AssertSourceUnchanged(string path, SourceFingerprint expected)
    {
        SourceFingerprint current;
        try
        {
            current = SourceFiles.Fingerprint(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new MediaCompletenessException(
                $"The source could not be rechecked after processing ({exception.Message}), so the staged output was not published.",
                exception);
        }

        if (current != expected)
        {
            throw new MediaCompletenessException(
                "The source changed while Refiner was reading it. The staged output was discarded and Weir will wait " +
                "for the downloader or importer to finish.");
        }
    }

    /// <summary><c>_fail_before</c>.</summary>
    public static PyDict FailBefore(string relativeMediaPath, string reason, string? inspectedSourcePath = null, PyDict? extra = null)
    {
        var result = new PyDict()
            .Set("ok", false)
            .Set("outcome", RemuxPassOutcomes.FailedBeforeExecution)
            .Set("preflight_status", "failed")
            .Set("preflight_reason", reason)
            .Set("reason", reason)
            .Set("relative_media_path", relativeMediaPath);
        foreach (var (key, value) in extra?.Items ?? [])
        {
            result.Set(key, value);
        }

        if (!string.IsNullOrEmpty(inspectedSourcePath))
        {
            result.Set("inspected_source_path", inspectedSourcePath);
        }

        return result;
    }

    /// <summary><c>_source_not_ready</c>: an expected wait, not a failure.</summary>
    public static PyDict SourceNotReady(string relativeMediaPath, string reason, string? inspectedSourcePath = null)
    {
        var result = new PyDict()
            .Set("ok", false)
            .Set("outcome", RemuxPassOutcomes.SourceNotReady)
            .Set("retryable_wait", true)
            .Set("preflight_status", "waiting")
            .Set("preflight_reason", reason)
            .Set("reason", reason)
            .Set("relative_media_path", relativeMediaPath);
        if (!string.IsNullOrEmpty(inspectedSourcePath))
        {
            result.Set("inspected_source_path", inspectedSourcePath);
        }

        return result;
    }

    /// <summary><c>_skip_guardrail</c>.</summary>
    public static PyDict SkipGuardrail(string relativeMediaPath, string reason, string guardrail, string? inspectedSourcePath, PyDict extra)
    {
        ArgumentNullException.ThrowIfNull(extra);
        var result = new PyDict()
            .Set("ok", true)
            .Set("outcome", RemuxPassOutcomes.SkippedGuardrail)
            .Set("preflight_status", "skipped")
            .Set("preflight_reason", reason)
            .Set("reason", reason)
            .Set("guardrail", guardrail)
            .Set("relative_media_path", relativeMediaPath);
        foreach (var (key, value) in extra.Items)
        {
            result.Set(key, value);
        }

        if (inspectedSourcePath is not null)
        {
            result.Set("inspected_source_path", inspectedSourcePath);
        }

        return result;
    }

    /// <summary><c>_normalize_media_scope_for_cleanup</c>.</summary>
    public static string NormalizeScope(string? raw) => string.Equals(PyStrings.Strip(raw ?? "movie"), "tv", StringComparison.OrdinalIgnoreCase) ? "tv" : "movie";

    private static PyList StringList(IEnumerable<string> values) => new(values.Select(value => (PyJson)new PyStr(value)));

    private static PyJson NullableFloat(double? value) => value is { } v ? new PyFloat(v) : PyNull.Instance;
}

/// <summary>The environment-level settings a pass reads (<c>WeirSettings</c> fields).</summary>
public sealed record RemuxPassSettings
{
    public int ProbeSizeMb { get; init; } = 10;
    public int AnalyzeDurationSeconds { get; init; } = 10;
    public int WatchedFolderMinFileAgeSeconds { get; init; } = 60;
    public int MovieOutputCleanupMinAgeSeconds { get; init; }
    public int TvOutputCleanupMinAgeSeconds { get; init; }
}
