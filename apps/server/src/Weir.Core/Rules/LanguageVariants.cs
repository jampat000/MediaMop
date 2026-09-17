using System.Globalization;
using System.Text;

namespace Weir.Core.Rules;

/// <summary>Where a detected <see cref="VariantDetection"/> came from.</summary>
public enum VariantSource
{
    /// <summary>No variant was detected (or the identifier is just an alias of the base, not detected).</summary>
    None,

    /// <summary>An explicit BCP 47 region or script subtag on the track's own language tag.</summary>
    Tag,

    /// <summary>A marker word or phrase in the track's name (<c>tags.title</c>).</summary>
    Name,
}

/// <summary>
/// One outcome of <see cref="LanguageVariants.Detect"/>: the identifier (if any), where it came
/// from, and the exact marker text for a plan note (e.g. <c>"French (Canada), from the track name
/// 'VFQ'."</c>).
/// </summary>
public sealed record VariantDetection(string? Identifier, VariantSource Source, string? Marker)
{
    public static readonly VariantDetection None = new(null, VariantSource.None, null);

    public bool Found => Identifier is { Length: > 0 };
}

/// <summary>
/// Issue #496: tells regional language variants apart (Quebec vs France French, Latin American vs
/// Castilian Spanish, Brazilian vs European Portuguese, Traditional vs Simplified Chinese,
/// Cantonese vs Mandarin, Flemish) from a track's name or an explicit BCP 47 region/script subtag,
/// ported from Muxarr's <c>Muxarr.Core/Language/LanguageVariants.cs</c> (the owner cleared copying
/// its behaviour; see the issue).
/// </summary>
/// <remarks>
/// <para>
/// <b>Identifier scheme.</b> An identifier is either <c>{base}-{REGION}</c> (an ISO 3166-1
/// alpha-2 country code, e.g. <c>fre-CA</c>, <c>por-BR</c>), <c>{base}-{region}</c> using a UN M49
/// numeric region for a group of countries (<c>spa-419</c>, Latin America and the Caribbean, as
/// CLDR spells <c>es-419</c>), <c>{base}-{Script}</c> using an ISO 15924 script subtag in
/// title case (<c>zho-Hant</c>, <c>zho-Hans</c>), or a bare ISO 639-3 code for a language that is
/// its own code but is offered as a refinement of a macrolanguage tag (<c>yue</c> Cantonese,
/// <c>cmn</c> Mandarin, both refinements of a <c>chi</c>/<c>zho</c> track). <c>base</c> is a fixed,
/// canonical spelling per entry (chosen to match the issue's own examples: the bibliographic form
/// for French, the terminological form for Chinese and Dutch), not necessarily the exact spelling
/// of the input tag — a track tagged <c>fra</c>, <c>fre</c> or <c>fr</c> all refine to <c>fre-CA</c>.
/// </para>
/// <para>
/// <b>Matching a marker.</b> A marker is either a short, ambiguous token (<c>VFQ</c>, <c>CHT</c>,
/// <c>pt-BR</c>) matched as a whole token — case-insensitive, accent-insensitive (diacritics are
/// stripped from both the marker and the title before comparing, so "Québécois" and "Quebecois"
/// are the same token), with <c>.</c> and <c>_</c> treated as word separators like a space — or a
/// marker containing CJK characters (<c>繁體</c>, <c>粵語</c>), matched as a plain substring since
/// CJK text has no spacing between words.
/// </para>
/// <para>
/// <b>Refine-only.</b> Each variant's markers are split into <i>self-identifying</i> (imply both
/// the base language and the variant on their own, e.g. <c>VFQ</c>) and <i>refine-only</i> (only
/// mean anything once the base language is already known, e.g. bare <c>Latino</c>, which could
/// belong to any number of unrelated words). A track's base language classifies as: undetermined
/// (empty or <c>und</c>) — only self-identifying markers apply; the same family as the variant
/// (e.g. base <c>fre</c> for a French variant) — both self-identifying and refine-only markers
/// apply; or conflicting (e.g. base <c>eng</c> for a French variant) — no marker for that variant
/// applies, self-identifying included, since it contradicts a language the track already has. An
/// explicit BCP 47 region/script subtag is read directly and never overridden by a name marker.
/// </para>
/// </remarks>
public static class LanguageVariants
{
    // --- the variant table --------------------------------------------------------------

    private static readonly string[] FrenchFamily = ["fre", "fra", "fr"];
    private static readonly string[] SpanishFamily = ["spa", "es"];
    private static readonly string[] PortugueseFamily = ["por", "pt"];
    private static readonly string[] ChineseFamily = ["chi", "zho", "zh"];
    private static readonly string[] DutchFamily = ["dut", "nld", "nl"];

