using System.Globalization;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>
/// The ffprobe and ffmpeg command lines from <c>refiner_remux_mux.py</c>, token for token. Paths are
/// taken as the strings the caller already holds (the reference passes <c>str(path)</c>).
/// </summary>
public static class FfmpegCommands
{
    /// <summary><c>REFINER_FFMPEG_TIMEOUT_S</c>: the wall-clock limit for one ffmpeg run.</summary>
    public const int FfmpegTimeoutSeconds = 3600;

    /// <summary><c>REFINER_FFMPEG_SLOW_GRACE_S</c>: projections are ignored for the first minute.</summary>
    public const int FfmpegSlowGraceSeconds = 60;

    /// <summary><c>REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S</c>: twelve hours.</summary>
    public const int FfmpegMaxProjectedRemainingSeconds = 12 * 60 * 60;

    /// <summary>ffprobe's default time limit in <c>ffprobe_json</c>.</summary>
    public const int FfprobeTimeoutSeconds = 120;

    /// <summary><c>_REFINER_FFPROBE_LOG_MAX_CHARS</c>.</summary>
    public const int ProbeLogMaxChars = 2000;

    /// <summary><c>_REFINER_FFMPEG_STDERR_TAIL_BYTES</c>: how much of ffmpeg's stderr a failure message keeps.</summary>
    public const int FfmpegStderrTailBytes = 32 * 1024;

    /// <summary>The ffmpeg wait after its progress stream closes (<c>proc.wait(timeout=5)</c>).</summary>
    public const int ProgressExitWaitSeconds = 5;

    /// <summary><c>_HWACCEL_TIMEOUT_SECONDS</c> (a float in the reference, so it prints as <c>10.0</c>).</summary>
    public const double HwaccelTimeoutSeconds = 10.0;

    /// <summary>
    /// <c>build_ffprobe_argv</c>: probe size and analyze duration are clamped to 1..1024 MB and 1..300 s.
    /// </summary>
    /// <remarks>
    /// Deliberate divergence (#539 item 1): the reference passes <c>-v quiet</c>, which discards ffprobe's
    /// diagnostics entirely, so the words <see cref="ProbeOutput.UnreadableMediaMarkers"/> looks for never
    /// reach stderr and unreadable media is reported as a plain failure instead of <c>MediaUnreadableException</c>.
    /// <c>-v error</c> keeps JSON on stdout unchanged (verbosity does not affect <c>-print_format json</c>) and
    /// puts ffmpeg's own error lines on stderr, which is what the classification in
    /// <see cref="ProbeOutput.FailureFor"/> needs. See apps/server/README.md "ffmpeg parity" for how the golden
    /// fixtures captured against Python's <c>-v quiet</c> behaviour are patched to prove this on purpose.
    /// <para>
    /// Deliberate divergence (#498): the reference never asks ffprobe for chapters, so a caller wanting to know
    /// whether a file has any (<see cref="Weir.Core.Rules.RemuxRules.IsRemuxRequired"/>'s <c>chaptersPresent</c>,
    /// for the "remove chapters" option) would need a second probe just for that. <c>-show_chapters</c> is added
    /// here instead, so every probe's JSON already carries a <c>chapters</c> array (see
    /// <see cref="ProbeResult.Chapters"/>) — empty when the file has none. This only adds a <c>chapters</c> key to
    /// the parsed result; every other field is unchanged, and the golden fixtures (captured before this option
    /// existed) are patched at the one changed argv token — see README "ffmpeg parity" and each patch site's
    /// <c>GoldenDivergences</c> helper.
    /// </para>
    /// </remarks>
    public static IReadOnlyList<string> BuildFfprobeArgv(string ffprobeBin, string src, long probeSizeMb = 10, long analyzeDurationSeconds = 10)
    {
        ArgumentNullException.ThrowIfNull(ffprobeBin);
        ArgumentNullException.ThrowIfNull(src);
        var psMb = Math.Max(1, Math.Min(1024, probeSizeMb));
        var adS = Math.Max(1, Math.Min(300, analyzeDurationSeconds));
        return
        [
            ffprobeBin,
            "-v",
            "error",
            "-probesize",
            (psMb * 1024 * 1024).ToString(CultureInfo.InvariantCulture),
            "-analyzeduration",
            (adS * 1_000_000).ToString(CultureInfo.InvariantCulture),
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            "-show_chapters",
            src,
        ];
    }

