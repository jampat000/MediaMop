using Weir.Infrastructure.Processing;

namespace Weir.Infrastructure.Tests.Processing;

/// <summary>The sentence a bulk "try again" reports, counted in English in the singular and the plural.</summary>
public sealed class RequeueStoreTests
{
    [Theory]
    [InlineData(1, 0, "Queued 1 file again. It starts as capacity frees up.")]
    [InlineData(3, 0, "Queued 3 files again. They start as capacity frees up.")]
    [InlineData(1, 1, "Queued 1 file again. 1 could not be queued because its library is gone.")]
    [InlineData(2, 2, "Queued 2 files again. 2 could not be queued because their library is gone.")]
    [InlineData(0, 1, "Nothing was queued: 1 file belongs to a library that no longer exists.")]
    [InlineData(0, 2, "Nothing was queued: 2 files belong to a library that no longer exists.")]
    [InlineData(0, 0, "Nothing matched, so nothing was queued.")]
    public void A_bulk_requeue_reports_its_counts_in_english(int requeued, int skipped, string expected) =>
        Assert.Equal(expected, RequeueStore.BulkDetail(requeued, skipped));
}
