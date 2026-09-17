using Weir.Core.Library;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Library;

/// <summary>
/// Rules x removed tracks -> affected titles (#509 step 2). See <see cref="RemovedTrackDiff"/>'s remarks for
/// why audio is an approximation (only one audio track is ever kept) and why every comparison here is
/// base-language only (no <c>LanguageVariants</c> concept exists in this codebase).
/// </summary>
public sealed class RemovedTrackDiffTests
{
    private static RemovedTrackRecord Audio(string lang, string reason = "not selected") => new()
    {
        Language = lang,
        Type = RemovedTrackType.Audio,
        Codec = "aac",
        Reason = reason,
    };

    private static RemovedTrackRecord Subtitle(string lang, string reason = "language not kept by subtitle rules") => new()
    {
        Language = lang,
        Type = RemovedTrackType.Subtitle,
        Codec = "subrip",
        Reason = reason,
    };

    [Fact]
    public void A_removed_audio_track_is_wanted_once_its_language_becomes_a_preferred_audio_language()
    {
        var removed = Audio("jpn");
        var rulesBefore = RemuxRules.DefaultConfig() with { PrimaryAudioLang = "eng", SecondaryAudioLang = "", TertiaryAudioLang = "" };
        var rulesAfter = rulesBefore with { SecondaryAudioLang = "jpn" };

        Assert.False(RemovedTrackDiff.WouldNowBeKept(rulesBefore, removed));
        Assert.True(RemovedTrackDiff.WouldNowBeKept(rulesAfter, removed));
    }

    [Fact]
    public void A_removed_subtitle_track_is_wanted_once_its_language_is_added_to_kept_subtitle_languages()
    {
        var removed = Subtitle("spa");
        var rulesBefore = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["eng"] };
        var rulesAfter = rulesBefore with { SubtitleLangs = ["eng", "spa"] };

        Assert.False(RemovedTrackDiff.WouldNowBeKept(rulesBefore, removed));
        Assert.True(RemovedTrackDiff.WouldNowBeKept(rulesAfter, removed));
    }

    [Fact]
    public void Subtitle_mode_remove_all_never_wants_a_removed_subtitle_back_even_if_the_language_is_listed()
    {
        var removed = Subtitle("spa");
        // A language list with subtitle mode still set to remove-all keeps nothing; the diff must not
        // treat the language list alone as meaningful (this is exactly what RemuxRules.PlanRemux itself does).
        var rules = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeRemoveAll, SubtitleLangs = ["spa"] };

        Assert.False(RemovedTrackDiff.WouldNowBeKept(rules, removed));
    }

    [Fact]
    public void Language_comparison_normalizes_case_the_same_way_the_rules_engine_does()
    {
        // RemuxRules.NormalizeLang only lower-cases and takes the primary subtag (e.g. "en-US" -> "en",
        // distinct from "eng") — it does not map ISO-639-1 to ISO-639-2, so this only proves case folding.
        var removed = Subtitle("eng");
        var rules = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["ENG"] };

        Assert.True(RemovedTrackDiff.WouldNowBeKept(rules, removed));
    }

    [Fact]
    public void Tracks_now_wanted_returns_only_the_matching_tracks_in_original_order()
    {
        var removedTracks = new List<RemovedTrackRecord> { Audio("jpn"), Audio("fre"), Subtitle("spa") };
        var rules = RemuxRules.DefaultConfig() with
        {
            PrimaryAudioLang = "eng",
            SecondaryAudioLang = "jpn",
            TertiaryAudioLang = string.Empty,
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["spa"],
        };

        var wanted = RemovedTrackDiff.TracksNowWanted(rules, removedTracks);

        Assert.Equal(2, wanted.Count);
        Assert.Equal("jpn", wanted[0].Language);
        Assert.Equal("spa", wanted[1].Language);
    }

    [Fact]
    public void Affected_files_reports_only_files_with_at_least_one_now_wanted_track()
    {
        var rules = RemuxRules.DefaultConfig() with
        {
            PrimaryAudioLang = "eng",
            SecondaryAudioLang = "jpn",
            TertiaryAudioLang = string.Empty,
        };
        var affectedFile = new RemovedTrackFileKey(1, "Movies/A.mkv");
        var untouchedFile = new RemovedTrackFileKey(1, "Movies/B.mkv");
        var byFile = new Dictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>
        {
            [affectedFile] = [Audio("jpn")],
            [untouchedFile] = [Audio("ger")],
        };

        var results = RemovedTrackDiff.AffectedFiles(rules, byFile);

        var only = Assert.Single(results);
        Assert.Equal(affectedFile, only.File);
        Assert.Single(only.TracksNowWanted);
    }
}
