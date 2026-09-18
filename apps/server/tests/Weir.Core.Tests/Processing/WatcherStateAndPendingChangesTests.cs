using Weir.Core.Processing;

namespace Weir.Core.Tests.Processing;

/// <summary>Pure-logic port of the debounce and readiness-summary assertions in
/// <c>test_processing_watched_folder_watcher.py</c> (<c>PendingChanges</c> and <c>watcher_summary</c>).</summary>
public sealed class WatcherStateAndPendingChangesTests
{
    private static readonly DateTimeOffset T0 = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    // --- debounce -----------------------------------------------------------------------------------

    [Fact]
    public void A_burst_of_writes_to_one_file_produces_one_candidate()
    {
        // A chunked write — a PVR writing a recording in pieces — is one arrival, not twenty.
        var pending = new WatchedFolderPendingChanges();
        for (var tick = 0; tick < 20; tick++)
        {
            pending.Note(1, T0 + TimeSpan.FromSeconds(tick * 0.1));
        }

        // Still inside the debounce window: nothing is ready.
        Assert.Empty(pending.DrainQuiet(T0 + TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(3)));
        Assert.Equal(1, pending.PendingCount);

        // Quiet for long enough, and the whole burst becomes exactly one library id.
        Assert.Equal([1L], pending.DrainQuiet(T0 + TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(3)));
        Assert.Equal(0, pending.PendingCount);
    }

    [Fact]
    public void The_debounce_window_restarts_while_writing_continues()
    {
        var pending = new WatchedFolderPendingChanges();
        pending.Note(1, T0);
        Assert.Equal([1L], pending.DrainQuiet(T0 + TimeSpan.FromSeconds(4), TimeSpan.FromSeconds(3)));

        pending.Note(1, T0 + TimeSpan.FromSeconds(10));
        Assert.Empty(pending.DrainQuiet(T0 + TimeSpan.FromSeconds(11), TimeSpan.FromSeconds(3)));
        Assert.Equal([1L], pending.DrainQuiet(T0 + TimeSpan.FromSeconds(14), TimeSpan.FromSeconds(3)));
    }

    [Fact]
    public void Separate_libraries_debounce_independently()
    {
        var pending = new WatchedFolderPendingChanges();
        pending.Note(1, T0);
        pending.Note(2, T0 + TimeSpan.FromSeconds(10));

        Assert.Equal([1L], pending.DrainQuiet(T0 + TimeSpan.FromSeconds(4), TimeSpan.FromSeconds(3)));
        Assert.Equal([2L], pending.DrainQuiet(T0 + TimeSpan.FromSeconds(14), TimeSpan.FromSeconds(3)));
    }

    [Fact]
    public void Forgetting_a_library_drops_its_pending_event()
    {
        var pending = new WatchedFolderPendingChanges();
        pending.Note(1, T0);
        pending.Forget(1);

        Assert.Empty(pending.DrainQuiet(T0 + TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(3)));
        Assert.Equal(0, pending.PendingCount);
    }

    // --- readiness summary ---------------------------------------------------------------------------

    [Fact]
    public void Readiness_says_nothing_alarming_when_no_library_is_watched()
    {
        var store = new WatcherStateStore();
        var (ok, detail) = store.Summary();

        Assert.True(ok);
        Assert.Contains("No libraries", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Readiness_reports_the_watching_count_when_nothing_is_degraded()
    {
        var store = new WatcherStateStore();
        store.Record(new WatcherReport(1, "Movies", "/movies", WatcherStatus.Watching, "watching"));
        store.Record(new WatcherReport(2, "TV", "/tv", WatcherStatus.Watching, "watching"));

        var (ok, detail) = store.Summary();

        Assert.True(ok);
        Assert.Contains("Watching 2 folder(s)", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void A_library_switched_off_is_not_degraded_and_readiness_still_passes()
    {
        var store = new WatcherStateStore();
        var report = new WatcherReport(1, "Movies", "/movies", WatcherStatus.Disabled, "off");

        Assert.False(report.Degraded);

        store.Record(report);
        var (ok, detail) = store.Summary();

        Assert.True(ok);
        // Nothing is watching and nothing is degraded, so this reads as the "watching 0" sentence, not an
        // alarm about the switched-off library.
        Assert.Contains("Watching 0 folder(s)", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Falling_back_to_polling_is_reported_but_still_passes_readiness()
    {
        var store = new WatcherStateStore();
        store.Record(new WatcherReport(1, "Movies", "/movies", WatcherStatus.PollingFallback, "polling"));

        var report = store.Reports().Single();
        Assert.True(report.Degraded);

        var (ok, detail) = store.Summary();

        // Slower, not broken: readiness still passes and the sentence names the affected library.
        Assert.True(ok);
        Assert.Contains("Falling back to the periodic scan for Movies", detail, StringComparison.Ordinal);
        Assert.Contains("scan interval", detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Forgetting_and_clearing_remove_reports()
    {
        var store = new WatcherStateStore();
        store.Record(new WatcherReport(1, "Movies", "/movies", WatcherStatus.Watching, "watching"));
        store.Record(new WatcherReport(2, "TV", "/tv", WatcherStatus.Watching, "watching"));

        store.Forget(1);
        Assert.Single(store.Reports());

        store.Clear();
        Assert.Empty(store.Reports());
    }
}