    private sealed record Marker(string Display, string Normalized)
    {
        public static Marker Of(string display) => new(display, NormalizeForMatch(display));
    }

    private sealed record VariantEntry(
        string Identifier,
        string DisplayName,
        IReadOnlyList<string> Family,
        IReadOnlyList<Marker> SelfIdentifying,
        IReadOnlyList<Marker> RefineOnly);

    private static VariantEntry Entry(string id, string display, string[] family, string[] self, string[] refineOnly) =>
        new(id, display, family, [.. self.Select(Marker.Of)], [.. refineOnly.Select(Marker.Of)]);

    /// <summary>
    /// Regional entries before the plain base-language catch-all, and the more specific entry
    /// before a broader one for the same base language.
    /// </summary>
    private static readonly IReadOnlyList<VariantEntry> Table =
    [
        Entry("fre-CA", "French (Canada)", FrenchFamily,
            self: ["VFQ", "VOQ", "Québécois", "Quebecois", "Canadian French", "French Canadian"],
            refineOnly: ["VQ", "Québec", "Quebec", "Canada", "Canadian"]),
        Entry("fre-FR", "French (France)", FrenchFamily,
            self: ["VFF", "Truefrench", "True French"],
            refineOnly: []),
        Entry("fre-BE", "French (Belgium)", FrenchFamily,
            self: ["VFB"],
            refineOnly: []),
        Entry("spa-ES", "Spanish (Spain)", SpanishFamily,
            self: ["Castellano", "Castilian", "European Spanish"],
            refineOnly: []),
        Entry("spa-419", "Spanish (Latin America)", SpanishFamily,
            self: ["Español Latino", "Espanol Latino", "Latin American", "Latin Spanish", "LATAM"],
            refineOnly: ["Latino"]),
        Entry("por-BR", "Portuguese (Brazil)", PortugueseFamily,
            self: ["Brasileiro", "Brazilian", "pt-BR"],
            refineOnly: []),
        Entry("por-PT", "Portuguese (Portugal)", PortugueseFamily,
            self: ["Português Europeu", "Portugues Europeu", "European Portuguese", "pt-PT"],
            refineOnly: ["Europeu"]),
        Entry("zho-Hant", "Chinese (Traditional)", ChineseFamily,
            self: ["CHT", "BIG5", "繁體", "繁体", "Traditional Chinese"],
            refineOnly: ["Traditional"]),
        Entry("zho-Hans", "Chinese (Simplified)", ChineseFamily,
            self: ["CHS", "简体", "簡體", "Simplified Chinese"],
            refineOnly: ["Simplified"]),
        Entry("yue", "Cantonese", ChineseFamily,
            self: ["Cantonese", "廣東話", "广东话", "粵語", "粤语"],
            refineOnly: ["Yue"]),
        Entry("cmn", "Mandarin", ChineseFamily,
            self: ["Mandarin", "普通話", "普通话", "國語", "国语"],
            refineOnly: []),
        Entry("nld-BE", "Flemish", DutchFamily,
            self: ["Vlaams", "Flemish"],
            refineOnly: []),
    ];

    /// <summary>Every identifier this table can produce, for recognizing one in a configured value.</summary>
    private static readonly HashSet<string> KnownIdentifiers = Table.Select(e => e.Identifier).ToHashSet(StringComparer.Ordinal);

    /// <summary>Human-readable name for a plan note, e.g. <c>"French (Canada)"</c>.</summary>
    public static IReadOnlyDictionary<string, string> DisplayNames { get; } =
        Table.ToDictionary(e => e.Identifier, e => e.DisplayName, StringComparer.Ordinal);

    public static string DisplayName(string identifier) => DisplayNames.GetValueOrDefault(identifier, identifier);

    /// <summary>Whether <paramref name="value"/> is one of the identifiers this table can produce.</summary>
    public static bool IsVariantIdentifier(string? value) => value is not null && KnownIdentifiers.Contains(value);

    // --- BCP 47 -----------------------------------------------------------------------

