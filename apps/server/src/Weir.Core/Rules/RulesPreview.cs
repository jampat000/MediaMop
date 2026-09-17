using System.Text.RegularExpressions;
using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>
/// Turns one <see cref="RemuxPlan"/> and the probe it was built from into the per-track rows the
/// "Try on a file" preview (#502) shows: what Refiner would keep or drop, and why. Pure and
/// read-only — it never touches the filesystem or the database, so a caller can run it against
/// unsaved rule edits with no risk of writing anything.
/// </summary>
public static partial class RulesPreview
{
    /// <summary>Video, audio and subtitle streams only: images and attachments are already summarised
    /// in <see cref="RemuxPlan.MetadataNotes"/> and are not shown as their own rows here.</summary>
    private static readonly HashSet<string> RowCodecTypes = new(StringComparer.Ordinal) { "video", "audio", "subtitle" };

    [GeneratedRegex(@"\bstream (\d+)\b")]
    private static partial Regex StreamIndexMention();

    /// <summary>One row of the preview table.</summary>
    public sealed record TrackRow
    {
        public required int Index { get; init; }
        public required string Type { get; init; }
        public string Codec { get; init; } = string.Empty;
        public string Language { get; init; } = string.Empty;
        public string Title { get; init; } = string.Empty;
        public long Channels { get; init; }
        public required bool Kept { get; init; }
        public bool Default { get; init; }
        public bool Forced { get; init; }
        public IReadOnlyList<string> Reasons { get; init; } = [];

        public PyDict ToOut() => new PyDict()
            .Set("index", Index)
            .Set("type", Type)
            .Set("codec", Codec)
            .Set("language", Language)
            .Set("title", Title)
            .Set("channels", Channels)
            .Set("action", Kept ? "keep" : "drop")
            .Set("default", Default)
            .Set("forced", Forced)
            .Set("reasons", new PyList(Reasons.Select(r => (PyJson)new PyStr(r))));
    }

    /// <summary>
    /// One row per video, audio and subtitle stream ffprobe reported, in stream-index order. Each
    /// row's <see cref="TrackRow.Reasons"/> is drawn from <see cref="RemuxPlan.AudioSelectionNotes"/> —
    /// the exact sentences <see cref="RemuxRules.PlanRemux"/> already writes for that stream index —
    /// so the preview reads the same explanation a live pass would log, never a re-derived one.
    /// </summary>
    public static IReadOnlyList<TrackRow> BuildTrackRows(ProbeResult probe, RemuxPlan plan)
    {
        ArgumentNullException.ThrowIfNull(probe);
        ArgumentNullException.ThrowIfNull(plan);

        var keptVideo = new HashSet<int>(plan.VideoIndices);
        var keptAudio = plan.Audio.Count > 0 ? plan.Audio[0] : null;
        var keptSubtitles = plan.Subtitles.ToDictionary(t => t.InputIndex);
        var notesByIndex = NotesByStreamIndex(plan.AudioSelectionNotes);

        var rows = new List<TrackRow>();
        foreach (var stream in probe.Streams)
        {
            if (stream.Index is not { } rawIndex)
            {
                continue;
            }

            var index = (int)rawIndex;
            var type = stream.CodecType;
            if (!RowCodecTypes.Contains(type))
            {
                continue;
            }

            var disposition = stream.Disposition;
            var language = RemuxRules.NormalizeLang(stream.Tag("language"));
            var title = stream.Tag("title") ?? string.Empty;
            var codec = stream.CodecName;
            bool kept;
            bool isDefault;
            bool isForced;
            long channels = 0;

            switch (type)
            {
                case "video":
                    kept = keptVideo.Contains(index);
                    isDefault = disposition.GetValueOrDefault("default") != 0;
                    isForced = disposition.GetValueOrDefault("forced") != 0;
                    break;
                case "audio":
                    channels = Py.TryInt(stream.Get("channels"), out var ch) ? ch : 0;
                    kept = keptAudio?.InputIndex == index;
                    isDefault = kept && keptAudio!.Default;
                    isForced = kept ? keptAudio!.Forced : disposition.GetValueOrDefault("forced") != 0;
                    break;
                default: // subtitle
                    kept = keptSubtitles.TryGetValue(index, out var subTrack);
                    isDefault = kept && subTrack!.Default;
                    isForced = kept ? subTrack!.Forced : disposition.GetValueOrDefault("forced") != 0;
                    break;
            }

            var reasons = notesByIndex.GetValueOrDefault(index) ?? [];
            if (reasons.Count == 0)
            {
                reasons = [DefaultReason(type, kept)];
            }

            rows.Add(new TrackRow
            {
                Index = index,
                Type = type,
                Codec = codec,
                Language = language,
                Title = title,
                Channels = channels,
                Kept = kept,
                Default = isDefault,
                Forced = isForced,
                Reasons = reasons,
            });
        }

        return [.. rows.OrderBy(r => r.Index)];
    }

