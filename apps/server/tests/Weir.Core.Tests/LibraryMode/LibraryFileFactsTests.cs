using Weir.Core.LibraryMode;
using Weir.Core.Rules;

namespace Weir.Core.Tests.LibraryMode;

/// <summary>
/// Issue #568: the codec, resolution and language facts the Library view groups by, read from the ffprobe JSON a
/// scan already cached. Nothing here probes anything, and a fact the document does not carry is "unknown".
/// </summary>
public sealed class LibraryFileFactsTests
{
    private const string FilmProbe = """
    {
      "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160},
        {"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "channel_layout": "5.1(side)", "tags": {"language": "eng"}},
        {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "channel_layout": "stereo", "tags": {"language": "ja"}},
        {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
        {"index": 4, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "fr"}}
      ],
      "format": {"duration": "7200.0"}
    }
    """;

    [Fact]
    public void A_probe_gives_the_video_codec_resolution_class_and_track_counts()
    {
        var facts = LibraryFileFactsReader.Derive(FilmProbe);

        Assert.Equal("hevc", facts.VideoCodec);
        Assert.Equal(2160, facts.VideoHeight);
        Assert.Equal("4k", facts.ResolutionClass);
        Assert.Equal(2, facts.AudioTrackCount);
        Assert.Equal(2, facts.SubtitleTrackCount);
    }

    [Fact]
    public void Every_facet_a_file_contributes_is_listed_once_with_canonical_languages()
    {
        var facts = LibraryFileFactsReader.Derive(FilmProbe);

        Assert.Equal(
            [
                (LibraryFacets.VideoCodec, "hevc"),
                (LibraryFacets.Resolution, "4k"),
                (LibraryFacets.AudioCodecChannels, "eac3 5.1"),
                (LibraryFacets.AudioLanguage, "eng"),
                (LibraryFacets.AudioCodecChannels, "aac stereo"),
                // "ja" and "fr" are the two-letter spellings; the breakdown must not show them beside "jpn"/"fre".
                (LibraryFacets.AudioLanguage, "jpn"),
                (LibraryFacets.SubtitleLanguage, "eng"),
                (LibraryFacets.SubtitleLanguage, "fre"),
            ],
            facts.Facets.Select(f => (f.Facet, f.Value)));
    }

    [Fact]
    public void A_file_with_two_tracks_of_the_same_shape_contributes_that_facet_value_once()
    {
        var facts = LibraryFileFactsReader.Derive("""
        {"streams": [
          {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
          {"codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "eng"}},
          {"codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "eng"}}
        ]}
        """);

        Assert.Single(facts.Facets, f => f.Facet == LibraryFacets.AudioCodecChannels && f.Value == "ac3 5.1");
        Assert.Single(facts.Facets, f => f.Facet == LibraryFacets.AudioLanguage && f.Value == "eng");
        Assert.Equal(2, facts.AudioTrackCount);
    }

    [Fact]
    public void An_attached_poster_never_becomes_the_files_video_codec()
    {
        var facts = LibraryFileFactsReader.Derive("""
        {"streams": [
          {"codec_type": "video", "codec_name": "mjpeg", "width": 600, "height": 900, "disposition": {"attached_pic": 1}},
          {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
          {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}
        ]}
        """);

        Assert.Equal("h264", facts.VideoCodec);
        Assert.Equal("1080p", facts.ResolutionClass);
    }

    [Fact]
    public void A_missing_or_unparsable_probe_is_unknown_rather_than_a_guess()
    {
        foreach (var probe in new string?[] { null, "", "   ", "not json", "[]" })
        {
            var facts = LibraryFileFactsReader.Derive(probe);
            Assert.Equal(LibraryFileFacts.Unknown, facts.VideoCodec);
            Assert.Equal(LibraryFileFacts.Unknown, facts.ResolutionClass);
            Assert.Null(facts.VideoHeight);
            Assert.Equal(0, facts.AudioTrackCount);
            Assert.Null(facts.AudioSummary);
        }
    }

