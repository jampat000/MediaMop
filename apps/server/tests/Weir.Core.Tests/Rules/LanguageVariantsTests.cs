using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Issue #496: regional/script language variants (Quebec vs France French, Latin American vs
/// Castilian Spanish, Brazilian vs European Portuguese, Traditional vs Simplified Chinese,
/// Cantonese vs Mandarin, Flemish), detected from a track's name or an explicit BCP 47 tag,
/// refine-only, and wired into audio/subtitle rule matching without changing a plain-language
/// rule's existing behaviour.
/// </summary>
public sealed class LanguageVariantsTests
{
    // --- the detection table, from the issue -----------------------------------------------

    [Theory]
    // French: regional entries checked before a plainer one for the same language.
    [InlineData("fre", "VFQ", "fre-CA")]
    [InlineData("fre", "VOQ", "fre-CA")]
    [InlineData("fre", "Québécois", "fre-CA")] // accent-insensitive
    [InlineData("fre", "Quebecois", "fre-CA")]
    [InlineData("fre", "Canadian French", "fre-CA")]
    [InlineData("fre", "French Canadian", "fre-CA")]
    [InlineData("fre", "VFF", "fre-FR")]
    [InlineData("fre", "Truefrench", "fre-FR")]
    [InlineData("fre", "True French", "fre-FR")]
    [InlineData("fre", "VFB", "fre-BE")]
    // Spanish.
    [InlineData("spa", "Castellano", "spa-ES")]
    [InlineData("spa", "Castilian", "spa-ES")]
    [InlineData("spa", "European Spanish", "spa-ES")]
    [InlineData("spa", "Español Latino", "spa-419")]
    [InlineData("spa", "LATAM", "spa-419")]
    // Portuguese.
    [InlineData("por", "Brasileiro", "por-BR")]
    [InlineData("por", "Brazilian", "por-BR")]
    [InlineData("por", "pt-BR", "por-BR")] // a literal marker in the name, not the BCP 47 tag path
    [InlineData("por", "Português Europeu", "por-PT")]
    [InlineData("por", "European Portuguese", "por-PT")]
    // Chinese script and Cantonese/Mandarin.
    [InlineData("chi", "CHT", "zho-Hant")]
    [InlineData("chi", "BIG5", "zho-Hant")]
    [InlineData("chi", "繁體", "zho-Hant")]
    [InlineData("chi", "繁体", "zho-Hant")]
    [InlineData("chi", "Traditional Chinese", "zho-Hant")]
    [InlineData("chi", "CHS", "zho-Hans")]
    [InlineData("chi", "简体", "zho-Hans")]
    [InlineData("chi", "簡體", "zho-Hans")]
    [InlineData("chi", "Simplified Chinese", "zho-Hans")]
    [InlineData("chi", "Cantonese", "yue")]
    [InlineData("chi", "廣東話", "yue")]
    [InlineData("chi", "广东话", "yue")]
    [InlineData("chi", "粵語", "yue")]
    [InlineData("chi", "粤语", "yue")]
    [InlineData("chi", "Mandarin", "cmn")]
    [InlineData("chi", "普通話", "cmn")]
    [InlineData("chi", "國語", "cmn")]
    // Flemish.
    [InlineData("dut", "Vlaams", "nld-BE")]
    [InlineData("dut", "Flemish", "nld-BE")]
    public void Self_identifying_markers_are_detected(string baseCode, string title, string expected)
    {
        Assert.Equal(expected, LanguageVariants.DetectVariant(title, baseCode));
    }

    // --- refine-only: only ever refines an already-known, matching base language ------------

    [Fact]
    public void A_spanish_track_named_Latino_refines_to_latin_american_spanish()
    {
        Assert.Equal("spa-419", LanguageVariants.DetectVariant("Latino", "spa"));
    }

    [Fact]
    public void An_english_track_named_Latino_gets_no_variant()
    {
        // "Latino" alone means nothing outside a Spanish track; a conflicting base language is
        // never overridden, self-identifying or not.
        Assert.Null(LanguageVariants.DetectVariant("Latino", "eng"));
    }

    [Theory]
    [InlineData("fre", "Canada", "fre-CA")]
    [InlineData("fre", "Quebec", "fre-CA")]
    [InlineData("fre", "Canadian", "fre-CA")]
    [InlineData("por", "Europeu", "por-PT")]
    [InlineData("chi", "Traditional", "zho-Hant")]
    [InlineData("chi", "Simplified", "zho-Hans")]
    [InlineData("chi", "Yue", "yue")]
    public void Refine_only_markers_apply_only_with_the_matching_base_language(string baseCode, string title, string expected)
    {
        Assert.Equal(expected, LanguageVariants.DetectVariant(title, baseCode));
    }

