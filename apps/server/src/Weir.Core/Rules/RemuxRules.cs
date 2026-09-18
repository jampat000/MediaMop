using System.Text.RegularExpressions;
using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>The stored values the reference compares against, kept as strings so unknown stored values behave identically.</summary>
public static class RemuxRuleValues
{
    public const string SubtitleModeRemoveAll = "remove_all";
    public const string SubtitleModeKeepSelected = "keep_selected";
    public const string DefaultAudioSlotPrimary = "primary";
    public const string DefaultAudioSlotSecondary = "secondary";
    public const string PolicyPreferredLangsQuality = "preferred_langs_quality";
    public const string PolicyPreferredLangsStrict = "preferred_langs_strict";
    public const string PolicyQualityAllLanguages = "quality_all_languages";

    /// <summary>Issue #497: keep exactly one audio track overall (today's behaviour, and the default).</summary>
    public const string AudioKeepModeSingle = "single";

    /// <summary>Issue #497: keep the best track of each configured language slot that has one.</summary>
    public const string AudioKeepModePerLanguage = "per_language";

    /// <summary>Issue #497: text (SRT/ASS/WebVTT/mov_text) over image (PGS/VobSub/DVB), the default.</summary>
    public const string SubtitleStrategyTextFirst = "text_first";

    public const string SubtitleStrategyImageFirst = "image_first";

    /// <summary>Issue #497: a hearing-impaired (SDH) track ranks first.</summary>
    public const string SubtitleStrategyAccessibility = "accessibility";
}

/// <summary>
/// The rules in force for one pass (<c>processing_remux_rules.ProcessingRulesConfig</c>).
/// <see cref="SubtitleMode"/> and <see cref="AudioPreferenceMode"/> stay strings: the planner
/// treats any subtitle mode other than <c>remove_all</c> as keep-selected and normalizes an
/// unknown policy to the default, exactly as the reference does.
/// </summary>
public sealed record ProcessingRulesConfig
{
    public required string PrimaryAudioLang { get; init; }
    public required string SecondaryAudioLang { get; init; }
    public required string TertiaryAudioLang { get; init; }
    public required string DefaultAudioSlot { get; init; }
    public required bool RemoveCommentary { get; init; }
    public required string SubtitleMode { get; init; }

    /// <summary>
    /// Issue #537 item 3: normalized the same way a track's own language tag is (<see cref="RemuxRules.NormalizeLang"/>),
    /// so "ENG" or "en-US" matches a file tagged "eng". Stored values were compared as-is before the fix.
    /// Issue #496: a recognized variant identifier ("fre-CA", or "fr-CA" as a BCP 47 tag) is kept
    /// instead of being reduced to its base language, so a list can single out a regional dub.
    /// </summary>
    public required IReadOnlyList<string> SubtitleLangs { get; init; }

    public required bool PreserveForcedSubs { get; init; }
    public required bool PreserveDefaultSubs { get; init; }
    public required string AudioPreferenceMode { get; init; }

    /// <summary>The ordered sorter list, as stored JSON. Empty means the seeded default.</summary>
    public string AudioSortersJson { get; init; } = string.Empty;

    /// <summary>
    /// Issue #495: remove a subtitle track whose <see cref="TrackFlags.HearingImpaired"/> flag is
    /// set (SDH/CC), from its disposition or its name. Off by default, so an upgrade changes nothing.
    /// </summary>
    public bool RemoveHearingImpairedSubs { get; init; }

    /// <summary>
    /// Issue #497: <see cref="RemuxRuleValues.AudioKeepModeSingle"/> (default; today's behaviour —
    /// every golden case is unchanged) or <see cref="RemuxRuleValues.AudioKeepModePerLanguage"/>,
    /// which keeps the best track of each configured language slot (primary/secondary/tertiary)
    /// that has one, instead of a single winner. New, so absent (the record default) means "single",
    /// exactly like every golden fixture recorded before this field existed.
    /// </summary>
    public string AudioKeepMode { get; init; } = RemuxRuleValues.AudioKeepModeSingle;

    /// <summary>
    /// Issue #497: caps how many subtitle tracks survive per language, keeping the best by
    /// <see cref="SubtitleQualityStrategy"/>. 0 (the default) means unlimited — today's behaviour.
    /// A forced track kept under <see cref="PreserveForcedSubs"/> does not count toward the cap.
    /// </summary>
    public int SubtitleMaxPerLanguage { get; init; }

    /// <summary>
    /// Issue #497: how the subtitle cap picks a winner within a language —
    /// <see cref="RemuxRuleValues.SubtitleStrategyTextFirst"/> (default), <c>image_first</c> or
    /// <c>accessibility</c>. Unused while <see cref="SubtitleMaxPerLanguage"/> is 0.
    /// </summary>
    public string SubtitleQualityStrategy { get; init; } = RemuxRuleValues.SubtitleStrategyTextFirst;

    /// <summary>Metadata and attachment stripping. All off by default.</summary>
    public MetadataRules Metadata { get; init; } = new();

    /// <summary>Carried for the pass; the planner itself reads only the resolved hint below.</summary>
    public OriginalLanguageRules? OriginalLanguage { get; init; }

    /// <summary>Input indices the pass wants preferred, in order, from the metadata lookup.</summary>
    public IReadOnlyList<int> PreferredAudioIndices { get; init; } = [];

    /// <summary>The sentence explaining which mechanism chose, appended to the selection notes.</summary>
    public string OriginalLanguageNote { get; init; } = string.Empty;

    /// <summary>
    /// Issue #537 item 4: how a caller feeds an original-language decision in cleanly, once the
    /// remux pass can look one up (it needs the manager/TMDb metadata lookup from #520, not ported
    /// yet — see apps/server/README.md). <see cref="PreferredAudioIndices"/> and
    /// <see cref="OriginalLanguageNote"/> already flow straight into <see cref="RemuxRules.PlanRemux"/>
    /// unchanged; this just saves a caller from copying both fields by hand.
    /// </summary>
    public ProcessingRulesConfig WithOriginalLanguage(OriginalLanguageOutcome outcome)
    {
        ArgumentNullException.ThrowIfNull(outcome);
        return this with { PreferredAudioIndices = outcome.PreferredIndices, OriginalLanguageNote = outcome.Note };
    }
}

public enum TrackKind
{
    Audio,
    Subtitle,
}

/// <summary>One kept track in a plan (<c>PlannedTrack</c>).</summary>
public sealed record PlannedTrack
{
    public required int InputIndex { get; init; }
    public required string LangLabel { get; init; }
    public bool Commentary { get; init; }
    public bool Forced { get; init; }
    public bool Default { get; init; }
    public int Channels { get; init; }
    public bool Lossless { get; init; }
    public long Bitrate { get; init; }
    public int CodecRank { get; init; } = RemuxRules.CodecUnknownRank;
    public string CodecName { get; init; } = string.Empty;
    public TrackKind Kind { get; init; } = TrackKind.Audio;

    /// <summary>
    /// Issue #496: the regional/script variant detected for this track (<c>"fre-CA"</c>), or null
    /// when none was detected or the base language rule matched regardless of variant.
    /// </summary>
    public string? Variant { get; init; }
}

/// <summary>What one pass writes (<c>RemuxPlan</c>).</summary>
public sealed record RemuxPlan
{
    public required IReadOnlyList<int> VideoIndices { get; init; }
    public required IReadOnlyList<PlannedTrack> Audio { get; init; }
    public required IReadOnlyList<PlannedTrack> Subtitles { get; init; }
    public IReadOnlyList<string> RemovedAudio { get; init; } = [];
    public IReadOnlyList<string> RemovedSubtitles { get; init; } = [];

