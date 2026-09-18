using System.Text.Json;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>Ported from <c>apps/backend/tests/test_processing_track_sorters.py</c>.</summary>
public sealed class TrackSorterTests
{
    /// <summary>The ranking exactly as it was before the sorter list, copied from the Python test.</summary>
    private static List<long> OriginalQualitySortKey(SortableTrack track, int? fallbackPreferredPenalty = null)
    {
        long com = track.Commentary ? 1 : 0;
        var ch = track.Channels > 0 ? track.Channels : 0;
        long chUnknown = ch <= 0 ? 1 : 0;
        var chScore = ch > 0 ? -Math.Min(ch, 64) : 0;
        var cr = track.CodecRank;
        var br = track.Bitrate > 0 ? track.Bitrate : 0;
        long brUnknown = br <= 0 ? 1 : 0;
        var brScore = br > 0 ? -Math.Min(br, 2_000_000_000) : 0;
        long defaultWeak = track.Default ? 0 : 1;
        long fp = fallbackPreferredPenalty ?? 0;
        return [fp, com, chUnknown, chScore, cr, brUnknown, brScore, defaultWeak, track.Index];
    }

    private static SortableTrack Track(
        int index = 0,
        string language = "eng",
        string title = "",
        bool commentary = false,
        bool isDefault = false,
        long channels = 6,
        long bitrate = 640_000,
        string codec = "eac3",
        long codecRank = 3) => new()
    {
        Index = index,
        Language = language,
        Title = title,
        Commentary = commentary,
        Default = isDefault,
        Forced = false,
        Channels = channels,
        Bitrate = bitrate,
        Codec = codec,
        CodecRank = codecRank,
    };

    private static IReadOnlyList<long> Key(IEnumerable<TrackSorter> sorters, SortableTrack track) => TrackSorters.SortKeyForTrack(sorters, track);

    private static List<SortableTrack> Ranked(IReadOnlyList<TrackSorter> sorters, params SortableTrack[] tracks) =>
        [.. tracks.OrderBy(t => Key(sorters, t), SortKeyComparer.Instance)];

    // --- the equivalence that matters ----------------------------------------------------

    [Fact]
    public void The_seeded_default_ranks_identically_to_the_old_tuple()
    {
        var tracks = new List<SortableTrack>();
        var index = 0;
        foreach (var commentary in new[] { false, true })
        {
            foreach (var channels in new long[] { 0, 2, 6, 8 })
            {
                foreach (var codecRank in new long[] { 1, 3, 5 })
                {
                    foreach (var bitrate in new long[] { 0, 128_000, 640_000 })
                    {
                        foreach (var isDefault in new[] { false, true })
                        {
                            tracks.Add(Track(index++, commentary: commentary, channels: channels, codecRank: codecRank, bitrate: bitrate, isDefault: isDefault));
                        }
                    }
                }
            }
        }

        var byNew = tracks.OrderBy(t => Key(TrackSorters.DefaultAudioSorters, t), SortKeyComparer.Instance).Select(t => t.Index);
        var byOld = tracks.OrderBy(t => OriginalQualitySortKey(t), SortKeyComparer.Instance).Select(t => t.Index);

        Assert.Equal(byOld, byNew);
    }

    [Fact]
    public void The_two_rankings_agree_on_the_single_best_track()
    {
        SortableTrack[] tracks =
        [
            Track(0, channels: 2, codecRank: 5, bitrate: 128_000),
            Track(1, channels: 8, codecRank: 1, bitrate: 1_500_000),
            Track(2, channels: 8, codecRank: 1, bitrate: 1_500_000, commentary: true),
        ];

        var bestNew = tracks.MinBy(t => Key(TrackSorters.DefaultAudioSorters, t), SortKeyComparer.Instance)!;
        var bestOld = tracks.MinBy(t => OriginalQualitySortKey(t), SortKeyComparer.Instance)!;

        Assert.Equal(bestOld.Index, bestNew.Index);
        Assert.Equal(1, bestNew.Index);
    }

    // --- what the list can now express that the tuple could not --------------------------