    /// <summary>
    /// #500: the same probe as <see cref="BuildFfprobeArgv"/> but at <c>-v warning</c>, so ffprobe's warning-level
    /// diagnostics (not just errors) land on stderr for the source-vs-output comparison in
    /// <see cref="RemuxOutputValidation"/>. Verbosity does not affect <c>-print_format json</c> or the JSON on
    /// stdout, which callers of this argv discard — only stderr is read.
    /// </summary>
    public static IReadOnlyList<string> BuildFfprobeWarningsArgv(string ffprobeBin, string src, long probeSizeMb = 10, long analyzeDurationSeconds = 10)
    {
        var argv = BuildFfprobeArgv(ffprobeBin, src, probeSizeMb, analyzeDurationSeconds).ToList();
        var index = argv.IndexOf("-v");
        argv[index + 1] = "warning";
        return argv;
    }

    /// <summary>
    /// #500: demuxes exactly the streams <paramref name="plan"/> keeps (video, then audio, then subtitles, matching
    /// <see cref="BuildRemuxArgv"/>'s map order) without writing them anywhere, so the last <c>-progress pipe:1</c>
    /// timestamp reached is the source's playable duration restricted to those streams. Used only when none of the
    /// kept streams' own probed duration is usable (<see cref="RemuxOutputValidation.ExpectedDurationFromKeptStreams"/>).
    /// </summary>
    public static IReadOnlyList<string> BuildKeptStreamsDemuxArgv(string ffmpegBin, string src, RemuxPlan plan)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        ArgumentNullException.ThrowIfNull(src);
        ArgumentNullException.ThrowIfNull(plan);
        var args = new List<string> { ffmpegBin, "-hide_banner", "-v", "error", "-i", src };
        foreach (var vi in plan.VideoIndices)
        {
            args.AddRange(["-map", Map(vi)]);
        }

        foreach (var track in plan.Audio)
        {
            args.AddRange(["-map", Map(track.InputIndex)]);
        }

        foreach (var track in plan.Subtitles)
        {
            args.AddRange(["-map", Map(track.InputIndex)]);
        }

