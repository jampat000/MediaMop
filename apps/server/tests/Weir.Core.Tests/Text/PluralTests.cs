using Weir.Core.Text;

namespace Weir.Core.Tests.Text;

public sealed class PluralTests
{
    [Theory]
    [InlineData(0, "0 files")]
    [InlineData(1, "1 file")]
    [InlineData(2, "2 files")]
    [InlineData(1000, "1000 files")]
    public void A_count_reads_as_english(long count, string expected) =>
        Assert.Equal(expected, Plural.Of(count, "file"));

    [Fact]
    public void An_irregular_plural_is_used_when_given()
    {
        Assert.Equal("1 library", Plural.Of(1, "library", "libraries"));
        Assert.Equal("3 libraries", Plural.Of(3, "library", "libraries"));
    }

    [Fact]
    public void The_noun_alone_agrees_with_the_count()
    {
        Assert.Equal("was", Plural.Noun(1, "was", "were"));
        Assert.Equal("were", Plural.Noun(2, "was", "were"));
        Assert.Equal("characters", Plural.Noun(0, "character"));
    }
}
