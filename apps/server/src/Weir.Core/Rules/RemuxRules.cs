using System.Text.RegularExpressions;

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
}

/// <summary>
/// The rules in force for one pass (<c>refiner_remux_rules.RefinerRulesConfig</c>).
/// <see cref="SubtitleMode"/> and <see cref="AudioPreferenceMode"/> stay strings: the planner
/// treats any subtitle mode other than <c>remove_all</c> as keep-selected and normalizes an
/// unknown policy to the default, exactly as the reference does.
/// </summary>
public sealed record RefinerRulesConfig
{
    public required string PrimaryAudioLang { get; init; }
    public required string SecondaryAudioLang { get; init; }
    public required string TertiaryAudioLang { get; init; }
    public required string DefaultAudioSlot { get; init; }
    public required bool RemoveCommentary { get; init; }
    public required string SubtitleMode { get; init; }

    /// <summary>Compared as stored: the planner does not normalize these, so "ENG" never matches a normalized "eng" tag.</summary>
    public required IReadOnlyList<string> SubtitleLangs { get; init; }

    public required bool PreserveForcedSubs { get; init; }
    public required bool PreserveDefaultSubs { get; init; }
    public required string AudioPreferenceMode { get; init; }

    /// <summary>The ordered sorter list, as stored JSON. Empty means the seeded default.</summary>
    public string AudioSortersJson { get; init; } = string.Empty;

    /// <summary>Metadata and attachment stripping. All off by default.</summary>
    public MetadataRules Metadata { get; init; } = new();

    /// <summary>Carried for the pass; the planner itself reads only the resolved hint below.</summary>
    public OriginalLanguageRules? OriginalLanguage { get; init; }

    /// <summary>Input indices the pass wants preferred, in order, from the metadata lookup.</summary>
    public IReadOnlyList<int> PreferredAudioIndices { get; init; } = [];

    /// <summary>The sentence explaining which mechanism chose, appended to the selection notes.</summary>
    public string OriginalLanguageNote { get; init; } = string.Empty;
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
}

/// <summary>What one pass writes (<c>RemuxPlan</c>).</summary>
public sealed record RemuxPlan
{
    public required IReadOnlyList<int> VideoIndices { get; init; }
    public required IReadOnlyList<PlannedTrack> Audio { get; init; }
    public required IReadOnlyList<PlannedTrack> Subtitles { get; init; }
    public IReadOnlyList<string> RemovedAudio { get; init; } = [];
    public IReadOnlyList<string> RemovedSubtitles { get; init; } = [];
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
/// Remux planning (<c>refiner_remux_rules.py</c>): stream splitting, audio candidate ranking under
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
    /// Containers Refiner can genuinely process. Raw elementary streams (<c>.h264</c>, <c>.h265</c>,
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
        var c = Py.Lower(Py.Strip(codecName ?? string.Empty));
        if (c.Length == 0)
        {
            return CodecUnknownRank;
        }