    [Fact]
    public void An_untagged_or_undetermined_track_language_reads_unknown()
    {
        var facts = LibraryFileFactsReader.Derive("""
        {"streams": [
          {"codec_type": "video", "codec_name": "h264", "height": 1080},
          {"codec_type": "audio", "codec_name": "dts", "channels": 8},
          {"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "und"}}
        ]}
        """);

        Assert.Contains(new LibraryFileFacet(LibraryFacets.AudioLanguage, LibraryFileFacts.Unknown), facts.Facets);
        Assert.Contains(new LibraryFileFacet(LibraryFacets.SubtitleLanguage, LibraryFileFacts.Unknown), facts.Facets);
        Assert.Equal("unknown dts 7.1", facts.AudioSummary);
    }

    [Theory]
    [InlineData(3840, 2160, "4k")]
    [InlineData(3840, 1600, "4k")]
    [InlineData(1920, 1080, "1080p")]
    [InlineData(1920, 800, "1080p")]
    [InlineData(1280, 720, "720p")]
    [InlineData(720, 576, "sd")]
    [InlineData(0, 0, "unknown")]
    public void Resolution_classes_read_the_way_an_operator_names_them(int width, int height, string expected) =>
        Assert.Equal(expected, LibraryFileFactsReader.ResolutionClassFor(width == 0 ? null : width, height == 0 ? null : height));

    [Theory]
    [InlineData("5.1(side)", 6, "5.1")]
    [InlineData("7.1(wide)", 8, "7.1")]
    [InlineData("", 1, "mono")]
    [InlineData("", 2, "stereo")]
    [InlineData("", 6, "5.1")]
    [InlineData("", 8, "7.1")]
    [InlineData("", 3, "3ch")]
    [InlineData("", 0, "unknown")]
    public void Channel_layouts_drop_ffprobes_qualifier_and_fall_back_to_the_count(string layout, int channels, string expected) =>
        Assert.Equal(expected, LibraryFileFactsReader.ChannelLayoutFor(layout, channels));

    [Fact]
    public void A_track_summary_shows_the_first_three_then_says_how_many_more()
    {
        var facts = LibraryFileFactsReader.Derive("""
        {"streams": [
          {"codec_type": "video", "codec_name": "h264", "height": 1080},
          {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}},
          {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "fre"}},
          {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "spa"}},
          {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "ita"}},
          {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "deu"}}
        ]}
        """);

        Assert.Equal("eng aac stereo, fre aac stereo, spa aac stereo +2 more", facts.AudioSummary);
    }

    [Fact]
    public void Every_problem_kind_has_a_wire_name_that_round_trips_and_something_to_do_about_it()
    {
        foreach (var kind in LibraryProblems.All)
        {
            Assert.Equal(kind, LibraryProblems.Parse(LibraryProblems.Name(kind)));
            Assert.NotEmpty(LibraryProblems.Title(kind));
            Assert.EndsWith(".", LibraryProblems.WhatToDo(kind), StringComparison.Ordinal);
        }

        Assert.Null(LibraryProblems.Parse("something-else"));
        Assert.Null(LibraryProblems.Parse(null));
    }

    [Fact]
    public void Only_the_five_named_facets_are_accepted_as_filters()
    {
        Assert.All(LibraryFacets.All, facet => Assert.True(LibraryFacets.IsKnown(facet)));
        Assert.False(LibraryFacets.IsKnown("path"));
        Assert.False(LibraryFacets.IsKnown(null));
    }

    [Fact]
    public void A_probe_result_and_its_raw_text_derive_the_same_facts()
    {
        var fromDocument = LibraryFileFactsReader.Derive(ProbeResult.Parse(FilmProbe));
        var fromText = LibraryFileFactsReader.Derive(FilmProbe);

        // The facet list is a reference member, so the records' own equality would compare it by identity.
        Assert.Equal(fromDocument with { Facets = [] }, fromText with { Facets = [] });
        Assert.Equal(fromDocument.Facets, fromText.Facets);
    }
}