    [Theory]
    [InlineData("eng", "Canada")]
    [InlineData("eng", "Europeu")]
    [InlineData("eng", "Traditional")]
    [InlineData("jpn", "Yue")]
    public void Refine_only_markers_are_ignored_for_a_conflicting_base_language(string baseCode, string title)
    {
        Assert.Null(LanguageVariants.DetectVariant(title, baseCode));
    }

    [Fact]
    public void An_undetermined_track_accepts_a_self_identifying_marker()
    {
        Assert.Equal("fre-CA", LanguageVariants.DetectVariant("VFQ", baseCode: null));
        Assert.Equal("fre-CA", LanguageVariants.DetectVariant("VFQ", baseCode: ""));
        Assert.Equal("fre-CA", LanguageVariants.DetectVariant("VFQ", baseCode: "und"));
    }

    [Fact]
    public void An_undetermined_track_does_not_accept_a_refine_only_marker()
    {
        // "Canada" only means something once French is already established.
        Assert.Null(LanguageVariants.DetectVariant("Canada", baseCode: null));
    }

    [Fact]
    public void A_conflicting_self_identifying_marker_is_also_ignored()
    {
        // A strongly regional marker still never overrides an already different, established language.
        Assert.Null(LanguageVariants.DetectVariant("VFQ", "eng"));
    }

    [Fact]
    public void Plain_language_markers_that_do_not_identify_a_region_produce_no_variant()
    {
        Assert.Null(LanguageVariants.DetectVariant("VF", "fre"));
        Assert.Null(LanguageVariants.DetectVariant("VOF", "fre"));
        Assert.Null(LanguageVariants.DetectVariant("English", "eng"));
        Assert.Null(LanguageVariants.DetectVariant(null, "fre"));
    }

    // --- BCP 47 tags: read directly, and an explicit regional tag is never overridden -------

    [Theory]
    [InlineData("fr-CA", "fre-CA")]
    [InlineData("fr-FR", "fre-FR")]
    [InlineData("fr-BE", "fre-BE")]
    [InlineData("es-419", "spa-419")]
    [InlineData("es-ES", "spa-ES")]
    [InlineData("pt-BR", "por-BR")]
    [InlineData("pt-PT", "por-PT")]
    [InlineData("zh-Hant", "zho-Hant")]
    [InlineData("zh-Hans", "zho-Hans")]
    [InlineData("nl-BE", "nld-BE")]
    [InlineData("yue", "yue")]
    [InlineData("cmn", "cmn")]
    public void A_bcp47_tag_is_read_directly(string tag, string expected)
    {
        Assert.Equal(expected, LanguageVariants.DetectVariant(title: null, baseCode: null, bcp47Tag: tag));
    }

    [Fact]
    public void An_explicit_regional_tag_is_never_overridden_by_the_track_name()
    {
        // The name says "VFF" (France), but the file's own BCP 47 tag already says Quebec.
        Assert.Equal("fre-CA", LanguageVariants.DetectVariant("VFF", "fre", "fr-CA"));
    }

    [Fact]
    public void An_unrecognized_bcp47_region_falls_through_to_the_name()
    {
        Assert.Equal("fre-CA", LanguageVariants.DetectVariant("VFQ", "fre", "fr-XX"));
    }

    // --- matching a configured rule against a track ------------------------------------------

    [Fact]
    public void A_plain_base_rule_matches_every_variant()
    {
        Assert.True(LanguageVariants.Matches("fre", "fre", "fre-CA"));
        Assert.True(LanguageVariants.Matches("fre", "fre", "fre-FR"));
        Assert.True(LanguageVariants.Matches("fre", "fre", null));
    }

    [Fact]
    public void A_variant_rule_matches_only_that_exact_variant()
    {
        Assert.True(LanguageVariants.Matches("fre-CA", "fre", "fre-CA"));
        Assert.False(LanguageVariants.Matches("fre-CA", "fre", "fre-FR"));
        Assert.False(LanguageVariants.Matches("fre-CA", "fre", null));
    }

    // --- normalizing a configured value: preserves a recognized variant identifier ----------