        return CodecRankLookup.TryGetValue(c, out var rank) ? rank : CodecUnknownRank;
    }

    /// <summary>The canonical policy; unknown stored values use the default policy.</summary>
    public static string NormalizeAudioPreferenceMode(string? raw)
    {
        var m = Py.Lower(Py.Strip(raw ?? string.Empty));
        return m is RemuxRuleValues.PolicyPreferredLangsQuality or RemuxRuleValues.PolicyPreferredLangsStrict or RemuxRuleValues.PolicyQualityAllLanguages
            ? m
            : RemuxRuleValues.PolicyPreferredLangsQuality;
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

        var s = Py.Lower(Py.Strip(tag));
        if (s.Length == 0)
        {
            return string.Empty;
        }

        var match = LanguageTagRegex().Match(s);
        return match.Success ? match.Groups[1].Value : Py.Slice(s, 12);
    }

    public static IReadOnlyList<string> ParseSubtitleLangsCsv(string? raw)
    {
        var result = new List<string>();
        foreach (var part in (raw ?? string.Empty).Replace("\n", ",", StringComparison.Ordinal).Split(','))
        {
            var lang = NormalizeLang(part);
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
            var s = Py.Strip(line);
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
            var codecType = Py.Lower(Py.Strip(Py.StrMethodTarget(stream.Get("codec_type"))));
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

    /// <summary><c>list.sort(key=lambda x: int(x.get("index", 0)))</c>: every key is computed first, and the sort is stable.</summary>
    private static List<ProbeStreamInfo> SortByIndex(List<ProbeStreamInfo> streams)
    {
        var keys = streams.Select(s => s.Get("index") is { } index ? Py.Int(index) : 0).ToList();
        return streams.Select((stream, i) => (stream, key: keys[i])).OrderBy(p => p.key).Select(p => p.stream).ToList();
    }

    private static int IndexOf(ProbeStreamInfo stream) => Py.ToInt32(Py.Int(Py.Item(stream.Json, "index")));

    private static long DispositionFlag(ProbeStreamInfo stream, string name) => stream.Disposition.GetValueOrDefault(name, 0);

    public static bool IsRemuxRequired(RemuxPlan plan, IReadOnlyList<ProbeStreamInfo> audioProbe, IReadOnlyList<ProbeStreamInfo> subtitleProbe)
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

        var probeAudioIndices = audioProbe.Select(IndexOf).ToList();
        if (!plan.Audio.Select(t => t.InputIndex).SequenceEqual(probeAudioIndices))
        {
            return true;
        }

        var probeSubtitleIndices = subtitleProbe.Select(IndexOf).ToList();
        if (!plan.Subtitles.Select(t => t.InputIndex).SequenceEqual(probeSubtitleIndices))
        {
            return true;
        }

        var oldAudio = audioProbe.Select(s => (IndexOf(s), DispositionFlag(s, "default"))).ToList();
        var newAudio = plan.Audio.Select(t => (t.InputIndex, t.Default ? 1L : 0L)).ToList();
        if (!oldAudio.SequenceEqual(newAudio))
        {
            return true;
        }

        var oldSubtitles = subtitleProbe.Select(s => (IndexOf(s), DispositionFlag(s, "forced"), DispositionFlag(s, "default"))).ToList();
        var newSubtitles = plan.Subtitles.Select(t => (t.InputIndex, t.Forced ? 1L : 0L, t.Default ? 1L : 0L)).ToList();
        return !oldSubtitles.SequenceEqual(newSubtitles);
    }

    private static bool IsLosslessAudio(string? codecName) => LosslessCodecs.Contains(Py.Lower(Py.Strip(codecName ?? string.Empty)));

    private static List<string> OrderedPreferenceLangs(RefinerRulesConfig config)
    {
        var result = new List<string>();
        foreach (var raw in new[] { config.PrimaryAudioLang, config.SecondaryAudioLang, config.TertiaryAudioLang })
        {
            var lang = NormalizeLang(raw);
            if (lang.Length > 0 && !result.Contains(lang))
            {
                result.Add(lang);
            }
        }

        return result;
    }

    internal sealed record AudioCandidate(
        int InputIndex,
        string LangLabel,
        bool Commentary,
        bool Default,
        int Channels,
        long Bitrate,
        int CodecRank,
        string CodecName);

    private static AudioCandidate CandidateFromStream(ProbeStreamInfo s)
    {
        var tags = s.Tags;
        var index = IndexOf(s);
        var lang = NormalizeLang(tags.GetValueOrDefault("language"));
        var disposition = s.Disposition;
        var codecName = Py.StrOr(s.Get("codec_name"), string.Empty);
        var channels = Py.ToInt32(Py.Truthy(s.Get("channels")) ? Py.Int(s.Get("channels")) : 0);
        var bitrate = Py.Truthy(s.Get("bit_rate")) ? Py.Int(s.Get("bit_rate")) : 0;
        return new AudioCandidate(
            InputIndex: index,
            LangLabel: lang,
            Commentary: IsCommentaryAudio(s),
            Default: disposition.GetValueOrDefault("default") != 0,
            Channels: channels,
            Bitrate: bitrate,
            CodecRank: AudioCodecQualityRank(codecName),
            CodecName: codecName.Length > 0 ? codecName : "unknown");
    }

    private static SortableTrack CandidateAsTrack(AudioCandidate c) => new()
    {
        Index = c.InputIndex,
        Language = c.LangLabel,
        // The reference hands the codec name to the "title" sorter, so a title sorter matches codec names. Kept as-is for parity.
        Title = c.CodecName,
        Commentary = c.Commentary,
        Default = c.Default,
        Forced = false,
        Channels = c.Channels,
        Bitrate = c.Bitrate,
        Codec = c.CodecName,
        CodecRank = c.CodecRank,
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
    private static AudioCandidate PickBest(List<AudioCandidate> pool, HashSet<string> preferredSet, bool useFallbackPenalty, IReadOnlyList<TrackSorter> sorters)
    {
        AudioCandidate? best = null;
        List<long>? bestKey = null;
        foreach (var c in pool)
        {
            int? penalty = useFallbackPenalty ? (c.LangLabel.Length > 0 && preferredSet.Contains(c.LangLabel) ? 0 : 1) : null;
            var key = QualitySortKey(c, penalty, sorters);
            if (bestKey is null || SortKeyComparer.Instance.Compare(key, bestKey) < 0)
            {
                best = c;
                bestKey = key;
            }
        }

        return best ?? throw new InvalidOperationException("min() arg is an empty sequence");
    }

    private static string DescribeCandidate(AudioCandidate c)
    {
        var lang = c.LangLabel.Length > 0 ? c.LangLabel : "unknown";
        var channels = c.Channels > 0 ? $"{c.Channels} ch" : "unknown channels";
        return $"{lang} {c.CodecName} {channels} (stream {c.InputIndex})";
    }

    private static AudioCandidate? SelectAudioWinner(RefinerRulesConfig config, List<AudioCandidate> candidates, List<string> notes)
    {
        var policy = NormalizeAudioPreferenceMode(config.AudioPreferenceMode);
        var preferredList = OrderedPreferenceLangs(config);
        var preferredSet = new HashSet<string>(preferredList, StringComparer.Ordinal);
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
            var w = PickBest(candidates, preferredSet, useFallbackPenalty: false, sorters);
            notes.Add($"Selected {DescribeCandidate(w)} using quality across all languages (policy: quality across all languages).");
            return w;
        }

        if (policy == RemuxRuleValues.PolicyPreferredLangsStrict)
        {
            var primary = NormalizeLang(config.PrimaryAudioLang);
            if (primary.Length == 0)
            {
                notes.Add("Strict policy requires a primary language; none configured.");
                return null;
            }

            var pool = candidates.Where(c => c.LangLabel == primary).ToList();
            if (pool.Count == 0)
            {
                notes.Add($"No audio tracks matched primary language '{primary}' (strict policy — no fallback to secondary or other languages).");
                return null;
            }

            var w = PickBest(pool, preferredSet, useFallbackPenalty: false, sorters);
            notes.Add($"Selected {DescribeCandidate(w)} using primary language only (strict policy).");
            return w;
        }

        // preferred_langs_quality: tier walk, then fallback.
        foreach (var tierLang in preferredList)
        {
            var pool = candidates.Where(c => c.LangLabel == tierLang).ToList();
            if (pool.Count == 0)
            {
                continue;
            }

            var w = PickBest(pool, preferredSet, useFallbackPenalty: false, sorters);
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

        var fallback = PickBest(candidates, preferredSet, useFallbackPenalty: true, sorters);
        var tiers = preferredList.Count > 0 ? string.Join(", ", preferredList) : "none";
        notes.Add(
            $"Fell back to {DescribeCandidate(fallback)} because no track matched configured language tiers ({tiers}); ranked by quality with preferred-language matches first.");
        return fallback;
    }

    /// <summary>
    /// A single winning audio track, the subtitle retention policy and metadata stripping. Null
    /// when no audio would remain.
    /// </summary>
    public static RemuxPlan? PlanRemux(
        IReadOnlyList<ProbeStreamInfo> video,
        IReadOnlyList<ProbeStreamInfo> audio,
        IReadOnlyList<ProbeStreamInfo> subtitles,
        RefinerRulesConfig config,
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
        var notes = new List<string>();
        var candidates = new List<AudioCandidate>();

        foreach (var s in audio)
        {
            var commentary = IsCommentaryAudio(s);
            if (config.RemoveCommentary && commentary)
            {
                var lang = NormalizeLang(s.Tag("language"));
                removedAudio.Add($"{(lang.Length > 0 ? lang : "und")} (commentary excluded — remove commentary enabled)");
                notes.Add($"Excluded commentary track (stream {IndexOf(s)}) because remove commentary is enabled.");
                continue;
            }

            candidates.Add(CandidateFromStream(s));
        }

        var policy = NormalizeAudioPreferenceMode(config.AudioPreferenceMode);

        var winner = SelectAudioWinner(config, [.. candidates], notes);
        if (winner is null)
        {
            return null;
        }

        // Retention: one winner; every other audio stream is removed.
        var winnerIndex = winner.InputIndex;
        foreach (var c in candidates.Where(c => c.InputIndex != winnerIndex))
        {
            removedAudio.Add($"{DescribeCandidate(c)}: removed (not selected — {DescribeCandidate(winner)} kept)");
            notes.Add($"Removed non-selected {DescribeCandidate(c)} after selecting {DescribeCandidate(winner)}.");
        }

        if (policy == RemuxRuleValues.PolicyPreferredLangsQuality)
        {
            var preferred = OrderedPreferenceLangs(config);
            if (preferred.Count > 1 && preferred.Contains(winner.LangLabel))
            {
                var winnerTier = preferred.IndexOf(winner.LangLabel);
                foreach (var c in candidates)
                {
                    if (c.InputIndex == winnerIndex)
                    {
                        continue;
                    }

                    if (preferred.Contains(c.LangLabel) && preferred.IndexOf(c.LangLabel) > winnerTier)
                    {
                        notes.Add(
                            $"Ignored {DescribeCandidate(c)} because preferred languages (tiered quality) had candidates in '{winner.LangLabel}' first.");
                    }
                }
            }
        }

        var winnerStream = audio.FirstOrDefault(s => (s.Get("index") is { } i ? Py.Int(i) : -1) == winnerIndex);
        var winnerDisposition = winnerStream?.Disposition ?? new Dictionary<string, long>();
        var codecName = winnerStream is null ? string.Empty : Py.StrOr(winnerStream.Get("codec_name"), string.Empty);

        var kept = new PlannedTrack
        {
            InputIndex = winnerIndex,
            LangLabel = winner.LangLabel,
            Commentary = winner.Commentary,
            Forced = winnerDisposition.GetValueOrDefault("forced") != 0,
            Default = true,
            Channels = winner.Channels,
            Lossless = IsLosslessAudio(codecName),
            Bitrate = winner.Bitrate,
            CodecRank = winner.CodecRank,
            CodecName = codecName,
            Kind = TrackKind.Audio,
        };

        var keptSubtitles = new List<PlannedTrack>();
        var removedSubtitleLabels = new List<string>();
        if (config.SubtitleMode == RemuxRuleValues.SubtitleModeRemoveAll || config.SubtitleLangs.Count == 0)
        {
            foreach (var s in subtitles)
            {
                var lang = NormalizeLang(s.Tag("language"));
                removedSubtitleLabels.Add(lang.Length > 0 ? lang : "und");
            }
        }
        else
        {
            var selected = new HashSet<string>(config.SubtitleLangs, StringComparer.Ordinal);
            foreach (var s in subtitles)
            {
                var index = IndexOf(s);
                var lang = NormalizeLang(s.Tag("language"));
                var disposition = s.Disposition;
                if (lang.Length == 0 || !selected.Contains(lang))
                {
                    removedSubtitleLabels.Add(lang.Length > 0 ? lang : "und");
                    continue;
                }

                keptSubtitles.Add(new PlannedTrack
                {
                    InputIndex = index,
                    LangLabel = lang,
                    Forced = config.PreserveForcedSubs && disposition.GetValueOrDefault("forced") != 0,
                    Default = config.PreserveDefaultSubs && disposition.GetValueOrDefault("default") != 0,
                    Kind = TrackKind.Subtitle,
                });
            }

            // {lang: position}, where a repeated language keeps its last position.
            var rank = new Dictionary<string, int>(StringComparer.Ordinal);
            for (var n = 0; n < config.SubtitleLangs.Count; n++)
            {
                rank[config.SubtitleLangs[n]] = n;
            }

            keptSubtitles = [.. keptSubtitles.OrderBy(t => rank.GetValueOrDefault(t.LangLabel, 99)).ThenBy(t => t.InputIndex)];
        }

        return new RemuxPlan
        {
            VideoIndices = videoIndices,
            Audio = [kept],
            Subtitles = keptSubtitles,
            RemovedAudio = removedAudio,
            RemovedSubtitles = removedSubtitleLabels,
            DefaultAudioOutputIndex = 0,
            AudioSelectionNotes = notes,
            RemovedImages = droppedImages.Select(MetadataStreams.DescribeImageStream).ToList(),
            RemovedAttachments = droppedAttachments.Select(MetadataStreams.DescribeAttachmentStream).ToList(),
            MetadataNotes = MetadataStreams.RemovalNotes(rules, droppedImages, droppedAttachments),
            Metadata = rules,
        };
    }

    /// <summary>Sane defaults for remux planning (<c>default_refiner_remux_rules_config</c>).</summary>
    public static RefinerRulesConfig DefaultConfig() => new()
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
    };
}
