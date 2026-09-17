using Weir.Core.LibraryMode;

namespace Weir.Core.Tests.LibraryMode;

public sealed class HardlinkPolicyTests
{
    [Fact]
    public void A_shared_file_is_skipped_by_default()
    {
        var decision = HardlinkPolicy.Evaluate(linkCount: 2, cleanHardlinkedFiles: false);

        Assert.True(decision.Skip);
        Assert.Equal("still shared with a download (seeding)", decision.Reason);
    }

    [Fact]
    public void A_shared_file_is_allowed_when_clean_hardlinked_files_is_on()
    {
        var decision = HardlinkPolicy.Evaluate(linkCount: 2, cleanHardlinkedFiles: true);

        Assert.False(decision.Skip);
        Assert.Null(decision.Reason);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(0)]
    [InlineData(null)]
    public void A_file_with_no_evidence_of_sharing_is_never_skipped_for_that_reason(int? linkCount)
    {
        Assert.Equal(HardlinkDecision.Allow, HardlinkPolicy.Evaluate(linkCount, cleanHardlinkedFiles: false));
        Assert.Equal(HardlinkDecision.Allow, HardlinkPolicy.Evaluate(linkCount, cleanHardlinkedFiles: true));
    }

    [Fact]
    public void A_link_count_of_null_is_not_evidence_of_sharing_even_though_it_is_unknown()
    {
        // An unreadable/unsupported platform reports null; Weir should not block a clean it cannot justify.
        Assert.False(HardlinkPolicy.Evaluate(null, cleanHardlinkedFiles: false).Skip);
    }
}
