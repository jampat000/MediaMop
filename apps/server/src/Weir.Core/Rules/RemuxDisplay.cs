using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>
/// Human-readable language labels and audio/subtitle lines for the overview and activity
/// (<c>refiner_remux_lang_display.py</c>, <c>refiner_remux_track_display.py</c>).
/// </summary>
public static class RemuxDisplay
{
    /// <summary>ISO 639 code to English label, in the reference's order.</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> StreamLanguageOptions { get; } =
    [
        new("eng", "English"),
        new("jpn", "Japanese"),
        new("spa", "Spanish"),
        new("fre", "French"),
        new("deu", "German"),
        new("ita", "Italian"),
        new("por", "Portuguese"),
        new("rus", "Russian"),
        new("zho", "Chinese"),
        new("kor", "Korean"),
        new("hin", "Hindi"),
        new("ara", "Arabic"),
        new("pol", "Polish"),
        new("tur", "Turkish"),
        new("swe", "Swedish"),
        new("dan", "Danish"),
        new("fin", "Finnish"),
        new("nld", "Dutch"),
        new("nor", "Norwegian"),
        new("hun", "Hungarian"),
        new("ces", "Czech"),
        new("ell", "Greek"),
        new("heb", "Hebrew"),
        new("tha", "Thai"),
        new("vie", "Vietnamese"),
        new("ukr", "Ukrainian"),
        new("ron", "Romanian"),
        new("ind", "Indonesian"),
        new("msa", "Malay"),
        new("und", "Undetermined"),
    ];

    private const string Dash = "—";

    private static string? Label(string code)
    {
        foreach (var (key, label) in StreamLanguageOptions)
        {
            if (key == code)
            {
                return label;
            }
        }

        return null;
    }

    /// <summary><c>refiner_lang_display</c>: a label, the upper-cased code, or an em dash.</summary>
    public static string LangDisplay(string? code)
    {
        var c = RemuxRules.NormalizeLang(code ?? string.Empty);
        return c.Length == 0 ? Dash : Label(c) ?? Py.Upper(c);
    }

    /// <summary><c>refiner_lang_display_or_blank</c>: as <see cref="LangDisplay"/>, but empty for no code.</summary>
    public static string LangDisplayOrBlank(string? code)
    {
        var c = RemuxRules.NormalizeLang(code ?? string.Empty);
        return c.Length == 0 ? string.Empty : Label(c) ?? Py.Upper(c);
    }

    /// <summary>The {channels} placeholder in <see cref="TrackNaming"/>: the same 2.0/5.1/7.1 label as the track lines.</summary>
    public static string ChannelsDisplay(long channels) => ChannelLayoutLabel(channels);

    /// <summary>The {codec} placeholder in <see cref="TrackNaming"/>: the same display label as the track lines.</summary>
    public static string CodecDisplayName(string? codecName) => CodecLabel(codecName ?? string.Empty);

    private static string ChannelLayoutLabel(long n) => n switch
    {
        <= 0 => string.Empty,
        1 => "1.0",
        2 => "2.0",
        6 => "5.1",
        8 => "7.1",
        _ => $"{n} ch",
    };

    private static string CodecLabel(string codecName)
    {
        var c = Py.Lower(PyStrings.Strip(codecName));
        return c switch
        {
            "" => string.Empty,
            "truehd" => "TrueHD",
            "dts_hd" => "DTS-HD MA",
            "eac3" => "E-AC-3",
            "ac3" => "AC-3",
            "aac" => "AAC",
            "flac" => "FLAC",
            "opus" => "Opus",
            "vorbis" => "Vorbis",
            "pcm_s16le" or "pcm_s24le" or "pcm_s32le" => "PCM",
            "mp3" => "MP3",
            _ => Py.Upper(c.Replace("_", " ", StringComparison.Ordinal)),
        };
    }

    private static string JoinParts(params string[] parts)
    {
        var present = parts.Where(p => p.Length > 0).ToList();
        return present.Count > 0 ? string.Join(" ", present) : Dash;
    }

    public static string FormatProbeAudioTrackLine(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var lang = LangDisplayOrBlank(stream.Tag("language"));
        var channels = Py.Truthy(stream.Get("channels")) ? Py.Int(stream.Get("channels")) : 0;
        var codec = CodecLabel(Py.StrOr(stream.Get("codec_name"), string.Empty));
        return JoinParts(lang, ChannelLayoutLabel(channels), codec);
    }

    public static string FormatPlannedAudioTrackLine(PlannedTrack track)
    {
        ArgumentNullException.ThrowIfNull(track);
        return JoinParts(LangDisplayOrBlank(track.LangLabel), ChannelLayoutLabel(track.Channels), CodecLabel(track.CodecName));
    }

    public static string JoinTrackLines(IEnumerable<string?> lines)
    {
        ArgumentNullException.ThrowIfNull(lines);
        var cleaned = lines
            .Where(x => PyStrings.Strip(x ?? string.Empty).Length > 0 && PyStrings.Strip(x!) != Dash)
            .Select(x => PyStrings.Strip(x!))
            .ToList();
        return cleaned.Count > 0 ? string.Join(" · ", cleaned) : Dash;
    }

    public static string AudioBeforeLineFromProbe(IEnumerable<ProbeStreamInfo> audioStreams)
    {
        ArgumentNullException.ThrowIfNull(audioStreams);
        return JoinTrackLines(audioStreams.Select(FormatProbeAudioTrackLine).ToList());
    }

    public static string AudioAfterLineFromPlan(RemuxPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        return JoinTrackLines(plan.Audio.Where(t => t.Kind == TrackKind.Audio).Select(FormatPlannedAudioTrackLine).ToList());
    }

    public static string SubtitleBeforeLineFromProbe(IEnumerable<ProbeStreamInfo> subtitleStreams)
    {
        ArgumentNullException.ThrowIfNull(subtitleStreams);
        var bits = subtitleStreams
            .Select(s => RemuxRules.NormalizeLang(s.Tag("language")))
            .Select(lang => lang.Length > 0 ? LangDisplay(lang) : "Undetermined")
            .ToList();
        return bits.Count > 0 ? string.Join(" · ", bits) : Dash;
    }

    public static string SubtitleAfterLineFromPlan(RemuxPlan plan, bool removeAll)
    {
        ArgumentNullException.ThrowIfNull(plan);
        if (removeAll || plan.Subtitles.Count == 0)
        {
            return "None";
        }

        var langs = plan.Subtitles
            .Where(t => t.Kind == TrackKind.Subtitle)
            .Select(t => LangDisplayOrBlank(t.LangLabel))
            .Where(x => x.Length > 0)
            .ToList();
        return langs.Count > 0 ? string.Join(" · ", langs) : "None";
    }

    /// <summary>What the pass stripped beyond audio and subtitles.</summary>
    public static string MetadataRemovedLineFromPlan(RemuxPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        return JoinTrackLines(plan.MetadataNotes);
    }
}