    private static string DefaultReason(string type, bool kept) => type switch
    {
        "video" => kept ? "Video track kept unchanged." : "Embedded image dropped by the metadata rules.",
        "audio" => kept ? "Selected as the preferred audio track." : "Removed — a different audio track was selected.",
        _ => kept
            ? "Subtitle language matches the configured selection."
            : "Removed — language not in the configured subtitle selection.",
    };

    /// <summary>Groups the plan's diagnostic notes by every stream index a note names ("stream 3").
    /// One note can name more than one index (a comparison between two candidates) and so can appear
    /// under more than one row.</summary>
    private static Dictionary<int, List<string>> NotesByStreamIndex(IReadOnlyList<string> notes)
    {
        var byIndex = new Dictionary<int, List<string>>();
        foreach (var note in notes)
        {
            foreach (Match match in StreamIndexMention().Matches(note))
            {
                if (!int.TryParse(match.Groups[1].Value, out var index))
                {
                    continue;
                }

                if (!byIndex.TryGetValue(index, out var list))
                {
                    list = [];
                    byIndex[index] = list;
                }

                if (!list.Contains(note))
                {
                    list.Add(note);
                }
            }
        }

        return byIndex;
    }

    /// <summary>
    /// A rough size estimate for the tracks the plan drops: each dropped stream's own reported
    /// <c>bit_rate</c> (when ffprobe gave one), multiplied by the file's duration. Always an estimate —
    /// it ignores container overhead and cannot know a real remux's actual muxing efficiency, which is
    /// why the caller must present it as one.
    /// </summary>
    public static long? EstimateDroppedBytes(ProbeResult probe, RemuxPlan plan, double? durationSeconds)
    {
        ArgumentNullException.ThrowIfNull(probe);
        ArgumentNullException.ThrowIfNull(plan);
        if (durationSeconds is not { } duration || duration <= 0)
        {
            return null;
        }

        var keptVideo = new HashSet<int>(plan.VideoIndices);
        var keptAudioIndex = plan.Audio.Count > 0 ? plan.Audio[0].InputIndex : (int?)null;
        var keptSubtitleIndices = new HashSet<int>(plan.Subtitles.Select(t => t.InputIndex));

        double totalBits = 0;
        var any = false;
        foreach (var stream in probe.Streams)
        {
            if (stream.Index is not { } rawIndex)
            {
                continue;
            }

            var index = (int)rawIndex;
            var dropped = stream.CodecType switch
            {
                "video" => !keptVideo.Contains(index),
                "audio" => index != keptAudioIndex,
                "subtitle" => !keptSubtitleIndices.Contains(index),
                _ => false,
            };
            if (!dropped)
            {
                continue;
            }

            var bitrate = ReadBitRate(stream);
            if (bitrate > 0)
            {
                totalBits += bitrate;
                any = true;
            }
        }

        return any ? (long)(totalBits / 8.0 * duration) : null;
    }

    /// <summary>As <c>refiner_remux_rules._read_bit_rate</c>: <c>"N/A"</c> and other unparsable text mean
    /// unknown, not a failure.</summary>
    private static long ReadBitRate(ProbeStreamInfo stream)
    {
        try
        {
            return Py.Truthy(stream.Get("bit_rate")) ? Py.Int(stream.Get("bit_rate")) : 0;
        }
        catch (RulesInputException)
        {
            return 0;
        }
    }
}