    /// <summary>
    /// The same removals as <see cref="RemovedAudio"/>/<see cref="RemovedSubtitles"/>, structured for #509
    /// (a rule change surfacing titles that can only be fixed by re-downloading): one entry per removed
    /// track with its language, kind and codec, captured from the same source data those display strings
    /// are built from rather than parsed back out of them. Additive — existing golden fixtures compare
    /// only the fields <c>GoldenParityTests.WritePlanResult</c> names, which does not include this one.
    /// </summary>
    public IReadOnlyList<RemovedTrackRecord> RemovedTrackRecords { get; init; } = [];
    public int DefaultAudioOutputIndex { get; init; }
    public IReadOnlyList<string> AudioSelectionNotes { get; init; } = [];

    /// <summary>Embedded posters this plan drops, described.</summary>
    public IReadOnlyList<string> RemovedImages { get; init; } = [];

    public IReadOnlyList<string> RemovedAttachments { get; init; } = [];
    public IReadOnlyList<string> MetadataNotes { get; init; } = [];
    public MetadataRules Metadata { get; init; } = new();
}

/// <summary>The streams of a probe by type, each ordered by index (<c>split_streams</c>).</summary>
public sealed record SplitProbeStreams(IReadOnlyList<ProbeStreamInfo> Video, IReadOnlyList<ProbeStreamInfo> Audio, IReadOnlyList<ProbeStreamInfo> Subtitles);

/// <summary>
/// Remux planning (<c>processing_remux_rules.py</c>): stream splitting, audio candidate ranking under
/// the three policies, subtitle retention, metadata stripping and whether a pass is needed.
/// </summary>
public static partial class RemuxRules
{
    /// <summary>Best (index 0) to worst. Unknown codecs sort after all of these.</summary>
    public static IReadOnlyList<string> AudioCodecQualityOrder { get; } =
    [
        "truehd", "dts_hd_ma", "flac", "alac", "pcm_s32le", "pcm_s24le", "pcm_s16le", "pcm_f32le", "pcm_u8", "wavpack",
        "opus", "libopus", "eac3", "ac3", "dca", "dts", "aac", "libfdk_aac", "mp2", "mp3", "vorbis", "libvorbis", "wmav2",
    ];

    public const int CodecUnknownRank = 23 + 32;

    private static readonly Dictionary<string, int> CodecRankLookup =
        AudioCodecQualityOrder.Select((codec, rank) => (codec, rank)).ToDictionary(p => p.codec, p => p.rank, StringComparer.Ordinal);

    private static readonly HashSet<string> LosslessCodecs =
        new(StringComparer.Ordinal) { "flac", "truehd", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "wavpack" };

    /// <summary>
    /// Containers Processing can genuinely process. Raw elementary streams (<c>.h264</c>, <c>.h265</c>,
    /// <c>.mpv</c>) stay out: they have no audio, so a plan fails and failure cleanup would delete the folder.
    /// </summary>
    public static IReadOnlySet<string> MediaExtensions { get; } = new HashSet<string>(StringComparer.Ordinal)
    {
        ".mkv", ".mp4", ".m4v", ".webm", ".avi", ".mpe", ".mpeg", ".mpg", ".mov", ".flv", ".wmv", ".avchd",
    };

    /// <summary>The effective allowlist, for operator-facing reporting.</summary>
    public static IReadOnlyList<string> MediaExtensionsSorted() => [.. MediaExtensions.Order(StringComparer.Ordinal)];

    /// <summary>Lower rank is the better codec.</summary>
    public static int AudioCodecQualityRank(string? codecName)
    {
        var c = Py.Lower(PyStrings.Strip(codecName ?? string.Empty));
        if (c.Length == 0)
        {
            return CodecUnknownRank;
        }

        return CodecRankLookup.TryGetValue(c, out var rank) ? rank : CodecUnknownRank;
    }

    /// <summary>The canonical policy; unknown stored values use the default policy.</summary>
    public static string NormalizeAudioPreferenceMode(string? raw)
    {
        var m = Py.Lower(PyStrings.Strip(raw ?? string.Empty));
        return m is RemuxRuleValues.PolicyPreferredLangsQuality or RemuxRuleValues.PolicyPreferredLangsStrict or RemuxRuleValues.PolicyQualityAllLanguages
            ? m
            : RemuxRuleValues.PolicyPreferredLangsQuality;
    }

    /// <summary>Issue #497: the canonical audio keep mode; unknown stored values use "single".</summary>
    public static string NormalizeAudioKeepMode(string? raw)
    {
        var m = Py.Lower(PyStrings.Strip(raw ?? string.Empty));
        return m == RemuxRuleValues.AudioKeepModePerLanguage ? RemuxRuleValues.AudioKeepModePerLanguage : RemuxRuleValues.AudioKeepModeSingle;
    }

    /// <summary>Issue #497: the canonical subtitle quality strategy; unknown stored values use "text_first".</summary>
    public static string NormalizeSubtitleQualityStrategy(string? raw)
    {
        var m = Py.Lower(PyStrings.Strip(raw ?? string.Empty));
        return m is RemuxRuleValues.SubtitleStrategyImageFirst or RemuxRuleValues.SubtitleStrategyAccessibility
            ? m
            : RemuxRuleValues.SubtitleStrategyTextFirst;
    }

    [GeneratedRegex("^([a-z]{2,3})(?:-[a-z0-9]+)?$", RegexOptions.CultureInvariant)]
    private static partial Regex LanguageTagRegex();

    /// <summary><c>normalize_lang</c>: the primary subtag of a language tag, lower-cased.</summary>
    public static string NormalizeLang(string? tag)
    {
        if (string.IsNullOrEmpty(tag))
        {
            return string.Empty;
        }

        var s = Py.Lower(PyStrings.Strip(tag));
        if (s.Length == 0)
        {
            return string.Empty;
        }

        var match = LanguageTagRegex().Match(s);
        return match.Success ? match.Groups[1].Value : PyStrings.Slice(s, 12);
    }

    public static IReadOnlyList<string> ParseSubtitleLangsCsv(string? raw)
    {
        var result = new List<string>();
        foreach (var part in (raw ?? string.Empty).Replace("\n", ",", StringComparison.Ordinal).Split(','))
        {
            // Issue #496: preserves a recognized variant identifier instead of reducing it to its
            // base language; identical to NormalizeLang for every plain code (no fixture regresses).
            var lang = LanguageVariants.NormalizeLanguageOrVariant(part);
            if (lang.Length > 0 && !result.Contains(lang))
            {
                result.Add(lang);
            }
        }

        return result;
    }

    /// <summary><c>parse_path_lines</c>: non-blank lines, stripped.</summary>
    public static IReadOnlyList<string> ParsePathLines(string? raw)
    {
        var lines = new List<string>();
        foreach (var line in SplitLines(raw ?? string.Empty))
        {
            var s = PyStrings.Strip(line);
            if (s.Length > 0)
            {
                lines.Add(s);
            }
        }

        return lines;
    }

    /// <summary><c>str.splitlines()</c>.</summary>
    private static List<string> SplitLines(string text)
    {
        var lines = new List<string>();
        var start = 0;
        var i = 0;
        while (i < text.Length)
        {
            var c = text[i];
            if (c is '\n' or '\r' or '\v' or '\f' or '\x1c' or '\x1d' or '\x1e' or '\x85' or '\x2028' or '\x2029')
            {
                lines.Add(text[start..i]);
                i += c == '\r' && i + 1 < text.Length && text[i + 1] == '\n' ? 2 : 1;
                start = i;
            }
            else
            {
                i++;
            }
        }

        if (start < text.Length)
        {
            lines.Add(text[start..]);
        }

        return lines;
    }