    [Theory]
    [InlineData("fre-CA", "fre-CA")]
    [InlineData("FRE-ca", "fre-CA")]
    [InlineData("fr-CA", "fre-CA")]
    [InlineData("pt-BR", "por-BR")]
    [InlineData("eng", "eng")]
    [InlineData("ENG", "eng")]
    [InlineData("en-US", "en")] // no recognized identifier for English; falls back like NormalizeLang
    public void Configured_values_are_normalized_preserving_a_recognized_variant(string raw, string expected)
    {
        Assert.Equal(expected, LanguageVariants.NormalizeLanguageOrVariant(raw));
    }

    [Fact]
    public void Display_names_read_like_the_issues_own_examples()
    {
        Assert.Equal("French (Canada)", LanguageVariants.DisplayName("fre-CA"));
        Assert.Equal("Spanish (Latin America)", LanguageVariants.DisplayName("spa-419"));
        Assert.Equal("Portuguese (Brazil)", LanguageVariants.DisplayName("por-BR"));
        Assert.Equal("Chinese (Traditional)", LanguageVariants.DisplayName("zho-Hant"));
        Assert.Equal("Cantonese", LanguageVariants.DisplayName("yue"));
        Assert.Equal("Flemish", LanguageVariants.DisplayName("nld-BE"));
    }

    // --- wired into planning: a variant rule keeps only its own variant ---------------------

    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static readonly ProbeStreamInfo Video = Stream("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");

    private static ProbeStreamInfo FrenchAudio(int index, string title) => Stream(
        $"{{\"index\": {index}, \"codec_type\": \"audio\", \"codec_name\": \"aac\", \"channels\": 2, \"bit_rate\": \"128000\", \"tags\": {{\"language\": \"fre\", \"title\": {System.Text.Json.JsonSerializer.Serialize(title)}}}}}");

    [Fact]
    public void A_variant_rule_keeps_only_the_track_detected_as_that_variant()
    {
        var vfq = FrenchAudio(1, "VFQ");
        var vff = FrenchAudio(2, "VFF");
        var config = RemuxRules.DefaultConfig() with { PrimaryAudioLang = "fre-CA", SecondaryAudioLang = "", RemoveCommentary = false };

        var plan = RemuxRules.PlanRemux([Video], [vfq, vff], [], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Audio);
        Assert.Equal(1, plan.Audio[0].InputIndex);
        Assert.Equal("fre-CA", plan.Audio[0].Variant);
        Assert.Contains(plan.AudioSelectionNotes, n => n.Contains("as the only track in the first matching language tier", StringComparison.Ordinal));
        // The plan explains the detection the way the issue itself phrases it.
        Assert.Contains("French (Canada), from the track name 'VFQ'.", plan.AudioSelectionNotes);
    }

    [Fact]
    public void A_plain_base_rule_still_considers_every_variant_as_one_tier()
    {
        var vfq = FrenchAudio(1, "VFQ");
        var vff = FrenchAudio(2, "VFF");
        var config = RemuxRules.DefaultConfig() with { PrimaryAudioLang = "fre", SecondaryAudioLang = "", RemoveCommentary = false };

        var plan = RemuxRules.PlanRemux([Video], [vfq, vff], [], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Audio);
        // Both VFQ and VFF are French, so the plain "fre" tier holds both — the pre-#496 behaviour
        // for a base-language rule (which of the two wins is an unrelated quality tie-break).
        Assert.Contains(plan.AudioSelectionNotes, n => n.Contains("within the same language tier", StringComparison.Ordinal) && n.Contains("(stream 1)", StringComparison.Ordinal) && n.Contains("(stream 2)", StringComparison.Ordinal));
    }

    [Fact]
    public void Subtitle_language_lists_accept_a_variant_identifier()
    {
        var english = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "eng"}}""");
        var vfq = Stream("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "fre", "title": "VFQ"}}""");
        var vff = Stream("""{"index": 3, "codec_type": "subtitle", "tags": {"language": "fre", "title": "VFF"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["fre-CA"] };

        var plan = RemuxRules.PlanRemux([Video], [english], [vfq, vff], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Subtitles);
        Assert.Equal(2, plan.Subtitles[0].InputIndex);
        Assert.Equal("fre-CA", plan.Subtitles[0].Variant);
    }

    [Fact]
    public void Subtitle_language_lists_with_a_plain_base_code_still_keep_every_variant()
    {
        var english = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "eng"}}""");
        var vfq = Stream("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "fre", "title": "VFQ"}}""");
        var vff = Stream("""{"index": 3, "codec_type": "subtitle", "tags": {"language": "fre", "title": "VFF"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["fre"] };

        var plan = RemuxRules.PlanRemux([Video], [english], [vfq, vff], config);

        Assert.NotNull(plan);
        Assert.Equal(2, plan!.Subtitles.Count);
    }
}