        args.AddRange(["-c", "copy", "-f", "null", "-"]);
        return args;
    }

    /// <summary>The full demux of the primary video that <c>validate_media_integrity</c> runs.</summary>
    public static IReadOnlyList<string> BuildIntegrityArgv(string ffmpegBin, string path)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        ArgumentNullException.ThrowIfNull(path);
        return
        [
            ffmpegBin,
            "-hide_banner",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-i",
            path,
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "null",
            "-",
        ];
    }

    /// <summary>What <c>detect_acceleration</c> asks ffmpeg.</summary>
    public static IReadOnlyList<string> BuildHwaccelsArgv(string ffmpegBin)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        return [ffmpegBin, "-hide_banner", "-hwaccels"];
    }

    /// <summary>
    /// #547: the mov,mp4,m4a,3gp,3g2,mj2 muxer family — the only extensions Weir's remux ever writes that share
    /// it are <c>.mp4</c>, <c>.m4v</c> and <c>.mov</c> — refuses an attachment output stream outright ("Attachments
    /// are not supported in QuickTime/MP4"), verified against the bundled ffmpeg. Every other container Weir
    /// writes accepts one, Matroska above all (where attachments actually originate), and <c>-map 0:t?</c>'s
    /// <c>?</c> already makes the map a no-op when the source has none, so a container that cannot itself carry an
    /// <c>attachment</c>-typed input stream (there being no such ffprobe <c>codec_type</c> for it) is unaffected
    /// either way; only the containers that could plausibly receive one but reject it need excluding here.
    /// </summary>
    private static readonly HashSet<string> AttachmentIncapableExtensions = new(StringComparer.OrdinalIgnoreCase) { ".mp4", ".m4v", ".mov" };

    /// <summary>
    /// #547: mkvmerge's own per-track statistics tags (<c>DURATION</c>, <c>NUMBER_OF_FRAMES</c>,
    /// <c>NUMBER_OF_BYTES</c>, <c>BPS</c>, the three <c>_STATISTICS_*</c> keys) plus ffmpeg's <c>ENCODER</c> tag:
    /// all describe how the *elementary stream* was produced, not this remux, and survive a plain <c>-c copy</c>
    /// unchanged (confirmed against the bundled ffmpeg) even when the track set around them changes. Cleared on
    /// every kept video/audio/subtitle output stream so a player is not shown stale lineage. Matroska's own muxer
    /// recomputes a fresh, correct <c>DURATION</c> tag from the packets it actually writes regardless of this
    /// clear (also confirmed against the bundled ffmpeg), so clearing it here loses nothing; a stream with no such
    /// tag to begin with is unaffected, since setting an absent key to empty is a no-op.
    /// </summary>
    private static readonly IReadOnlyList<string> StaleStatisticsTagKeys =
    [
        "DURATION",
        "NUMBER_OF_FRAMES",
        "NUMBER_OF_BYTES",
        "BPS",
        "_STATISTICS_WRITING_APP",
        "_STATISTICS_WRITING_DATE_UTC",
        "_STATISTICS_TAGS",
        "ENCODER",
    ];

    /// <summary>
    /// <c>build_ffmpeg_argv</c>. <paramref name="inputFlags"/> (hardware acceleration and strictness) go
    /// before <c>-i</c>, because <c>-hwaccel</c> applies to the input that follows it.
    /// </summary>
    public static IReadOnlyList<string> BuildRemuxArgv(string ffmpegBin, string src, string dst, RemuxPlan plan, IReadOnlyList<string>? inputFlags = null)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        ArgumentNullException.ThrowIfNull(src);
        ArgumentNullException.ThrowIfNull(dst);
        ArgumentNullException.ThrowIfNull(plan);
        var args = new List<string>
        {
            ffmpegBin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-nostdin",
            "-y",
        };
        args.AddRange(inputFlags ?? []);
        args.AddRange(["-i", src]);
        foreach (var vi in plan.VideoIndices)
        {
            args.AddRange(["-map", Map(vi)]);
        }

        foreach (var track in plan.Audio)
        {
            args.AddRange(["-map", Map(track.InputIndex)]);
        }

        foreach (var track in plan.Subtitles)
        {
            args.AddRange(["-map", Map(track.InputIndex)]);
        }

        // #547 item 1: map every attachment (fonts attached for ASS/SSA subtitles, chiefly) unless the rules say
        // to drop them, or the output container cannot carry one at all (see AttachmentIncapableExtensions).
        // "0:t?" is ffmpeg's stream-type specifier for attachments; the trailing "?" makes it optional so a
        // source with none does not fail the map.
        var mapsAttachments = !plan.Metadata.RemoveAttachments && SupportsAttachmentOutput(dst);
        if (mapsAttachments)
        {
            args.AddRange(["-map", "0:t?"]);
        }

        args.AddRange(["-c", "copy"]);
        // After the maps: the maps decide which streams exist, these decide what they carry.
        args.AddRange(MetadataStreams.ArgvFlags(plan.Metadata));
        if (mapsAttachments && plan.Metadata.RemoveOtherMetadata)
        {
            // #547: "-map_metadata -1" above also erases an attachment's own filename/mimetype tags, unlike every
            // other stream type — unlike a video/audio/subtitle track, Matroska requires an attachment to carry a
            // filename tag at all, so without this restore ffmpeg refuses to write the file at all
            // ("Attachment stream N has no filename tag"), confirmed against the bundled ffmpeg. Restoring only the
            // attachment stream type's own metadata here keeps every other stream's "-map_metadata -1" intact.
            args.AddRange(["-map_metadata:s:t", "0:s:t"]);
        }

        // #547 item 2: additive syntax ("+flag"/"-flag") only ever touches default/forced, whatever else ffmpeg
        // already copied through from the source stream's own disposition (comment, descriptions,
        // hearing_impaired, dub, original, ...) unlike the flat "default"/"0" this replaced, which discarded them;
        // verified against the bundled ffmpeg's -dispositions and real remuxes.
        for (var i = 0; i < plan.Audio.Count; i++)
        {
            args.AddRange([$"-disposition:a:{i.ToString(CultureInfo.InvariantCulture)}", plan.Audio[i].Default ? "+default" : "-default"]);
        }

        for (var i = 0; i < plan.Subtitles.Count; i++)
        {
            var track = plan.Subtitles[i];
            var flags = (track.Default ? "+default" : "-default") + (track.Forced ? "+forced" : "-forced");
            args.AddRange([$"-disposition:s:{i.ToString(CultureInfo.InvariantCulture)}", flags]);
        }

        // #547 item 3: drop stale per-track statistics tags on every kept stream, indexed by output position like
        // the dispositions above.
        AddStatisticsTagClears(args, 'v', plan.VideoIndices.Count);
        AddStatisticsTagClears(args, 'a', plan.Audio.Count);
        AddStatisticsTagClears(args, 's', plan.Subtitles.Count);

        // #498: standard track names and cleared video names, after the dispositions, indexed by output position
        // (same as the dispositions above) rather than the original input index.
        if (plan.Metadata.StandardizeTrackNames)
        {
            for (var i = 0; i < plan.Audio.Count; i++)
            {
                args.AddRange([$"-metadata:s:a:{i.ToString(CultureInfo.InvariantCulture)}", $"title={TrackNaming.RenderTrackName(plan.Metadata, plan.Audio[i])}"]);
            }

            for (var i = 0; i < plan.Subtitles.Count; i++)
            {
                args.AddRange([$"-metadata:s:s:{i.ToString(CultureInfo.InvariantCulture)}", $"title={TrackNaming.RenderTrackName(plan.Metadata, plan.Subtitles[i])}"]);
            }
        }

        if (plan.Metadata.ClearVideoTrackNames)
        {
            for (var i = 0; i < plan.VideoIndices.Count; i++)
            {
                args.AddRange([$"-metadata:s:v:{i.ToString(CultureInfo.InvariantCulture)}", "title="]);
            }
        }

        args.Add(dst);
        return args;
    }

    /// <summary><c>_argv_with_progress</c>: <c>-progress pipe:1 -nostats</c> goes just before the output path.</summary>
    public static IReadOnlyList<string> WithProgress(IReadOnlyList<string> argv)
    {
        ArgumentNullException.ThrowIfNull(argv);
        var insertAt = argv.Count > 1 ? argv.Count - 1 : argv.Count;
        var result = new List<string>(argv.Count + 3);
        result.AddRange(argv.Take(insertAt));
        result.AddRange(["-progress", "pipe:1", "-nostats"]);
        result.AddRange(argv.Skip(insertAt));
        return result;
    }

    /// <summary><c>logger.debug("Refiner: ffmpeg %s", " ".join(argv[:8]) + " ...")</c>.</summary>
    public static string DebugSummary(IReadOnlyList<string> argv)
    {
        ArgumentNullException.ThrowIfNull(argv);
        return "Refiner: ffmpeg " + string.Join(' ', argv.Take(8)) + " ...";
    }

    private static string Map(int index) => "0:" + index.ToString(CultureInfo.InvariantCulture);

    /// <summary>See <see cref="AttachmentIncapableExtensions"/>. A path with no extension (or none after the last
    /// separator) is treated as capable, matching every container Weir actually names with a suffix.</summary>
    private static bool SupportsAttachmentOutput(string dst)
    {
        var lastDot = dst.LastIndexOf('.');
        var lastSeparator = Math.Max(dst.LastIndexOf('/'), dst.LastIndexOf('\\'));
        if (lastDot <= lastSeparator)
        {
            return true;
        }

        return !AttachmentIncapableExtensions.Contains(dst[lastDot..]);
    }

    /// <summary>See <see cref="StaleStatisticsTagKeys"/>: clear each of them on every one of <paramref name="count"/>
    /// kept output streams of <paramref name="streamType"/> ('v', 'a' or 's').</summary>
    private static void AddStatisticsTagClears(List<string> args, char streamType, int count)
    {
        for (var i = 0; i < count; i++)
        {
            var specifier = $"-metadata:s:{streamType}:{i.ToString(CultureInfo.InvariantCulture)}";
            foreach (var key in StaleStatisticsTagKeys)
            {
                args.AddRange([specifier, $"{key}="]);
            }
        }
    }
}