    public static bool IsCommentaryAudio(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var tags = stream.Tags;
        var title = Py.Lower(tags.GetValueOrDefault("title") ?? string.Empty);
        if (title.Contains("commentary", StringComparison.Ordinal))
        {
            return true;
        }

        var comment = tags.GetValueOrDefault("comment");
        return !string.IsNullOrEmpty(comment) && Py.Lower(comment).Contains("commentary", StringComparison.Ordinal);
    }

    /// <summary>Attached fonts and similar; not part of <see cref="SplitStreams"/>.</summary>
    public static IReadOnlyList<ProbeStreamInfo> AttachmentStreams(ProbeResult probe)
    {
        ArgumentNullException.ThrowIfNull(probe);
        return probe.Streams.Where(MetadataStreams.IsAttachmentStream).ToList();
    }

    public static SplitProbeStreams SplitStreams(ProbeResult probe)
    {
        ArgumentNullException.ThrowIfNull(probe);
        var video = new List<ProbeStreamInfo>();
        var audio = new List<ProbeStreamInfo>();
        var subtitles = new List<ProbeStreamInfo>();
        foreach (var stream in probe.Streams)
        {
            var codecType = Py.Lower(PyStrings.Strip(Py.StrMethodTarget(stream.Get("codec_type"))));
            switch (codecType)
            {
                case "video":
                    video.Add(stream);
                    break;
                case "audio":
                    audio.Add(stream);
                    break;
                case "subtitle":
                    subtitles.Add(stream);
                    break;
                default:
                    break;
            }
        }

        return new SplitProbeStreams(SortByIndex(video), SortByIndex(audio), SortByIndex(subtitles));
    }

    /// <summary>
    /// <c>list.sort(key=lambda x: int(x.get("index", 0)))</c>: every key is computed first, and the
    /// sort is stable. Issue #537 item 6: a present-but-unreadable index (<c>null</c>, or text that
    /// is not a number) sorts as if it were 0 rather than failing the whole plan; the stream is
    /// dropped later, at the point a real index is actually needed.
    /// </summary>
    private static List<ProbeStreamInfo> SortByIndex(List<ProbeStreamInfo> streams)
    {
        var keys = streams.Select(s => Py.TryInt(s.Get("index"), out var n) ? n : 0).ToList();
        return streams.Select((stream, i) => (stream, key: keys[i])).OrderBy(p => p.key).Select(p => p.stream).ToList();
    }

    private static int IndexOf(ProbeStreamInfo stream) => Py.ToInt32(Py.Int(Py.Item(stream.Json, "index")));

    /// <summary>
    /// Issue #537 item 6: a stream with no usable <c>index</c> (missing, <c>null</c>, or not a
    /// number) is skipped rather than failing the whole plan.
    /// </summary>
    private static bool TryIndexOf(ProbeStreamInfo stream, out int index)
    {
        try
        {
            index = IndexOf(stream);
            return true;
        }
        catch (RulesInputException)
        {
            index = 0;
            return false;
        }
    }

    /// <summary>Streams with a usable index, paired with it, in the order given.</summary>
    private static IEnumerable<(ProbeStreamInfo Stream, int Index)> WithIndex(IEnumerable<ProbeStreamInfo> streams)
    {
        foreach (var stream in streams)
        {
            if (TryIndexOf(stream, out var index))
            {
                yield return (stream, index);
            }
        }
    }

    private static long DispositionFlag(ProbeStreamInfo stream, string name) => stream.Disposition.GetValueOrDefault(name, 0);

    /// <param name="plan">The planned remux.</param>
    /// <param name="audioProbe">The source's audio streams, for the audio comparisons and (#498) their current titles.</param>
    /// <param name="subtitleProbe">The source's subtitle streams, for the subtitle comparisons and (#498) their current titles.</param>
    /// <param name="videoProbe">
    /// #498: the source's video streams, for <see cref="MetadataRules.ClearVideoTrackNames"/>'s current-title
    /// check. Optional and defaulting to null so every pre-#498 caller (and the golden parity tests, which predate
    /// this option) keeps compiling and behaving exactly as before; when null and the option is on, a video title
    /// is assumed present (the safer of the two guesses) rather than silently skipped.
    /// </param>
    /// <param name="chaptersPresent">
    /// #498: whether the source has any chapters, for <see cref="MetadataRules.RemoveChapters"/>. Defaults to
    /// false, matching every caller from before this option existed.
    /// </param>
    public static bool IsRemuxRequired(
        RemuxPlan plan,
        IReadOnlyList<ProbeStreamInfo> audioProbe,
        IReadOnlyList<ProbeStreamInfo> subtitleProbe,
        IReadOnlyList<ProbeStreamInfo>? videoProbe = null,
        bool chaptersPresent = false)
    {
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(audioProbe);
        ArgumentNullException.ThrowIfNull(subtitleProbe);

        // A file whose only change is metadata stripping still needs a pass.
        if (plan.RemovedImages.Count > 0 || plan.RemovedAttachments.Count > 0)
        {
            return true;
        }

        if (plan.Metadata.RemoveTitle || plan.Metadata.RemoveLanguageTags || plan.Metadata.RemoveOtherMetadata)
        {
            return true;
        }

        var probeAudioIndices = WithIndex(audioProbe).Select(p => p.Index).ToList();
        if (!plan.Audio.Select(t => t.InputIndex).SequenceEqual(probeAudioIndices))
        {
            return true;
        }

        var probeSubtitleIndices = WithIndex(subtitleProbe).Select(p => p.Index).ToList();
        if (!plan.Subtitles.Select(t => t.InputIndex).SequenceEqual(probeSubtitleIndices))
        {
            return true;
        }

        var oldAudio = WithIndex(audioProbe).Select(p => (p.Index, DispositionFlag(p.Stream, "default"))).ToList();
        var newAudio = plan.Audio.Select(t => (t.InputIndex, t.Default ? 1L : 0L)).ToList();
        if (!oldAudio.SequenceEqual(newAudio))
        {
            return true;
        }

        var oldSubtitles = WithIndex(subtitleProbe).Select(p => (p.Index, DispositionFlag(p.Stream, "forced"), DispositionFlag(p.Stream, "default"))).ToList();
        var newSubtitles = plan.Subtitles.Select(t => (t.InputIndex, t.Forced ? 1L : 0L, t.Default ? 1L : 0L)).ToList();
        if (!oldSubtitles.SequenceEqual(newSubtitles))
        {
            return true;
        }

        // #498: standardized/cleared track names and chapter removal are changes too, judged against the input's
        // current titles and chapter presence so a file already conforming to the template is not remuxed again.
        if (plan.Metadata.RemoveChapters && chaptersPresent)
        {
            return true;
        }

        if (plan.Metadata.StandardizeTrackNames && TrackTitlesDiffer(plan, audioProbe, subtitleProbe))
        {
            return true;
        }

        return plan.Metadata.ClearVideoTrackNames && VideoTitlesPresent(plan.VideoIndices, videoProbe);
    }

