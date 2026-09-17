using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>What a metadata provider knows about one title (<c>provider_port.TitleMetadata</c>).</summary>
public sealed record TitleMetadata
{
    /// <summary>ISO 639-1 as providers report it (<c>fr</c>).</summary>
    public string OriginalLanguage { get; init; } = string.Empty;

    public string Title { get; init; } = string.Empty;
    public int? Year { get; init; }
    public string ProviderId { get; init; } = string.Empty;

    public bool HasOriginalLanguage => PyStrings.Strip(OriginalLanguage).Length > 0;
}

/// <summary>
/// A lookup outcome (<c>provider_port.LookupResult</c>), including the outcomes that are not
/// answers. The provider that produces one does network IO and is ported with the media managers;
/// this is only the value the rules read.
/// </summary>
public sealed record LookupResult
{
    public const string StatusMatched = "matched";
    public const string StatusNoMatch = "no_match";
    public const string StatusNotConfigured = "not_configured";
    public const string StatusUnreachable = "unreachable";

    public required string Status { get; init; }
    public TitleMetadata? Metadata { get; init; }
    public string Detail { get; init; } = string.Empty;

    public bool Matched => Status == StatusMatched && Metadata is not null;
}

/// <summary>The five original-language options, all off by default (<c>OriginalLanguageRules</c>).</summary>
public sealed record OriginalLanguageRules
{
    public bool Enabled { get; init; }

    /// <summary>Extra ISO 639-2 codes kept alongside the original.</summary>
    public IReadOnlyList<string> AdditionalLanguages { get; init; } = [];

    /// <summary>Keep only the first track of each kept language.</summary>
    public bool KeepOnlyFirst { get; init; } = true;

    /// <summary>If nothing matches, decline so the caller's fallback keeps the audio. The safety net.</summary>
    public bool FirstIfNone { get; init; } = true;

    /// <summary>A track with no language tag is treated as the original language.</summary>
    public bool TreatEmptyAsOriginal { get; init; }
}

/// <summary>Which tracks to prefer, and the sentence explaining the choice. No indices means "declined".</summary>
public sealed record OriginalLanguageOutcome
{
    public IReadOnlyList<int> PreferredIndices { get; init; } = [];
    public string Note { get; init; } = string.Empty;

    public bool Chose => PreferredIndices.Count > 0;
}

/// <summary>An audio track as original-language selection sees it.</summary>
public sealed record OriginalLanguageTrack(int Index, string Language);

/// <summary>
/// Original-language audio selection (<c>refiner_original_language.py</c>): the pure mapping and
/// selection. The lookup that feeds it calls a metadata provider over the network and belongs to
/// a later port.
/// </summary>
public static class OriginalLanguage
{
    private static readonly string[][] LanguageGroups =
    [
        ["eng", "en"],
        ["fre", "fr", "fra"],
        ["ger", "de", "deu"],
        ["spa", "es"],
        ["ita", "it"],
        ["jpn", "ja"],
        ["kor", "ko"],
        ["chi", "zh", "zho"],
        ["por", "pt"],
        ["rus", "ru"],
        ["dut", "nl", "nld"],
        ["swe", "sv"],
        ["dan", "da"],
        ["nor", "no"],
        ["fin", "fi"],
        ["pol", "pl"],
        ["cze", "cs", "ces"],
        ["hun", "hu"],
        ["tur", "tr"],
        ["ara", "ar"],
        ["heb", "he"],
        ["hin", "hi"],
        ["tha", "th"],
        ["ukr", "uk"],
        ["gre", "el", "ell"],
        ["rum", "ro", "ron"],
        ["ice", "is", "isl"],
    ];

    /// <summary>Every alias mapped to its group's first (bibliographic) entry.</summary>
    private static readonly Dictionary<string, string> Canonical = BuildCanonical();

    private static Dictionary<string, string> BuildCanonical()
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var group in LanguageGroups)
        {
            foreach (var code in group)
            {
                map[code] = group[0];
            }
        }

        return map;
    }

    /// <summary>One form per language, whichever standard the caller used. Unknown codes are returned as they are.</summary>
    public static string CanonicalLanguage(string? raw)
    {
        var code = RemuxRules.NormalizeLang(PyStrings.Strip(raw ?? string.Empty));
        return Canonical.GetValueOrDefault(code, code);
    }

    public static IReadOnlyList<string> ParseAdditionalLanguages(string? csv)
    {
        var result = new List<string>();
        foreach (var raw in (csv ?? string.Empty).Split(','))
        {
            var code = CanonicalLanguage(raw);
            if (code.Length > 0 && !result.Contains(code))
            {
                result.Add(code);
            }
        }

        return result;
    }

    /// <summary>Order audio tracks by the original language, or decline and say why.</summary>
    public static OriginalLanguageOutcome SelectTracks(OriginalLanguageRules rules, LookupResult lookup, IReadOnlyList<OriginalLanguageTrack> tracks)
    {
        ArgumentNullException.ThrowIfNull(rules);
        ArgumentNullException.ThrowIfNull(lookup);
        ArgumentNullException.ThrowIfNull(tracks);

        if (!rules.Enabled)
        {
            return new OriginalLanguageOutcome();
        }

        if (!lookup.Matched || lookup.Metadata is null)
        {
            var reason = lookup.Detail.Length > 0 ? lookup.Detail : lookup.Status;
            return new OriginalLanguageOutcome
            {
                Note = $"Original-language selection did not apply ({reason}), so the configured language preferences chose the track.",
            };
        }

        var original = CanonicalLanguage(lookup.Metadata.OriginalLanguage);
        if (original.Length == 0)
        {
            return new OriginalLanguageOutcome
            {
                Note = "The metadata provider matched this title but reported no original language, so the configured language preferences chose the track.",
            };
        }

        var wanted = new List<string> { original };
        wanted.AddRange(rules.AdditionalLanguages.Where(code => code != original));

        // Bucket by language in file order.
        var byLanguage = new Dictionary<string, List<OriginalLanguageTrack>>(StringComparer.Ordinal);
        foreach (var track in tracks)
        {
            var code = CanonicalLanguage(track.Language);
            if (code.Length == 0 && rules.TreatEmptyAsOriginal)
            {
                code = original;
            }

            if (!byLanguage.TryGetValue(code, out var bucket))
            {
                bucket = [];
                byLanguage[code] = bucket;
            }

            bucket.Add(track);
        }

        var ordered = new List<int>();
        foreach (var code in wanted)
        {
            var candidates = byLanguage.GetValueOrDefault(code) ?? [];
            var chosen = rules.KeepOnlyFirst ? candidates.Take(1) : candidates;
            ordered.AddRange(chosen.Select(t => t.Index));
        }

        if (ordered.Count > 0)
        {
            var kept = string.Join(", ", wanted);
            var plus = rules.AdditionalLanguages.Count > 0 ? $", plus {string.Join(", ", rules.AdditionalLanguages)}" : string.Empty;
            return new OriginalLanguageOutcome
            {
                PreferredIndices = ordered,
                Note = $"Kept audio in the original language ({original}{plus}) because the metadata provider identified it. Preferred languages: {kept}.",
            };
        }

        if (rules.FirstIfNone && tracks.Count > 0)
        {
            return new OriginalLanguageOutcome
            {
                Note = $"No audio track matched the original language ({original}), so Weir fell back to the configured language preferences to be sure the output still has audio.",
            };
        }

        return new OriginalLanguageOutcome
        {
            Note = $"No audio track matched the original language ({original}), so the configured language preferences chose the track.",
        };
    }
}