    [Fact]
    public void An_operator_can_prefer_a_specific_codec()
    {
        var best = Ranked([new("codec", "dts")], Track(0, codec: "truehd"), Track(1, codec: "dts"))[0];

        Assert.Equal("dts", best.Codec);
    }

    [Fact]
    public void An_operator_can_prefer_five_one_over_seven_one()
    {
        var best = Ranked([new("channels", "=5.1")], Track(0, channels: 8), Track(1, channels: 6))[0];

        Assert.Equal(6, best.Channels);
    }

    [Fact]
    public void An_operator_can_demote_a_title_containing_a_word()
    {
        var best = Ranked([new("title", "descriptive", Reversed: true)], Track(0, title: "English Descriptive Audio"), Track(1, title: "English"))[0];

        Assert.Equal("English", best.Title);
    }

    [Fact]
    public void Language_first_then_channels_is_the_flow_the_issue_describes()
    {
        var ranked = Ranked(
            [new("language", "eng"), new("channels", ">=5.1")],
            Track(0, language: "fre", channels: 8),
            Track(1, language: "eng", channels: 2),
            Track(2, language: "eng", channels: 6));

        Assert.Equal([2, 1, 0], ranked.Select(t => t.Index));
    }

    [Fact]
    public void Reversed_flips_a_natural_ordering()
    {
        var best = Ranked([new("bitrate", Reversed: true)], Track(0, bitrate: 1_500_000), Track(1, bitrate: 128_000))[0];

        Assert.Equal(128_000, best.Bitrate);
    }

    [Fact]
    public void An_unknown_value_sorts_after_a_known_one_in_both_directions()
    {
        var known = Track(0, bitrate: 128_000);
        var unknown = Track(1, bitrate: 0);

        Assert.Equal(0, Ranked([new("bitrate")], unknown, known)[0].Index);
        Assert.Equal(0, Ranked([new("bitrate", Reversed: true)], unknown, known)[0].Index);
    }

    [Fact]
    public void Channels_accepts_the_notation_operators_actually_write()
    {
        TrackSorter[] sorters = [new("channels", ">=5.1")];

        Assert.Equal(0, Key(sorters, Track(channels: 6))[0]);
        Assert.Equal(0, Key(sorters, Track(channels: 8))[0]);
        Assert.Equal(1, Key(sorters, Track(channels: 2))[0]);
        Assert.Equal(0, Key([new("channels", "stereo")], Track(channels: 2))[0]);
    }

    [Fact]
    public void The_index_is_always_the_final_tiebreak()
    {
        var ranked = Ranked(TrackSorters.DefaultAudioSorters, Track(3), Track(1));

        Assert.Equal([1, 3], ranked.Select(t => t.Index));
    }

    [Fact]
    public void An_empty_sorter_list_still_produces_a_total_order()
    {
        var ranked = Ranked([], Track(2), Track(0));

        Assert.Equal([0, 2], ranked.Select(t => t.Index));
    }

    // --- storage -------------------------------------------------------------------------

    [Fact]
    public void A_list_round_trips()
    {
        TrackSorter[] original = [new("language", "eng"), new("channels", Reversed: true)];

        Assert.Equal(original, TrackSorters.Parse(TrackSorters.Dump(original)));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("not json")]
    [InlineData("\"a string\"")]
    [InlineData("[]")]
    [InlineData("[1, 2, 3]")]
    public void An_unusable_stored_value_falls_back_to_the_seeded_default(string bad)
    {
        Assert.Equal(TrackSorters.DefaultAudioSorters, TrackSorters.Parse(bad));
    }

    [Fact]
    public void An_unknown_field_in_stored_data_is_skipped_rather_than_crashing()
    {
        var stored = JsonSerializer.Serialize(new[] { new { field = "loudness" }, new { field = "channels" } });

        Assert.Equal([new TrackSorter("channels")], TrackSorters.Parse(stored));
    }