    private static readonly Dictionary<string, (string CanonicalBase, string[] Family)> Bcp47Primary =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["fr"] = ("fre", FrenchFamily),
            ["fre"] = ("fre", FrenchFamily),
            ["fra"] = ("fre", FrenchFamily),
            ["es"] = ("spa", SpanishFamily),
            ["spa"] = ("spa", SpanishFamily),
            ["pt"] = ("por", PortugueseFamily),
            ["por"] = ("por", PortugueseFamily),
            ["zh"] = ("zho", ChineseFamily),
            ["chi"] = ("zho", ChineseFamily),
            ["zho"] = ("zho", ChineseFamily),
            ["nl"] = ("nld", DutchFamily),
            ["dut"] = ("nld", DutchFamily),
            ["nld"] = ("nld", DutchFamily),
        };

    /// <summary>
    /// Reads a BCP 47 tag directly (<c>fr-CA</c>, <c>pt-BR</c>, <c>zh-Hant</c>), or a bare tag that
    /// is itself one of the table's alias identifiers (<c>yue</c>, <c>cmn</c>). Only a region or
    /// script subtag this table actually knows about is recognized; anything else falls through to
    /// name-based detection.
    /// </summary>
    private static VariantDetection FromBcp47(string? rawTag)
    {
        if (string.IsNullOrWhiteSpace(rawTag))
        {
            return VariantDetection.None;
        }

        var parts = rawTag.Trim().Split('-', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0)
        {
            return VariantDetection.None;
        }

        var primary = parts[0];
        if (string.Equals(primary, "yue", StringComparison.OrdinalIgnoreCase) || string.Equals(primary, "cmn", StringComparison.OrdinalIgnoreCase))
        {
            return new VariantDetection(primary.ToLowerInvariant(), VariantSource.Tag, rawTag);
        }

        if (!Bcp47Primary.TryGetValue(primary, out var mapped))
        {
            return VariantDetection.None;
        }

        for (var i = 1; i < parts.Length; i++)
        {
            var subtag = parts[i];
            string? candidate = null;
            if (subtag.Length == 4 && subtag.All(char.IsLetter))
            {
                candidate = $"{mapped.CanonicalBase}-{char.ToUpperInvariant(subtag[0])}{subtag[1..].ToLowerInvariant()}";
            }
            else if (subtag.Length == 2 && subtag.All(char.IsLetter))
            {
                candidate = $"{mapped.CanonicalBase}-{subtag.ToUpperInvariant()}";
            }
            else if (subtag.Length == 3 && subtag.All(char.IsDigit))
            {
                candidate = $"{mapped.CanonicalBase}-{subtag}";
            }

            if (candidate is not null && KnownIdentifiers.Contains(candidate))
            {
                return new VariantDetection(candidate, VariantSource.Tag, rawTag);
            }
        }

        return VariantDetection.None;
    }

    // --- matching a name ----------------------------------------------------------------

    private static bool IsCjk(char c) => (c >= '⺀' && c <= '鿿') || (c >= '豈' && c <= '﫿');

    private static bool ContainsCjk(string s) => s.Any(IsCjk);

    private static string StripDiacritics(string text)
    {
        var decomposed = text.Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(decomposed.Length);
        foreach (var ch in decomposed)
        {
            if (CharUnicodeInfo.GetUnicodeCategory(ch) != UnicodeCategory.NonSpacingMark)
            {
                sb.Append(ch);
            }
        }

        return sb.ToString().Normalize(NormalizationForm.FormC);
    }

    /// <summary>Lower-case, accent-stripped, with <c>.</c>/<c>_</c> folded to a space like a word separator.</summary>
    private static string NormalizeForMatch(string? text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return string.Empty;
        }

        var lowered = StripDiacritics(text).ToLowerInvariant();
        var sb = new StringBuilder(lowered.Length);
        var lastWasSpace = false;
        foreach (var ch in lowered)
        {
            var c = ch is '_' or '.' ? ' ' : ch;
            if (c == ' ')
            {
                if (lastWasSpace)
                {
                    continue;
                }

                lastWasSpace = true;
            }
            else
            {
                lastWasSpace = false;
            }

            sb.Append(c);
        }

        return sb.ToString();
    }

    private static bool IsWordChar(char c) => char.IsLetterOrDigit(c);

    /// <summary>A whole-token, case-insensitive substring match: neither side of the match may sit against a letter or digit.</summary>
    private static bool ContainsWholeToken(string haystack, string needle)
    {
        if (needle.Length == 0)
        {
            return false;
        }

        var idx = 0;
        while (true)
        {
            idx = haystack.IndexOf(needle, idx, StringComparison.Ordinal);
            if (idx < 0)
            {
                return false;
            }

            var beforeOk = idx == 0 || !IsWordChar(haystack[idx - 1]);
            var endIdx = idx + needle.Length;
            var afterOk = endIdx >= haystack.Length || !IsWordChar(haystack[endIdx]);
            if (beforeOk && afterOk)
            {
                return true;
            }

            idx++;
        }
    }

    /// <summary>CJK text has no spacing between words, so a CJK marker matches as a plain substring.</summary>
    private static bool MatchesMarker(string normalizedTitle, Marker marker) =>
        ContainsCjk(marker.Normalized) ? normalizedTitle.Contains(marker.Normalized, StringComparison.Ordinal) : ContainsWholeToken(normalizedTitle, marker.Normalized);

    private enum BaseRelation
    {
        /// <summary>No base language is known yet (empty, or <c>und</c>).</summary>
        Undetermined,

        /// <summary>The track's base language is this variant's own family.</summary>
        SameFamily,

        /// <summary>The track's base language is a different, established language.</summary>
        Conflicting,
    }

    private static BaseRelation Classify(string normalizedBase, IReadOnlyList<string> family)
    {
        if (normalizedBase.Length == 0 || normalizedBase == "und")
        {
            return BaseRelation.Undetermined;
        }

        return family.Contains(normalizedBase, StringComparer.Ordinal) ? BaseRelation.SameFamily : BaseRelation.Conflicting;
    }

    /// <summary>
    /// Detects a regional/script variant from an explicit BCP 47 tag first (never overridden), then
    /// from the track's name: self-identifying markers for an undetermined or matching base
    /// language, refine-only markers only for a matching base language, and nothing for a
    /// conflicting one. Regional entries are tried before a broader one for the same language.
    /// </summary>
    public static VariantDetection Detect(string? title, string? baseCode, string? bcp47Tag = null)
    {
        var fromTag = FromBcp47(bcp47Tag);
        if (fromTag.Found)
        {
            return fromTag;
        }

        if (string.IsNullOrWhiteSpace(title))
        {
            return VariantDetection.None;
        }

        var normalizedBase = RemuxRules.NormalizeLang(baseCode);
        var normalizedTitle = NormalizeForMatch(title);
        if (normalizedTitle.Length == 0)
        {
            return VariantDetection.None;
        }

        foreach (var entry in Table)
        {
            var relation = Classify(normalizedBase, entry.Family);
            if (relation == BaseRelation.Conflicting)
            {
                continue;
            }

            foreach (var marker in entry.SelfIdentifying)
            {
                if (MatchesMarker(normalizedTitle, marker))
                {
                    return new VariantDetection(entry.Identifier, VariantSource.Name, marker.Display);
                }
            }

            if (relation != BaseRelation.SameFamily)
            {
                continue;
            }

            foreach (var marker in entry.RefineOnly)
            {
                if (MatchesMarker(normalizedTitle, marker))
                {
                    return new VariantDetection(entry.Identifier, VariantSource.Name, marker.Display);
                }
            }
        }

        return VariantDetection.None;
    }

    /// <summary><c>detect_variant(title, base_code, bcp47_tag) -&gt; identifier</c>, the public entry point named by issue #496.</summary>
    public static string? DetectVariant(string? title, string? baseCode, string? bcp47Tag = null) => Detect(title, baseCode, bcp47Tag).Identifier;

    // --- rule matching and config normalization ------------------------------------------

    /// <summary>
    /// A plain base-language rule (<c>"fre"</c>) matches every track of that base language,
    /// variant or not — existing behaviour, unchanged. A variant rule (<c>"fre-CA"</c>) matches
    /// only a track detected as that exact variant.
    /// </summary>
    public static bool Matches(string configuredLangOrVariant, string trackBaseLang, string? trackVariant)
    {
        if (string.IsNullOrEmpty(configuredLangOrVariant))
        {
            return false;
        }

        if (IsVariantIdentifier(configuredLangOrVariant))
        {
            return trackVariant is not null && string.Equals(trackVariant, configuredLangOrVariant, StringComparison.Ordinal);
        }

        return string.Equals(trackBaseLang, configuredLangOrVariant, StringComparison.Ordinal);
    }

    /// <summary>
    /// Normalizes a configured audio-preference or subtitle-language value the same way a track's
    /// own tag is (<see cref="RemuxRules.NormalizeLang"/>), except that a recognized variant
    /// identifier — spelled exactly (<c>"fre-CA"</c>, any case) or as a BCP 47 tag (<c>"fr-CA"</c>)
    /// — is preserved instead of being reduced to its base language.
    /// </summary>
    public static string NormalizeLanguageOrVariant(string? raw)
    {
        if (string.IsNullOrEmpty(raw))
        {
            return string.Empty;
        }

        var trimmed = raw.Trim();
        foreach (var id in KnownIdentifiers)
        {
            if (string.Equals(trimmed, id, StringComparison.OrdinalIgnoreCase))
            {
                return id;
            }
        }

        var viaTag = FromBcp47(trimmed);
        if (viaTag.Found)
        {
            return viaTag.Identifier!;
        }

        return RemuxRules.NormalizeLang(raw);
    }
}
