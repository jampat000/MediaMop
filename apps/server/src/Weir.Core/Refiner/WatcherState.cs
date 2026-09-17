namespace Weir.Core.Refiner;

/// <summary>How a library's watched folder is being monitored (port of <c>refiner_watcher_state.WatcherStatus</c>).</summary>
public enum WatcherStatus
{
    /// <summary>Filesystem events are arriving. The periodic scan still runs as the backstop.</summary>
    Watching,

    /// <summary>The watcher could not start or has stopped. The periodic scan is the only mechanism
    /// finding work, which still works — it is just slower.</summary>
    PollingFallback,

    /// <summary>Switched off for this library by an operator.</summary>
    Disabled,
}

/// <summary>One library's watcher state and the sentence explaining it (port of <c>WatcherReport</c>).</summary>
public sealed record WatcherReport(long LibraryId, string LibraryName, string WatchedFolder, WatcherStatus Status, string Detail)
{
    /// <summary>
    /// True only for a watcher that was meant to run and is not. A library an operator switched off is
    /// not degraded, and reporting it as such would train people to ignore the signal.
    /// </summary>
    public bool Degraded => Status is WatcherStatus.PollingFallback;
}

/// <summary>
/// In-memory registry of what the filesystem watcher is actually doing, for readiness to report (port of
/// <c>refiner_watcher_state.py</c>). Process-local on purpose: this is the state of *this* process's
/// watchers, so persisting it would make a stale row from a previous run look like the current answer.
/// </summary>
public sealed class WatcherStateStore
{
    private readonly Lock _lock = new();
    private readonly Dictionary<long, WatcherReport> _reports = [];

    public void Record(WatcherReport report)
    {
        ArgumentNullException.ThrowIfNull(report);
        lock (_lock)
        {
            _reports[report.LibraryId] = report;
        }
    }

    public void Forget(long libraryId)
    {
        lock (_lock)
        {
            _reports.Remove(libraryId);
        }
    }

    /// <summary>Drop everything. Called when the watcher stops (or is switched off entirely), and by tests
    /// between cases.</summary>
    public void Clear()
    {
        lock (_lock)
        {
            _reports.Clear();
        }
    }

    public IReadOnlyList<WatcherReport> Reports()
    {
        lock (_lock)
        {
            return [.. _reports.Values.OrderBy(r => r.LibraryId)];
        }
    }

    /// <summary>
    /// <c>(ok, sentence)</c> for readiness. Falling back to polling is *not* a failure — Weir still finds
    /// every file, just on the scan interval rather than within seconds — so this always reports "ok" with
    /// a sentence naming the affected libraries rather than failing readiness over a slower path to the
    /// same result.
    /// </summary>
    public (bool Ok, string Detail) Summary()
    {
        var reports = Reports();
        if (reports.Count == 0)
        {
            return (true, "No libraries are being watched for filesystem events.");
        }

        var degraded = reports.Where(r => r.Degraded).ToList();
        var watching = reports.Count(r => r.Status is WatcherStatus.Watching);
        if (degraded.Count == 0)
        {
            return (true, $"Watching {watching} folder(s) for changes; the periodic scan is the backstop.");
        }

        var names = string.Join(", ", degraded.Select(r => r.LibraryName));
        return (
            true,
            $"Falling back to the periodic scan for {names}. Weir still finds every file, but new ones are " +
            "picked up on the scan interval instead of within seconds.");
    }
}
