using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Ported from <c>apps/backend/tests/test_processing_media_allowlist.py</c>: the allowlist itself.
/// The tests that check files on disk (<c>is_processing_media_candidate</c>) and the watched-folder
/// scan counters belong to the watched-folder scan port.
/// </summary>
public sealed class MediaExtensionsTests
{
    [Theory]
    [InlineData(".mpe")]
    [InlineData(".mpeg")]
    [InlineData(".mpg")]
    [InlineData(".mov")]
    [InlineData(".flv")]
    [InlineData(".wmv")]
    [InlineData(".avchd")]
    [InlineData(".mkv")]
    [InlineData(".mp4")]
    [InlineData(".m4v")]
    [InlineData(".webm")]
    [InlineData(".avi")]
    public void Supported_container_is_admitted(string suffix) => Assert.Contains(suffix, RemuxRules.MediaExtensionsSorted());

    [Theory]
    [InlineData(".h264")]
    [InlineData(".h265")]
    [InlineData(".mpv")]
    public void Raw_elementary_streams_stay_out(string suffix) => Assert.DoesNotContain(suffix, RemuxRules.MediaExtensionsSorted());

    [Theory]
    [InlineData(".iso")]
    [InlineData(".exe")]
    [InlineData(".rar")]
    [InlineData(".zip")]
    public void Genuinely_unsupported_types_stay_out(string suffix) => Assert.DoesNotContain(suffix, RemuxRules.MediaExtensions);

    [Fact]
    public void The_effective_allowlist_is_reportable()
    {
        var applied = RemuxRules.MediaExtensionsSorted();

        Assert.Equal(applied.Order(StringComparer.Ordinal), applied);
        Assert.All(applied, e => Assert.True(e.StartsWith('.') && string.Equals(e, e.ToLowerInvariant(), StringComparison.Ordinal)));
        Assert.Equal(12, applied.Count);
    }
}
