using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Weir.Core.Json;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>One track the plan expects to find at a given output position.</summary>
/// <param name="CodecType">"video", "audio" or "subtitle".</param>
/// <param name="Default">The disposition the plan sets, or null when the plan does not care (video).</param>
/// <param name="Forced">The disposition the plan sets, or null when the plan does not care (video).</param>
/// <param name="Language">
/// The normalized language the plan sets, or null when the plan does not tag one (unknown source language, or
/// <see cref="MetadataRules.RemoveLanguageTags"/> strips it on purpose).
/// </param>
public sealed record PlannedOutputTrack(string CodecType, bool? Default, bool? Forced, string? Language);

/// <summary>One track ffprobe actually found in the output, at its position in the file.</summary>
public sealed record ActualOutputTrack(string CodecType, bool Default, bool Forced, string? Language);

/// <summary>
/// Issue #500: checks a staged remux output against the whole <see cref="RemuxPlan"/> — the container family, the
/// track type and disposition at every position, the language tags the plan sets, new ffprobe warnings the source
/// did not have, and metadata rules that must have taken effect — instead of the older "at least the expected audio
/// count and not much shorter" check (kept as <see cref="ProbeOutput.ValidateRemuxOutput"/> only for golden parity
/// with the Python reference, which is not fixed). Ported from Muxarr's <c>OutputValidator</c> (see the issue for
/// the exact reference checked against).
/// </summary>
public static partial class RemuxOutputValidation
{
    private static readonly (string Label, string[] Markers)[] ContainerFamilies =
    [
        ("matroska/webm", ["matroska", "webm"]),
        ("mov/mp4", ["mov", "mp4", "m4a", "3gp", "3g2", "mj2"]),
    ];

    [GeneratedRegex("0x[0-9a-fA-F]+", RegexOptions.CultureInvariant)]
    private static partial Regex HexAddressRegex();

    [GeneratedRegex(@"\d+(?:\.\d+)?", RegexOptions.CultureInvariant)]
    private static partial Regex NumberRunRegex();

    [GeneratedRegex(@"\s+", RegexOptions.CultureInvariant)]
    private static partial Regex WhitespaceRunRegex();

    [GeneratedRegex(@"^(\d+):([0-5]?\d):([0-5]?\d(?:\.\d+)?)$", RegexOptions.CultureInvariant)]
    private static partial Regex TagsDurationRegex();

    /// <summary>
    /// The order <see cref="FfmpegCommands.BuildRemuxArgv"/> maps streams in: every kept video, then the one kept
    /// audio track, then the kept subtitles. Output position <c>i</c> must be this list's entry <c>i</c>.
    /// </summary>
    public static IReadOnlyList<PlannedOutputTrack> ExpectedLayout(RemuxPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        var languageTagsRemoved = plan.Metadata.RemoveLanguageTags;
        var result = new List<PlannedOutputTrack>(plan.VideoIndices.Count + plan.Audio.Count + plan.Subtitles.Count);
        for (var i = 0; i < plan.VideoIndices.Count; i++)
        {
            result.Add(new PlannedOutputTrack("video", null, null, null));
        }

        foreach (var track in plan.Audio)
        {
            result.Add(new PlannedOutputTrack("audio", track.Default, track.Forced, PlannedLanguage(track, languageTagsRemoved)));
        }

        foreach (var track in plan.Subtitles)
        {
            result.Add(new PlannedOutputTrack("subtitle", track.Default, track.Forced, PlannedLanguage(track, languageTagsRemoved)));
        }

        return result;
    }

    private static string? PlannedLanguage(PlannedTrack track, bool languageTagsRemoved) =>
        languageTagsRemoved || track.LangLabel.Length == 0 ? null : track.LangLabel;

    /// <summary>
    /// ffprobe's <c>format.format_name</c>, canonicalized to the family the reference groups it in: Matroska and
    /// WebM share a muxer family, as do the MOV/MP4-derived containers, so a WebM output for a Matroska plan is not
    /// a container flip. An unrecognized format name is returned lower-cased, so an exact match still passes and
    /// any other value still fails.
    /// </summary>
    public static string ContainerFamily(string? formatName)
    {
        var lowered = Py.Lower(PyStrings.Strip(formatName ?? string.Empty));
        if (lowered.Length == 0)
        {
            return string.Empty;
        }

        var tokens = lowered.Split(',');
        foreach (var (label, markers) in ContainerFamilies)
        {
            if (markers.Any(tokens.Contains))
            {
                return label;
            }
        }

        return lowered;
    }