    [Fact]
    public void Saving_an_unknown_field_is_refused_rather_than_silently_dropped()
    {
        var error = Assert.Throws<TrackSorterException>(() => TrackSorters.Validate("""[{"field": "loudness"}]"""));

        Assert.Contains("unknown field", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Saving_something_that_is_not_a_list_is_refused()
    {
        Assert.Contains("must be a list", Assert.Throws<TrackSorterException>(() => TrackSorters.Validate("""{"field": "channels"}""")).Message, StringComparison.Ordinal);
        Assert.Contains("not valid JSON", Assert.Throws<TrackSorterException>(() => TrackSorters.Validate("{{{")).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Saving_nothing_yields_the_seeded_default()
    {
        Assert.Equal(TrackSorters.DefaultAudioSorters, TrackSorters.Parse(TrackSorters.Validate("")));
    }

    [Fact]
    public void Every_documented_field_is_accepted()
    {
        var stored = JsonSerializer.Serialize(TrackSorters.Fields.Select(name => new { field = name }));

        Assert.Equal(TrackSorters.Fields.Count, TrackSorters.Parse(stored).Count);
    }

    // --- presets and notes ---------------------------------------------------------------

    [Fact]
    public void The_existing_policies_become_presets_that_fill_the_list()
    {
        Assert.Equal(TrackSorters.DefaultAudioSorters, TrackSorters.Preset("preferred_langs_quality"));
        Assert.Equal("commentary", TrackSorters.Preset("quality_all_languages")[0].Field);
        Assert.Equal(TrackSorters.DefaultAudioSorters, TrackSorters.Preset("something-else"));
    }

    [Fact]
    public void The_notes_describe_the_configured_list_rather_than_a_fixed_sentence()
    {
        var text = TrackSorters.Describe([new TrackSorter("language", "eng"), new TrackSorter("channels")]);

        Assert.Contains("language eng", text, StringComparison.Ordinal);
        Assert.Contains("channels", text, StringComparison.Ordinal);
        Assert.Contains(", then ", text, StringComparison.Ordinal);
    }

    [Fact]
    public void The_notes_say_so_when_nothing_is_configured()
    {
        Assert.Contains("file order", TrackSorters.Describe([]), StringComparison.Ordinal);
    }

    [Fact]
    public void A_negated_match_is_described_as_a_negation()
    {
        Assert.Equal("not title commentary", TrackSorters.Describe([new TrackSorter("title", "commentary", Reversed: true)]));
    }

    // --- issue #537 item 1: the notes must say the true ranking direction ----------------

    [Fact]
    public void The_default_notes_say_the_true_ranking_direction()
    {
        var text = TrackSorters.Describe(TrackSorters.DefaultAudioSorters);

        // channels and bitrate rank highest first; issue #497 put content tier (main, then
        // dub/audio description, then commentary) in place of the old plain "commentary" key.
        Assert.Contains("channels highest first", text, StringComparison.Ordinal);
        Assert.Contains("bitrate highest first", text, StringComparison.Ordinal);
        Assert.Contains("content tier (main, then dub/audio description, then commentary)", text, StringComparison.Ordinal);
        Assert.DoesNotContain("lowest first", text, StringComparison.Ordinal);
        Assert.DoesNotContain("commentary first", text, StringComparison.Ordinal);
    }

    [Fact]
    public void A_reversed_sorter_is_described_with_the_flipped_direction()
    {
        Assert.Equal("channels lowest first", TrackSorters.Describe([new TrackSorter("channels", Reversed: true)]));
        Assert.Equal("bitrate lowest first", TrackSorters.Describe([new TrackSorter("bitrate", Reversed: true)]));
        // Reversing the demotion puts commentary first instead of last.
        Assert.Equal("commentary first", TrackSorters.Describe([new TrackSorter("commentary", Reversed: true)]));
        Assert.Equal("default last", TrackSorters.Describe([new TrackSorter("default", Reversed: true)]));
    }

    [Fact]
    public void Choosing_a_policy_fills_the_sorter_list_so_it_can_then_be_edited()
    {
        var filled = TrackSorters.Parse(TrackSorters.Dump(TrackSorters.Preset("quality_all_languages")));

        Assert.Equal(["commentary", "channels", "codec", "bitrate"], filled.Select(s => s.Field));
        Assert.Equal(TrackSorters.DefaultAudioSorters, TrackSorters.Preset("preferred_langs_quality"));
    }
}
