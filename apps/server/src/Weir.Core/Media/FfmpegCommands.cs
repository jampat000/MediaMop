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

        args.AddRange(["-c", "copy"]);
        // After the maps: the maps decide which streams exist, these decide what they carry.
        args.AddRange(MetadataStreams.ArgvFlags(plan.Metadata));
        for (var i = 0; i < plan.Audio.Count; i++)
        {
            args.AddRange([$"-disposition:a:{i.ToString(CultureInfo.InvariantCulture)}", plan.Audio[i].Default ? "default" : "0"]);
        }

        for (var i = 0; i < plan.Subtitles.Count; i++)
        {
            var track = plan.Subtitles[i];
            var flags = new List<string>();
            if (track.Default)
            {
                flags.Add("default");
            }

            if (track.Forced)
            {
                flags.Add("forced");
            }

            args.AddRange([$"-disposition:s:{i.ToString(CultureInfo.InvariantCulture)}", flags.Count > 0 ? string.Join('+', flags) : "0"]);
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
}