    /// <summary><c>format.format_name</c> off a probe document, or null when absent.</summary>
    public static string? FormatName(JsonElement probe)
    {
        if (probe.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        var format = Py.Get(probe, "format");
        if (!Py.IsDict(format))
        {
            return null;
        }

        var name = Py.Get(format!.Value, "format_name");
        return Py.Truthy(name) ? Py.Str(name) : null;
    }

    /// <summary><c>format.tags.title</c> off a probe document, or null when absent or blank.</summary>
    public static string? FormatTitle(JsonElement probe)
    {
        if (probe.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        var format = Py.Get(probe, "format");
        if (!Py.IsDict(format))
        {
            return null;
        }

        var tags = Py.Get(format!.Value, "tags");
        if (!Py.IsDict(tags))
        {
            return null;
        }

        var title = Py.Get(tags!.Value, "title");
        return Py.Truthy(title) ? Py.Str(title) : null;
    }

    /// <summary>The tracks ffprobe actually found in a probe document, in output order (ffprobe already lists streams in that order).</summary>
    public static IReadOnlyList<ActualOutputTrack> ActualLayout(JsonElement probe)
    {
        if (probe.ValueKind != JsonValueKind.Object)
        {
            return [];
        }

        var streams = Py.Get(probe, "streams");
        if (!Py.IsList(streams))
        {
            return [];
        }

        var result = new List<ActualOutputTrack>();
        foreach (var stream in streams!.Value.EnumerateArray())
        {
            if (stream.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            var codecType = Py.IsStr(Py.Get(stream, "codec_type")) ? Py.Lower(Py.Get(stream, "codec_type")!.Value.GetString()!) : string.Empty;
            var disposition = Py.Get(stream, "disposition");
            var tags = Py.Get(stream, "tags");
            string? language = null;
            if (Py.IsDict(tags))
            {
                var raw = Py.Get(tags!.Value, "language");
                if (Py.Truthy(raw) && Py.IsStr(raw))
                {
                    language = raw!.Value.GetString();
                }
            }

            result.Add(new ActualOutputTrack(codecType, DispositionFlag(disposition, "default"), DispositionFlag(disposition, "forced"), language));
        }

        return result;
    }

    private static bool DispositionFlag(JsonElement? disposition, string name) =>
        Py.IsDict(disposition) && Py.TryInt(Py.Get(disposition!.Value, name), out var flag) && flag != 0;

    /// <summary>Strips the noise a fresh process run adds to an otherwise identical ffprobe/ffmpeg diagnostic line: pointer addresses and any other run of digits (offsets, timestamps, byte counts).</summary>
    public static string NormalizeWarning(string line)
    {
        var text = PyStrings.Strip(line);
        text = HexAddressRegex().Replace(text, "0x#");
        text = NumberRunRegex().Replace(text, "#");
        text = WhitespaceRunRegex().Replace(text, " ");
        return text;
    }

    /// <summary>Non-blank, stripped lines of an ffprobe <c>-v warning</c> stderr capture.</summary>
    public static IReadOnlyList<string> WarningLines(string stderrText)
    {
        var result = new List<string>();
        foreach (var raw in PyText.SplitLines(stderrText))
        {
            var stripped = PyStrings.Strip(raw);
            if (stripped.Length > 0)
            {
                result.Add(stripped);
            }
        }

        return result;
    }

    /// <summary>
    /// The output's normalized warning lines that have no match among the source's normalized warning lines
    /// (order preserved, duplicates collapsed).
    /// </summary>
    public static IReadOnlyList<string> WarningsNewInOutput(IReadOnlyList<string> sourceWarnings, IReadOnlyList<string> outputWarnings)
    {
        ArgumentNullException.ThrowIfNull(sourceWarnings);
        ArgumentNullException.ThrowIfNull(outputWarnings);
        var sourceNormalized = new HashSet<string>(sourceWarnings.Select(NormalizeWarning), StringComparer.Ordinal);
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<string>();
        foreach (var line in outputWarnings)
        {
            var normalized = NormalizeWarning(line);
            if (!sourceNormalized.Contains(normalized) && seen.Add(normalized))
            {
                result.Add(line);
            }
        }

        return result;
    }

    /// <summary>
    /// The max duration reported by any stream the plan keeps (its own <c>duration</c>, or a Matroska
    /// <c>tags.DURATION</c>), ignoring streams the plan drops. Null when none of the kept streams reports one, so
    /// the caller should fall back to measuring directly.
    /// </summary>
    public static double? ExpectedDurationFromKeptStreams(JsonElement sourceProbe, RemuxPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        var kept = new HashSet<int>(plan.VideoIndices);
        foreach (var track in plan.Audio)
        {
            kept.Add(track.InputIndex);
        }

        foreach (var track in plan.Subtitles)
        {
            kept.Add(track.InputIndex);
        }

        double? best = null;
        if (sourceProbe.ValueKind == JsonValueKind.Object && Py.Get(sourceProbe, "streams") is { } streams && Py.IsList(streams))
        {
            foreach (var stream in streams.EnumerateArray())
            {
                if (stream.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                if (!Py.TryInt(Py.Get(stream, "index"), out var index) || !kept.Contains((int)index))
                {
                    continue;
                }

                var candidate = StreamDurationSeconds(stream);
                if (candidate is { } value && value > 0 && (best is null || value > best.Value))
                {
                    best = value;
                }
            }
        }

        return best;
    }

    private static double? StreamDurationSeconds(JsonElement stream)
    {
        var duration = Py.Get(stream, "duration");
        if (Py.Truthy(duration))
        {
            var parsed = duration!.Value.ValueKind switch
            {
                JsonValueKind.Number => duration.Value.GetDouble(),
                JsonValueKind.String => Py.TryFloatFromText(duration.Value.GetString()!),
                _ => (double?)null,
            };
            if (parsed is { } value && value > 0)
            {
                return value;
            }
        }

        var tags = Py.Get(stream, "tags");
        if (Py.IsDict(tags))
        {
            var raw = Py.Get(tags!.Value, "DURATION");
            if (Py.Truthy(raw) && Py.IsStr(raw) && ParseTagsDuration(raw!.Value.GetString()) is { } seconds)
            {
                return seconds;
            }
        }

        return null;
    }

    /// <summary>Parses a Matroska-style <c>HH:MM:SS.sssssssss</c> duration tag into seconds, or null when it does not match.</summary>
    public static double? ParseTagsDuration(string? text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return null;
        }

        var match = TagsDurationRegex().Match(PyStrings.Strip(text));
        if (!match.Success)
        {
            return null;
        }

        var hours = double.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture);
        var minutes = double.Parse(match.Groups[2].Value, CultureInfo.InvariantCulture);
        var seconds = double.Parse(match.Groups[3].Value, CultureInfo.InvariantCulture);
        var total = (hours * 3600) + (minutes * 60) + seconds;
        return total > 0 ? total : null;
    }

    /// <summary>
    /// The full check (#500 steps 1-6). Throws <see cref="MediaToolException"/> naming exactly what differed for a
    /// structural mismatch (container, counts, position, disposition, language, warnings, metadata), or
    /// <see cref="MediaCompletenessException"/> when the output cannot be confirmed complete (no measurable
    /// duration, or a real shortfall) — both are execution failures, never content rejections, so a bad remux never
    /// tells a library's reject policy the release itself is bad.
    /// </summary>
    public static void ValidateAgainstPlan(
        JsonElement outputProbe,
        RemuxPlan plan,
        string? sourceFormatName,
        double expectedDurationSeconds,
        IReadOnlyList<string> sourceWarnings,
        IReadOnlyList<string> outputWarnings)
    {
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(sourceWarnings);
        ArgumentNullException.ThrowIfNull(outputWarnings);

        // 1. Container family.
        var outputFormatName = FormatName(outputProbe);
        var sourceFamily = ContainerFamily(sourceFormatName);
        var outputFamily = ContainerFamily(outputFormatName);
        if (sourceFamily.Length > 0 && outputFamily.Length > 0 && sourceFamily != outputFamily)
        {
            throw new MediaToolException(
                $"Planned to keep the {sourceFamily} container, but the output is {outputFamily} " +
                $"({(outputFormatName is { Length: > 0 } name ? name : "unknown")}).");
        }

        var expected = ExpectedLayout(plan);
        var actual = ActualLayout(outputProbe);

        // 2. Track counts, per type — a clearer message than a bare position count for the common case (a dropped subtitle).
        foreach (var type in new[] { "video", "audio", "subtitle" })
        {
            var wantCount = expected.Count(t => t.CodecType == type);
            var gotCount = actual.Count(t => t.CodecType == type);
            if (wantCount != gotCount)
            {
                throw new MediaToolException(
                    $"Planned {wantCount.ToString(CultureInfo.InvariantCulture)} {type} track(s), output has {gotCount.ToString(CultureInfo.InvariantCulture)}.");
            }
        }

        if (actual.Count != expected.Count)
        {
            throw new MediaToolException(
                $"Planned {expected.Count.ToString(CultureInfo.InvariantCulture)} track(s), output has {actual.Count.ToString(CultureInfo.InvariantCulture)}.");
        }

        // 3. Track type, disposition and language at every position.
        for (var i = 0; i < expected.Count; i++)
        {
            var want = expected[i];
            var got = actual[i];
            var position = i.ToString(CultureInfo.InvariantCulture);
            if (want.CodecType != got.CodecType)
            {
                throw new MediaToolException($"Planned output position {position} to be {want.CodecType}, output has {Describe(got.CodecType)}.");
            }

            if (want.Default is { } wantDefault && wantDefault != got.Default)
            {
                throw new MediaToolException(
                    $"Planned the {want.CodecType} track at position {position} to have default={PyBool(wantDefault)}, output has default={PyBool(got.Default)}.");
            }

            if (want.Forced is { } wantForced && wantForced != got.Forced)
            {
                throw new MediaToolException(
                    $"Planned the {want.CodecType} track at position {position} to have forced={PyBool(wantForced)}, output has forced={PyBool(got.Forced)}.");
            }

            if (want.Language is { Length: > 0 } wantLanguage)
            {
                var gotLanguage = RemuxRules.NormalizeLang(got.Language);
                if (gotLanguage != wantLanguage)
                {
                    throw new MediaToolException(
                        $"Planned the {want.CodecType} track at position {position} to be tagged '{wantLanguage}', output is tagged " +
                        $"'{(gotLanguage.Length > 0 ? gotLanguage : "und")}'.");
                }
            }
        }

        // 4. Duration, against the max of the kept source streams (or a direct measurement), not the whole source.
        var outputDuration = ProbeOutput.DurationSeconds(outputProbe);
        if (outputDuration is null)
        {
            throw new MediaCompletenessException(
                "Validation failed: Refiner could not confirm the staged output duration, so it was not published.");
        }

        var tolerance = Math.Max(0.5, expectedDurationSeconds * 0.01);
        if (outputDuration.Value < expectedDurationSeconds - tolerance)
        {
            throw new MediaCompletenessException(
                "Validation failed: the staged output is incomplete "
                + $"({PyText.FormatFixed(outputDuration.Value, 1)}s of {PyText.FormatFixed(expectedDurationSeconds, 1)}s expected), so it was not published.");
        }

        // 5. New ffprobe warnings.
        var newWarnings = WarningsNewInOutput(sourceWarnings, outputWarnings);
        if (newWarnings.Count > 0)
        {
            throw new MediaToolException(
                "ffprobe reported warnings on the output that the source did not have: " + string.Join(" | ", newWarnings));
        }

        // 6. Metadata: a cleared title must actually be cleared. Chapters are not modeled yet (#498 is not merged here).
        if (plan.Metadata.RemoveTitle)
        {
            var outputTitle = FormatTitle(outputProbe);
            if (!string.IsNullOrEmpty(outputTitle))
            {
                throw new MediaToolException($"Planned to clear the container title, output still has '{outputTitle}'.");
            }
        }
    }

    private static string Describe(string codecType) => codecType.Length > 0 ? codecType : "an untyped stream";

    private static string PyBool(bool value) => value ? "True" : "False";
}