    /// <summary>#498: true when any kept audio or subtitle track's current title does not match what <see cref="TrackNaming"/> would render for it.</summary>
    private static bool TrackTitlesDiffer(RemuxPlan plan, IReadOnlyList<ProbeStreamInfo> audioProbe, IReadOnlyList<ProbeStreamInfo> subtitleProbe)
    {
        var audioByIndex = audioProbe.ToDictionary(IndexOf, s => s);
        foreach (var track in plan.Audio)
        {
            var current = audioByIndex.TryGetValue(track.InputIndex, out var stream) ? stream.Tag("title") ?? string.Empty : string.Empty;
            if (!string.Equals(current, TrackNaming.RenderTrackName(plan.Metadata, track), StringComparison.Ordinal))
            {
                return true;
            }
        }

        var subtitleByIndex = subtitleProbe.ToDictionary(IndexOf, s => s);
        foreach (var track in plan.Subtitles)
        {
            var current = subtitleByIndex.TryGetValue(track.InputIndex, out var stream) ? stream.Tag("title") ?? string.Empty : string.Empty;
            if (!string.Equals(current, TrackNaming.RenderTrackName(plan.Metadata, track), StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>#498: true when a kept video stream already has a non-empty title, or when there is no video probe to check.</summary>
    private static bool VideoTitlesPresent(IReadOnlyList<int> videoIndices, IReadOnlyList<ProbeStreamInfo>? videoProbe)
    {
        if (videoProbe is null)
        {
            return videoIndices.Count > 0;
        }

        var videoByIndex = videoProbe.ToDictionary(IndexOf, s => s);
        foreach (var index in videoIndices)
        {
            var current = videoByIndex.TryGetValue(index, out var stream) ? stream.Tag("title") ?? string.Empty : string.Empty;
            if (current.Length > 0)
            {
                return true;
            }
        }

        return false;
    }

    private static bool IsLosslessAudio(string? codecName) => LosslessCodecs.Contains(Py.Lower(PyStrings.Strip(codecName ?? string.Empty)));

    private static List<string> OrderedPreferenceLangs(ProcessingRulesConfig config)
    {
        var result = new List<string>();
        foreach (var raw in new[] { config.PrimaryAudioLang, config.SecondaryAudioLang, config.TertiaryAudioLang })
        {
            // Issue #496: preserves a recognized variant identifier ("fre-CA") instead of reducing
            // it to its base language; identical to NormalizeLang for every plain code.
            var lang = LanguageVariants.NormalizeLanguageOrVariant(raw);
            if (lang.Length > 0 && !result.Contains(lang))
            {
                result.Add(lang);
            }
        }

        return result;
    }

    /// <summary>The first configured tier a track matches (base or variant), or -1 when none does.</summary>
    private static int TierIndexOf(List<string> preferred, string lang, string? variant)
    {
        for (var i = 0; i < preferred.Count; i++)
        {
            if (LanguageVariants.Matches(preferred[i], lang, variant))
            {
                return i;
            }
        }

        return -1;
    }

    internal sealed record AudioCandidate(
        int InputIndex,
        string LangLabel,
        string Title,
        bool Commentary,
        bool Default,
        int Channels,
        long Bitrate,
        int CodecRank,
        string CodecName,
        TrackFlags Flags,
        VariantDetection Variant);

    /// <summary>
    /// Issue #537 item 6: <c>bit_rate</c> text ffprobe cannot parse (<c>"N/A"</c> is a real value it
    /// emits for an unknown rate) is treated as unknown rather than failing the whole plan.
    /// </summary>
    private static long ReadBitRate(ProbeStreamInfo s)
    {
        try
        {
            return Py.Truthy(s.Get("bit_rate")) ? Py.Int(s.Get("bit_rate")) : 0;
        }
        catch (RulesInputException)
        {
            return 0;
        }
    }

    private static AudioCandidate CandidateFromStream(ProbeStreamInfo s, int index)
    {
        var tags = s.Tags;
        var rawLanguageTag = tags.GetValueOrDefault("language");
        var lang = NormalizeLang(rawLanguageTag);
        var disposition = s.Disposition;
        var codecName = Py.StrOr(s.Get("codec_name"), string.Empty);
        var channels = Py.ToInt32(Py.Truthy(s.Get("channels")) ? Py.Int(s.Get("channels")) : 0);
        var bitrate = ReadBitRate(s);
        var flags = TrackFlagsReader.Detect(s);
        // Issue #537 item 5: a non-string title tag (a list, say) is missing, not stringified.
        var title = tags.GetValueOrDefault("title") ?? string.Empty;
        return new AudioCandidate(
            InputIndex: index,
            LangLabel: lang,
            Title: title,
            Commentary: flags.Commentary.Value,
            Default: disposition.GetValueOrDefault("default") != 0,
            Channels: channels,
            Bitrate: bitrate,
            CodecRank: AudioCodecQualityRank(codecName),
            CodecName: codecName.Length > 0 ? codecName : "unknown",
            Flags: flags,
            // Issue #496: regional/script variant from the track's name or an explicit BCP 47 tag.
            Variant: LanguageVariants.Detect(title, lang, rawLanguageTag));
    }

    private static SortableTrack CandidateAsTrack(AudioCandidate c) => new()
    {
        Index = c.InputIndex,
        Language = c.LangLabel,
        // Issue #537 item 2: a "title" sorter now compares the stream's own title tag. The reference
        // handed it the codec name instead, so "demote a title containing X" could never match a
        // real track; kept only in golden/overrides for the cases that pinned the old behaviour.
        Title = c.Title,
        Commentary = c.Commentary,
        Default = c.Default,
        Forced = false,
        Channels = c.Channels,
        Bitrate = c.Bitrate,
        Codec = c.CodecName,
        CodecRank = c.CodecRank,
        // Issue #497: feeds the default sorters' content_tier key.
        Dub = c.Flags.Dub.Value,
        AudioDescription = c.Flags.AudioDescription.Value,
    };

    private static List<long> QualitySortKey(AudioCandidate c, int? fallbackPreferredPenalty, IReadOnlyList<TrackSorter> sorters)
    {
        var key = new List<long> { fallbackPreferredPenalty ?? 0 };
        key.AddRange(TrackSorters.SortKeyForTrack(sorters, CandidateAsTrack(c)));
        return key;
    }

    private static AudioCandidate? PickFromHint(List<AudioCandidate> pool, IReadOnlyList<int> hint)
    {
        if (hint.Count == 0)
        {
            return null;
        }

        var byIndex = new Dictionary<int, AudioCandidate>();
        foreach (var candidate in pool)
        {
            byIndex[candidate.InputIndex] = candidate;
        }

        foreach (var index in hint)
        {
            if (byIndex.TryGetValue(index, out var found))
            {
                return found;
            }
        }

        return null;
    }

    /// <summary><c>min(pool, key=...)</c>: the first candidate with the smallest key.</summary>
    private static AudioCandidate PickBest(List<AudioCandidate> pool, List<string> preferredList, bool useFallbackPenalty, IReadOnlyList<TrackSorter> sorters)
    {
        AudioCandidate? best = null;
        List<long>? bestKey = null;
        foreach (var c in pool)
        {
            int? penalty = useFallbackPenalty
                ? (c.LangLabel.Length > 0 && preferredList.Any(p => LanguageVariants.Matches(p, c.LangLabel, c.Variant.Identifier)) ? 0 : 1)
                : null;
            var key = QualitySortKey(c, penalty, sorters);
            if (bestKey is null || SortKeyComparer.Instance.Compare(key, bestKey) < 0)
            {
                best = c;
                bestKey = key;
            }
        }

        return best ?? throw new InvalidOperationException("min() arg is an empty sequence");
    }

    /// <summary>#509's removed-track records never leave <see cref="RemovedTrackRecord.Codec"/> blank.</summary>
    private static string CodecOrUnknown(string codecName) => codecName.Length > 0 ? codecName : "unknown";

    private static string DescribeCandidate(AudioCandidate c)
    {
        var lang = c.LangLabel.Length > 0 ? c.LangLabel : "unknown";
        var channels = c.Channels > 0 ? $"{c.Channels} ch" : "unknown channels";
        return $"{lang} {c.CodecName} {channels} (stream {c.InputIndex})";
    }

    private static AudioCandidate? SelectAudioWinner(ProcessingRulesConfig config, List<AudioCandidate> candidates, List<string> notes)
    {
        var policy = NormalizeAudioPreferenceMode(config.AudioPreferenceMode);
        var preferredList = OrderedPreferenceLangs(config);
        var sorters = TrackSorters.Parse(config.AudioSortersJson);
        notes.Add($"Track ranking: {TrackSorters.Describe([.. sorters])}.");

        // Original-language selection only chooses from the surviving candidates.
        var hint = config.PreferredAudioIndices;
        if (config.OriginalLanguageNote.Length > 0)
        {
            notes.Add(config.OriginalLanguageNote);
        }

        if (hint.Count > 0 && candidates.Count > 0)
        {
            var chosen = PickFromHint(candidates, hint);
            if (chosen is not null)
            {
                notes.Add($"Selected {DescribeCandidate(chosen)} by original language.");
                return chosen;
            }
        }

        if (candidates.Count == 0)
        {
            notes.Add("No eligible audio tracks after commentary and probe rules.");
            return null;
        }

        if (policy == RemuxRuleValues.PolicyQualityAllLanguages)
        {
            var w = PickBest(candidates, preferredList, useFallbackPenalty: false, sorters);
            notes.Add($"Selected {DescribeCandidate(w)} using quality across all languages (policy: quality across all languages).");
            return w;
        }

        if (policy == RemuxRuleValues.PolicyPreferredLangsStrict)
        {
            // Issue #496: a variant identifier is accepted here too, same as the tier walk below.
            var primary = LanguageVariants.NormalizeLanguageOrVariant(config.PrimaryAudioLang);
            if (primary.Length == 0)
            {
                notes.Add("Strict policy requires a primary language; none configured.");
                return null;
            }

            var pool = candidates.Where(c => LanguageVariants.Matches(primary, c.LangLabel, c.Variant.Identifier)).ToList();
            if (pool.Count == 0)
            {
                notes.Add($"No audio tracks matched primary language '{primary}' (strict policy — no fallback to secondary or other languages).");
                return null;
            }

            var w = PickBest(pool, preferredList, useFallbackPenalty: false, sorters);
            notes.Add($"Selected {DescribeCandidate(w)} using primary language only (strict policy).");
            return w;
        }

        // preferred_langs_quality: tier walk, then fallback. Issue #496: a tier that is a plain
        // base language ("fre") matches every variant of it, unchanged; a tier that is a variant
        // identifier ("fre-CA") matches only a track detected as that exact variant.
        foreach (var tierLang in preferredList)
        {
            var pool = candidates.Where(c => LanguageVariants.Matches(tierLang, c.LangLabel, c.Variant.Identifier)).ToList();
            if (pool.Count == 0)
            {
                continue;
            }

            var w = PickBest(pool, preferredList, useFallbackPenalty: false, sorters);
            var others = pool.Where(c => c.InputIndex != w.InputIndex).ToList();
            if (others.Count > 0)
            {
                var otherText = string.Join("; ", others.OrderBy(x => x.InputIndex).Select(DescribeCandidate));
                notes.Add($"Selected {DescribeCandidate(w)} over {otherText} within the same language tier (ranked by quality).");
            }
            else
            {
                notes.Add($"Selected {DescribeCandidate(w)} as the only track in the first matching language tier.");
            }

            return w;
        }

        var fallback = PickBest(candidates, preferredList, useFallbackPenalty: true, sorters);
        var tiers = preferredList.Count > 0 ? string.Join(", ", preferredList) : "none";
        notes.Add(
            $"Fell back to {DescribeCandidate(fallback)} because no track matched configured language tiers ({tiers}); ranked by quality with preferred-language matches first.");
        return fallback;
    }

    /// <summary>Builds the kept <see cref="PlannedTrack"/> for one audio candidate, re-reading its own stream's disposition and codec name.</summary>
    private static PlannedTrack BuildPlannedAudioTrack(IReadOnlyList<ProbeStreamInfo> audio, AudioCandidate candidate, bool isDefault)
    {
        var stream = WithIndex(audio).Where(p => p.Index == candidate.InputIndex).Select(p => p.Stream).FirstOrDefault();
        var disposition = stream?.Disposition ?? new Dictionary<string, long>();
        var codecName = stream is null ? string.Empty : Py.StrOr(stream.Get("codec_name"), string.Empty);

        return new PlannedTrack
        {
            InputIndex = candidate.InputIndex,
            LangLabel = candidate.LangLabel,
            Commentary = candidate.Commentary,
            Forced = disposition.GetValueOrDefault("forced") != 0,
            Default = isDefault,
            Channels = candidate.Channels,
            Lossless = IsLosslessAudio(codecName),
            Bitrate = candidate.Bitrate,
            CodecRank = candidate.CodecRank,
            CodecName = codecName,
            Kind = TrackKind.Audio,
            Variant = candidate.Variant.Identifier,
        };
    }

    /// <summary>
    /// Issue #495 step 5 and issue #496: say when a kept track's dub/audio-description flag came
    /// from its name rather than a stream flag, and which regional/script variant it was detected
    /// as. Shared by the single winner and every track kept under <c>per_language</c>.
    /// </summary>
    private static void AddCandidateFlagNotes(AudioCandidate candidate, List<string> notes)
    {
        if (candidate.Flags.Dub.FromName)
        {
            notes.Add($"The selected track ({DescribeCandidate(candidate)}) looks like a dub track from its name; ffprobe reported no dub flag.");
        }

        if (candidate.Flags.AudioDescription.FromName)
        {
            notes.Add($"The selected track ({DescribeCandidate(candidate)}) looks like an audio-description track from its name; ffprobe reported no such flag.");
        }

        if (candidate.Variant.Found)
        {
            var provenance = candidate.Variant.Source == VariantSource.Tag
                ? $"the language tag '{candidate.Variant.Marker}'"
                : $"the track name '{candidate.Variant.Marker}'";
            notes.Add($"{LanguageVariants.DisplayName(candidate.Variant.Identifier!)}, from {provenance}.");
        }
    }

    /// <summary>
    /// Issue #497: <c>audio_keep_mode: per_language</c>. Keeps the best track (by the configured
    /// sorters) of each configured language slot (primary, then secondary, then tertiary) that has
    /// one, instead of a single overall winner. Never returns an empty list when there is at least
    /// one candidate: a file with no track in any configured slot still keeps its best track
    /// overall, the same "never zero audio" guarantee <see cref="SelectAudioWinner"/> gives single
    /// mode.
    /// </summary>
    private static (List<AudioCandidate> Kept, int DefaultIndex) SelectPerLanguageAudioTracks(
        ProcessingRulesConfig config, List<AudioCandidate> candidates, List<string> notes)
    {
        var sorters = TrackSorters.Parse(config.AudioSortersJson);
        notes.Add($"Track ranking: {TrackSorters.Describe([.. sorters])}.");

        var slots = OrderedPreferenceLangs(config);
        var kept = new List<AudioCandidate>();
        var keptSlotLangs = new List<string>();

        foreach (var slotLang in slots)
        {
            var pool = candidates.Where(c => LanguageVariants.Matches(slotLang, c.LangLabel, c.Variant.Identifier)).ToList();
            if (pool.Count == 0)
            {
                notes.Add($"No {RemuxDisplay.LangDisplay(slotLang)} audio track available for that language slot; skipped.");
                continue;
            }

            var best = PickBest(pool, [], useFallbackPenalty: false, sorters);
            kept.Add(best);
            keptSlotLangs.Add(slotLang);

            var others = pool.Where(c => c.InputIndex != best.InputIndex).OrderBy(c => c.InputIndex).ToList();
            notes.Add(others.Count > 0
                ? $"Kept {DescribeCandidate(best)} for {RemuxDisplay.LangDisplay(slotLang)} over {string.Join("; ", others.Select(DescribeCandidate))}."
                : $"Kept {DescribeCandidate(best)} as the only {RemuxDisplay.LangDisplay(slotLang)} audio track.");
        }

        if (kept.Count == 0 && candidates.Count > 0)
        {
            // Never zero audio: no configured slot matched anything, so fall back to the best
            // candidate overall, exactly as single mode's fallback does.
            var preferredList = OrderedPreferenceLangs(config);
            var fallback = PickBest(candidates, preferredList, useFallbackPenalty: true, sorters);
            kept.Add(fallback);
            keptSlotLangs.Add(fallback.LangLabel);
            notes.Add($"No configured audio language slot matched any track; kept {DescribeCandidate(fallback)} by quality alone (never zero audio).");
        }

        var wantsSecondaryDefault = Py.Lower(PyStrings.Strip(config.DefaultAudioSlot)) == RemuxRuleValues.DefaultAudioSlotSecondary;
        var defaultSlot = wantsSecondaryDefault && slots.Count > 1 ? slots[1] : slots.Count > 0 ? slots[0] : string.Empty;
        var defaultIndex = keptSlotLangs.IndexOf(defaultSlot);
        if (defaultIndex < 0)
        {
            defaultIndex = kept.Count > 0 ? 0 : -1;
        }

        return (kept, defaultIndex);
    }

    // --- issue #497: subtitle cap per language --------------------------------------------

    /// <summary>Text formats the "text first" strategy prefers over an image format.</summary>
    private static readonly HashSet<string> TextSubtitleCodecs =
        new(StringComparer.Ordinal) { "subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text" };

    /// <summary>Image (bitmap) subtitle formats: no text to extract, so a player just overlays the image.</summary>
    private static readonly HashSet<string> ImageSubtitleCodecs =
        new(StringComparer.Ordinal) { "hdmv_pgs_subtitle", "pgs", "dvd_subtitle", "vobsub", "dvb_subtitle", "dvbsub", "xsub" };

    private static readonly string[] OrdinalWords =
        ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"];

    private static string Ordinal(int position) => position >= 0 && position < OrdinalWords.Length ? OrdinalWords[position] : $"{position}th";

    /// <summary>A short, human word for a subtitle's format, for the cap's plan notes (e.g. "kept the text track over PGS").</summary>
    private static string SubtitleFormatWord(string codecName)
    {
        var c = Py.Lower(PyStrings.Strip(codecName));
        if (TextSubtitleCodecs.Contains(c))
        {
            return "text";
        }

        return c switch
        {
            "hdmv_pgs_subtitle" or "pgs" => "PGS",
            "dvd_subtitle" or "vobsub" => "VobSub",
            "dvb_subtitle" or "dvbsub" => "DVB subtitle",
            "xsub" => "XSUB",
            "" => "unknown format",
            _ => Py.Upper(c),
        };
    }

    /// <summary>0 (best) to 2 (worst): text over image, or the reverse under <c>image_first</c>. An unrecognized codec sits in the middle.</summary>
    private static long SubtitleFormatRank(string codecName, string strategy)
    {
        var c = Py.Lower(PyStrings.Strip(codecName));
        var isText = TextSubtitleCodecs.Contains(c);
        var isImage = ImageSubtitleCodecs.Contains(c);
        if (strategy == RemuxRuleValues.SubtitleStrategyImageFirst)
        {
            return isImage ? 0 : isText ? 2 : 1;
        }

        return isText ? 0 : isImage ? 2 : 1;
    }

    private enum SubtitleTypeKind
    {
        Regular,
        HearingImpaired,
        Forced,
    }

    /// <summary>A forced track always classifies as forced, even one not exempt from the cap (preserve-forced off).</summary>
    private static SubtitleTypeKind ClassifySubtitleType(SubtitleCandidate candidate) =>
        candidate.ForcedRaw ? SubtitleTypeKind.Forced : candidate.HearingImpaired ? SubtitleTypeKind.HearingImpaired : SubtitleTypeKind.Regular;

    /// <summary>0 (best) to 2 (worst): regular over SDH over forced, or SDH first under <c>accessibility</c>.</summary>
    private static long SubtitleTypeRank(SubtitleTypeKind type, string strategy)
    {
        if (strategy == RemuxRuleValues.SubtitleStrategyAccessibility)
        {
            return type switch
            {
                SubtitleTypeKind.HearingImpaired => 0,
                SubtitleTypeKind.Regular => 1,
                _ => 2,
            };
        }

        return type switch
        {
            SubtitleTypeKind.Regular => 0,
            SubtitleTypeKind.HearingImpaired => 1,
            _ => 2,
        };
    }

    /// <summary>
    /// Issue #497: text (or image, forced) over image, then type (regular over SDH over forced) —
    /// or, under <c>accessibility</c>, SDH first and format only breaks a tie.
    /// </summary>
    private static List<long> SubtitleQualityKey(SubtitleCandidate candidate, string strategy)
    {
        var format = SubtitleFormatRank(candidate.CodecName, strategy);
        var type = SubtitleTypeRank(ClassifySubtitleType(candidate), strategy);
        return strategy == RemuxRuleValues.SubtitleStrategyAccessibility ? [type, format] : [format, type];
    }

    /// <summary>One subtitle stream that matched a configured language, before the per-language cap is applied.</summary>
    private sealed record SubtitleCandidate(int Tier, string Lang, string? Variant, string CodecName, bool HearingImpaired, bool ForcedRaw, PlannedTrack Track)
    {
        public int InputIndex => Track.InputIndex;
    }

    /// <summary>
    /// Issue #497: <c>subtitle_max_per_language</c> (0 = unlimited, today's behaviour). Groups the
    /// matched candidates by the configured language slot they matched (<see cref="SubtitleCandidate.Tier"/>,
    /// so a variant-specific slot and its base language are never conflated), keeps every forced
    /// track preserved under <see cref="ProcessingRulesConfig.PreserveForcedSubs"/> unconditionally
    /// (it never counts toward the cap), and otherwise keeps only the best
    /// <see cref="ProcessingRulesConfig.SubtitleMaxPerLanguage"/> by <see cref="SubtitleQualityKey"/>,
    /// noting each drop with the reason (e.g. "kept the text track over PGS").
    /// </summary>
    private static List<PlannedTrack> ApplySubtitleCap(
        List<SubtitleCandidate> candidates, ProcessingRulesConfig config, List<string> notes, List<string> removedSubtitleLabels)
    {
        if (config.SubtitleMaxPerLanguage <= 0)
        {
            return candidates.Select(c => c.Track).ToList();
        }

        var strategy = NormalizeSubtitleQualityStrategy(config.SubtitleQualityStrategy);
        var cap = config.SubtitleMaxPerLanguage;
        var result = new List<PlannedTrack>();

        foreach (var group in candidates.GroupBy(c => c.Tier))
        {
            var groupList = group.ToList();
            var exempt = groupList.Where(c => c.Track.Forced).ToList();
            var pool = groupList.Where(c => !c.Track.Forced).ToList();
            result.AddRange(exempt.Select(c => c.Track));

            if (pool.Count <= cap)
            {
                result.AddRange(pool.Select(c => c.Track));
                continue;
            }

            var ranked = pool
                .Select(c => (Candidate: c, Key: SubtitleQualityKey(c, strategy)))
                .OrderBy(p => p.Key, SortKeyComparer.Instance)
                .ThenBy(p => p.Candidate.InputIndex)
                .Select(p => p.Candidate)
                .ToList();

            var keep = ranked.Take(cap).ToList();
            var drop = ranked.Skip(cap).ToList();
            result.AddRange(keep.Select(c => c.Track));

            var best = keep[0];
            var byFileOrder = groupList.OrderBy(c => c.InputIndex).ToList();
            foreach (var dropped in drop.OrderBy(c => c.InputIndex))
            {
                var position = byFileOrder.FindIndex(c => c.InputIndex == dropped.InputIndex) + 1;
                var langLabel = dropped.Variant is not null ? LanguageVariants.DisplayName(dropped.Variant) : RemuxDisplay.LangDisplayOrBlank(dropped.Lang);
                if (langLabel.Length == 0)
                {
                    langLabel = "Undetermined";
                }

                notes.Add(
                    $"Dropped the {Ordinal(position)} {langLabel} subtitle (stream {dropped.InputIndex}); " +
                    $"kept the {SubtitleFormatWord(best.CodecName)} track over {SubtitleFormatWord(dropped.CodecName)}.");
                removedSubtitleLabels.Add(dropped.Lang.Length > 0 ? dropped.Lang : "und");
            }
        }

        return result;
    }

    /// <summary>
    /// A single winning audio track (issue #497: or one per configured language slot under
    /// <c>audio_keep_mode: per_language</c>), the subtitle retention policy and metadata stripping.
    /// Null when no audio would remain.
    /// </summary>
    public static RemuxPlan? PlanRemux(
        IReadOnlyList<ProbeStreamInfo> video,
        IReadOnlyList<ProbeStreamInfo> audio,
        IReadOnlyList<ProbeStreamInfo> subtitles,
        ProcessingRulesConfig config,
        IReadOnlyList<ProbeStreamInfo>? attachments = null)
    {
        ArgumentNullException.ThrowIfNull(video);
        ArgumentNullException.ThrowIfNull(audio);
        ArgumentNullException.ThrowIfNull(subtitles);
        ArgumentNullException.ThrowIfNull(config);

        var rules = config.Metadata;
        // Always split, so the plan knows which stream is the picture even when the poster is kept.
        var (realVideo, imageStreams) = MetadataStreams.SplitVideoAndImages(video);
        IReadOnlyList<ProbeStreamInfo> droppedImages = rules.RemoveImages ? imageStreams : [];
        var keptVideo = rules.RemoveImages ? realVideo : video;
        var videoIndices = keptVideo.Select(IndexOf).ToList();
        IReadOnlyList<ProbeStreamInfo> droppedAttachments = rules.RemoveAttachments
            ? (attachments ?? []).Where(MetadataStreams.IsAttachmentStream).ToList()
            : [];

        var removedAudio = new List<string>();
        var removedTrackRecords = new List<RemovedTrackRecord>();
        var notes = new List<string>();
        var candidates = new List<AudioCandidate>();

        foreach (var (s, streamIndex) in WithIndex(audio))
        {
            // Issue #495: commentary now flows through TrackFlags (disposition first, then the
            // name), which behaves exactly like the older title/comment-tag check for every track
            // that has no disposition.comment flag set — the only source ffprobe fixtures use today.
            var flags = TrackFlagsReader.Detect(s);
            if (config.RemoveCommentary && flags.Commentary.Value)
            {
                var rawLanguageTag = s.Tag("language");
                var lang = NormalizeLang(rawLanguageTag);
                var langLabel = lang.Length > 0 ? lang : "und";
                removedAudio.Add($"{langLabel} (commentary excluded — remove commentary enabled)");
                removedTrackRecords.Add(new RemovedTrackRecord
                {
                    Language = langLabel,
                    Type = RemovedTrackType.Audio,
                    Codec = CodecOrUnknown(s.CodecName),
                    // Issue #496: regional/script variant from the track's name or an explicit BCP 47 tag.
                    Variant = LanguageVariants.DetectVariant(s.Tag("title"), lang, rawLanguageTag),
                    Reason = "commentary excluded — remove commentary enabled",
                });
                notes.Add($"Excluded commentary track (stream {streamIndex}) because remove commentary is enabled.");
                continue;
            }

            candidates.Add(CandidateFromStream(s, streamIndex));
        }

        List<PlannedTrack> keptAudioTracks;
        int defaultAudioOutputIndex;

        if (NormalizeAudioKeepMode(config.AudioKeepMode) == RemuxRuleValues.AudioKeepModePerLanguage)
        {
            var (keptCandidates, defaultIndex) = SelectPerLanguageAudioTracks(config, [.. candidates], notes);
            if (keptCandidates.Count == 0)
            {
                notes.Add("No eligible audio tracks after commentary and probe rules.");
                return null;
            }

            keptAudioTracks = new List<PlannedTrack>(keptCandidates.Count);
            for (var i = 0; i < keptCandidates.Count; i++)
            {
                var candidate = keptCandidates[i];
                AddCandidateFlagNotes(candidate, notes);
                keptAudioTracks.Add(BuildPlannedAudioTrack(audio, candidate, isDefault: i == defaultIndex));
            }

            defaultAudioOutputIndex = defaultIndex >= 0 ? defaultIndex : 0;

            var keptIndices = keptAudioTracks.Select(t => t.InputIndex).ToHashSet();
            foreach (var c in candidates.Where(c => !keptIndices.Contains(c.InputIndex)).OrderBy(c => c.InputIndex))
            {
                removedAudio.Add($"{DescribeCandidate(c)}: removed (not selected for its language slot)");
                removedTrackRecords.Add(new RemovedTrackRecord
                {
                    Language = c.LangLabel.Length > 0 ? c.LangLabel : "und",
                    Type = RemovedTrackType.Audio,
                    Codec = CodecOrUnknown(c.CodecName),
                    Variant = c.Variant.Identifier,
                    Reason = "not selected for its language slot",
                });
                notes.Add($"Removed non-selected {DescribeCandidate(c)}.");
            }
        }
        else
        {
            var policy = NormalizeAudioPreferenceMode(config.AudioPreferenceMode);

            var winner = SelectAudioWinner(config, [.. candidates], notes);
            if (winner is null)
            {
                return null;
            }

            AddCandidateFlagNotes(winner, notes);

            // Retention: one winner; every other audio stream is removed.
            var winnerIndex = winner.InputIndex;
            foreach (var c in candidates.Where(c => c.InputIndex != winnerIndex))
            {
                removedAudio.Add($"{DescribeCandidate(c)}: removed (not selected — {DescribeCandidate(winner)} kept)");
                removedTrackRecords.Add(new RemovedTrackRecord
                {
                    Language = c.LangLabel.Length > 0 ? c.LangLabel : "und",
                    Type = RemovedTrackType.Audio,
                    Codec = CodecOrUnknown(c.CodecName),
                    Variant = c.Variant.Identifier,
                    Reason = $"not selected — {DescribeCandidate(winner)} kept",
                });
                notes.Add($"Removed non-selected {DescribeCandidate(c)} after selecting {DescribeCandidate(winner)}.");
            }

            if (policy == RemuxRuleValues.PolicyPreferredLangsQuality)
            {
                var preferred = OrderedPreferenceLangs(config);
                // Issue #496: a variant tier ("fre-CA") only ever matches its own variant, so this
                // looks up the tier by base-or-variant match instead of the track's plain language.
                var winnerTier = TierIndexOf(preferred, winner.LangLabel, winner.Variant.Identifier);
                if (preferred.Count > 1 && winnerTier >= 0)
                {
                    foreach (var c in candidates)
                    {
                        if (c.InputIndex == winnerIndex)
                        {
                            continue;
                        }

                        if (TierIndexOf(preferred, c.LangLabel, c.Variant.Identifier) > winnerTier)
                        {
                            notes.Add(
                                $"Ignored {DescribeCandidate(c)} because preferred languages (tiered quality) had candidates in '{winner.LangLabel}' first.");
                        }
                    }
                }
            }

            keptAudioTracks = [BuildPlannedAudioTrack(audio, winner, isDefault: true)];
            defaultAudioOutputIndex = 0;
        }

        var keptSubtitles = new List<PlannedTrack>();
        var removedSubtitleLabels = new List<string>();
        if (config.SubtitleMode == RemuxRuleValues.SubtitleModeRemoveAll || config.SubtitleLangs.Count == 0)
        {
            foreach (var s in subtitles)
            {
                var rawLanguageTag = s.Tag("language");
                var lang = NormalizeLang(rawLanguageTag);
                var langLabel = lang.Length > 0 ? lang : "und";
                removedSubtitleLabels.Add(langLabel);
                removedTrackRecords.Add(new RemovedTrackRecord
                {
                    Language = langLabel,
                    Type = RemovedTrackType.Subtitle,
                    Codec = CodecOrUnknown(s.CodecName),
                    // Issue #496: regional/script variant from the track's name or an explicit BCP 47 tag.
                    Variant = LanguageVariants.DetectVariant(s.Tag("title"), lang, rawLanguageTag),
                    Reason = "subtitle mode removes every subtitle track",
                });
            }
        }
        else
        {
            // Issue #537 item 3: configured subtitle languages are normalized the same way a
            // track's own tag is, so "ENG" or "en-US" matches a file tagged "eng". Issue #496: a
            // repeated language keeps its last position (as before); a variant identifier
            // ("fre-CA") is kept distinct from its base ("fre") rather than collapsed into it.
            var rank = new Dictionary<string, int>(StringComparer.Ordinal);
            for (var n = 0; n < config.SubtitleLangs.Count; n++)
            {
                rank[LanguageVariants.NormalizeLanguageOrVariant(config.SubtitleLangs[n])] = n;
            }

            var subtitleCandidates = new List<SubtitleCandidate>();

            foreach (var (s, index) in WithIndex(subtitles))
            {
                var rawLanguageTag = s.Tag("language");
                var lang = NormalizeLang(rawLanguageTag);
                var langLabel = lang.Length > 0 ? lang : "und";
                var disposition = s.Disposition;

                // A variant-specific tier ("fre-CA") takes priority over a broader base tier
                // ("fre") when a track matches both; a plain base tier still matches every variant.
                var variant = LanguageVariants.DetectVariant(s.Tag("title"), lang, rawLanguageTag);
                var matchedTier = variant is not null && rank.TryGetValue(variant, out var variantRank)
                    ? variantRank
                    : rank.GetValueOrDefault(lang, -1);
                if (lang.Length == 0 || matchedTier < 0)
                {
                    removedSubtitleLabels.Add(langLabel);
                    removedTrackRecords.Add(new RemovedTrackRecord
                    {
                        Language = langLabel,
                        Type = RemovedTrackType.Subtitle,
                        Codec = CodecOrUnknown(s.CodecName),
                        Variant = variant,
                        Reason = "language not kept by subtitle rules",
                    });
                    continue;
                }

                // Issue #495: forced now also comes from the name (a signs track counts as forced),
                // and a hearing-impaired track can be dropped outright when the rule is enabled.
                var flags = TrackFlagsReader.Detect(s);
                if (config.RemoveHearingImpairedSubs && flags.HearingImpaired.Value)
                {
                    removedSubtitleLabels.Add(langLabel);
                    removedTrackRecords.Add(new RemovedTrackRecord
                    {
                        Language = langLabel,
                        Type = RemovedTrackType.Subtitle,
                        Codec = CodecOrUnknown(s.CodecName),
                        Variant = variant,
                        Reason = "hearing-impaired subtitle removed",
                    });
                    var hiSource = flags.HearingImpaired.Source == TrackFlagSource.Disposition ? "its hearing-impaired flag" : "its name";
                    notes.Add($"Removed hearing-impaired subtitle track (stream {index}) because remove hearing-impaired subtitles is enabled ({hiSource}).");
                    continue;
                }

                var forced = config.PreserveForcedSubs && flags.Forced.Value;
                if (forced && flags.Forced.Source == TrackFlagSource.Name)
                {
                    notes.Add($"Subtitle track (stream {index}) counts as forced because its name says so; ffprobe reported no forced flag.");
                }

                var track = new PlannedTrack
                {
                    InputIndex = index,
                    LangLabel = lang,
                    Forced = forced,
                    Default = config.PreserveDefaultSubs && disposition.GetValueOrDefault("default") != 0,
                    Kind = TrackKind.Subtitle,
                    Variant = variant,
                };

                subtitleCandidates.Add(new SubtitleCandidate(
                    Tier: matchedTier,
                    Lang: lang,
                    Variant: variant,
                    CodecName: Py.StrOr(s.Get("codec_name"), string.Empty),
                    HearingImpaired: flags.HearingImpaired.Value,
                    ForcedRaw: flags.Forced.Value,
                    Track: track));
            }

            // Issue #497: cap how many subtitles survive per configured language slot (0 =
            // unlimited, today's behaviour). A forced track kept under preserve-forced is exempt.
            keptSubtitles = ApplySubtitleCap(subtitleCandidates, config, notes, removedSubtitleLabels);

            keptSubtitles = [.. keptSubtitles
                .OrderBy(t => t.Variant is not null && rank.TryGetValue(t.Variant, out var vr) ? vr : rank.GetValueOrDefault(t.LangLabel, 99))
                .ThenBy(t => t.InputIndex)];
        }

        return new RemuxPlan
        {
            VideoIndices = videoIndices,
            Audio = keptAudioTracks,
            Subtitles = keptSubtitles,
            RemovedAudio = removedAudio,
            RemovedSubtitles = removedSubtitleLabels,
            RemovedTrackRecords = removedTrackRecords,
            DefaultAudioOutputIndex = defaultAudioOutputIndex,
            AudioSelectionNotes = notes,
            RemovedImages = droppedImages.Select(MetadataStreams.DescribeImageStream).ToList(),
            RemovedAttachments = droppedAttachments.Select(MetadataStreams.DescribeAttachmentStream).ToList(),
            MetadataNotes = MetadataStreams.RemovalNotes(rules, droppedImages, droppedAttachments),
            Metadata = rules,
        };
    }

    /// <summary>Sane defaults for remux planning (<c>default_processing_remux_rules_config</c>).</summary>
    public static ProcessingRulesConfig DefaultConfig() => new()
    {
        PrimaryAudioLang = "eng",
        SecondaryAudioLang = "jpn",
        TertiaryAudioLang = string.Empty,
        DefaultAudioSlot = RemuxRuleValues.DefaultAudioSlotPrimary,
        RemoveCommentary = true,
        SubtitleMode = RemuxRuleValues.SubtitleModeRemoveAll,
        SubtitleLangs = [],
        PreserveForcedSubs = true,
        PreserveDefaultSubs = true,
        AudioPreferenceMode = RemuxRuleValues.PolicyPreferredLangsQuality,
        RemoveHearingImpairedSubs = false,
        AudioKeepMode = RemuxRuleValues.AudioKeepModeSingle,
        SubtitleMaxPerLanguage = 0,
        SubtitleQualityStrategy = RemuxRuleValues.SubtitleStrategyTextFirst,
    };
}
