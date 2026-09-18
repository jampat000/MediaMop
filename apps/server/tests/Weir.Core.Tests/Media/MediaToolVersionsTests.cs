using Weir.Core.Media;

namespace Weir.Core.Tests.Media;

/// <summary>
/// #548: reducing a <c>--version</c> run to the one line an operator needs. The banners here are the real ones
/// printed by the tools Weir bundles — the Windows package's BtbN ffmpeg build and MKVToolNix's portable
/// Windows build — not invented shapes.
/// </summary>
public sealed class MediaToolVersionsTests
{
    [Fact]
    public void The_first_line_is_the_version_and_ffmpegs_build_configuration_is_dropped()
    {
        // `ffmpeg -hide_banner -version` still prints the configure line and the per-library versions after the
        // first line; only the first line names the build, so only the first line is reported.
        const string Banner = """
            ffmpeg version 8.0-full_build-www.gyan.dev Copyright (c) 2000-2025 the FFmpeg developers
            built with gcc 15.2.0 (Rev3, Built by MSYS2 project)
            configuration: --enable-gpl --enable-version3 --enable-static
            libavutil      60.  8.100 / 60.  8.100
            """;

        Assert.Equal(
            "ffmpeg version 8.0-full_build-www.gyan.dev Copyright (c) 2000-2025 the FFmpeg developers",
            MediaToolVersions.FromBanner(0, Banner));
    }

    [Fact]
    public void Mkvmerges_one_line_banner_is_reported_whole()
    {
        Assert.Equal(
            "mkvmerge v102.0 ('Neon Lights') 64-bit",
            MediaToolVersions.FromBanner(0, "mkvmerge v102.0 ('Neon Lights') 64-bit\n"));
    }

    [Fact]
    public void Carriage_returns_and_leading_blank_lines_do_not_reach_the_report()
    {
        // Windows tools end lines with \r\n, and the runner captures the bytes as they came.
        Assert.Equal("mkvmerge v102.0 64-bit", MediaToolVersions.FromBanner(0, "\r\n\r\nmkvmerge v102.0 64-bit\r\nmore\r\n"));
    }

    [Fact]
    public void A_non_zero_exit_or_no_output_is_unknown_rather_than_a_wrong_version()
    {
        // Whatever a failing run printed is not a version banner, so it is never reported as one.
        Assert.Equal(MediaToolVersions.Unknown, MediaToolVersions.FromBanner(1, "mkvmerge v102.0 64-bit"));
        Assert.Equal(MediaToolVersions.Unknown, MediaToolVersions.FromBanner(0, string.Empty));
        Assert.Equal(MediaToolVersions.Unknown, MediaToolVersions.FromBanner(0, "   \n\t\n"));
    }

    [Fact]
    public void A_tool_that_streams_something_unexpected_cannot_put_an_unbounded_string_in_the_response()
    {
        var wall = new string('x', MediaToolVersions.MaxLength * 3);

        var reported = MediaToolVersions.FromBanner(0, wall);

        Assert.Equal(MediaToolVersions.MaxLength, reported.Length);
    }
}
