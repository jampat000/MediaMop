using Weir.Core.Library;
using Weir.Infrastructure.Library;

namespace Weir.Infrastructure.Tests.Library;

/// <summary>
/// <see cref="InMemoryRedownloadTracker"/> (#509 step 4): marking a title "waiting for new download" and
/// the clearing hook a future download pipeline calls once it processes a file for that title.
/// </summary>
public sealed class InMemoryRedownloadTrackerTests
{
    [Fact]
    public async Task Marking_then_clearing_a_title_round_trips()
    {
        var tracker = new InMemoryRedownloadTracker();
        var key = new RemovedTrackFileKey(1, "Movies/A.mkv");

        Assert.False(await tracker.IsWaitingAsync(key));

        await tracker.MarkWaitingAsync(key, "removed Japanese audio; rules now keep it");
        Assert.True(await tracker.IsWaitingAsync(key));
        var waiting = Assert.Single(await tracker.ListWaitingAsync());
        Assert.Equal(key, waiting.File);
        Assert.Contains("Japanese", waiting.Reason, StringComparison.Ordinal);

        // The hook: the download pipeline processed a file for this title.
        var cleared = await tracker.ClearAsync(key);
        Assert.True(cleared);
        Assert.False(await tracker.IsWaitingAsync(key));
        Assert.Empty(await tracker.ListWaitingAsync());
    }

    [Fact]
    public async Task Clearing_a_title_that_was_never_marked_reports_nothing_happened()
    {
        var tracker = new InMemoryRedownloadTracker();
        var cleared = await tracker.ClearAsync(new RemovedTrackFileKey(1, "Movies/Untouched.mkv"));
        Assert.False(cleared);
    }

    [Fact]
    public async Task Marking_the_same_title_twice_replaces_the_earlier_reason()
    {
        var tracker = new InMemoryRedownloadTracker();
        var key = new RemovedTrackFileKey(null, "Movies/A.mkv");

        await tracker.MarkWaitingAsync(key, "first reason");
        await tracker.MarkWaitingAsync(key, "second reason");

        var waiting = Assert.Single(await tracker.ListWaitingAsync());
        Assert.Equal("second reason", waiting.Reason);
    }

    [Fact]
    public void A_file_key_with_no_library_id_prints_the_bare_path()
    {
        Assert.Equal("Movies/A.mkv", new RemovedTrackFileKey(null, "Movies/A.mkv").ToString());
        Assert.Equal("3:Movies/A.mkv", new RemovedTrackFileKey(3, "Movies/A.mkv").ToString());
    }
}
