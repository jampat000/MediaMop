namespace Weir.Core.Processing;

/// <summary>
/// Thread-safe handoff from a filesystem watcher's own callback thread(s) to the loop that drains it (port
/// of <c>processing_watched_folder_watcher.PendingChanges</c>). A copy lands as a burst of write events, and
/// one candidate per burst — once the tree has been quiet for the debounce window — is the point.
/// </summary>
public sealed class WatchedFolderPendingChanges
{
    private readonly Lock _lock = new();
    private readonly Dictionary<long, DateTimeOffset> _libraries = [];

    public void Note(long libraryId, DateTimeOffset at)
    {
        lock (_lock)
        {
            _libraries[libraryId] = at;
        }
    }

    /// <summary>Library ids whose last event is older than the debounce window, removed from the pending set.</summary>
    public IReadOnlyList<long> DrainQuiet(DateTimeOffset now, TimeSpan debounce)
    {
        lock (_lock)
        {
            var ready = _libraries.Where(pair => now - pair.Value >= debounce).Select(pair => pair.Key).ToList();
            foreach (var libraryId in ready)
            {
                _libraries.Remove(libraryId);
            }

            ready.Sort();
            return ready;
        }
    }

    /// <summary>Drop a library's pending event, if any — it is no longer watched.</summary>
    public void Forget(long libraryId)
    {
        lock (_lock)
        {
            _libraries.Remove(libraryId);
        }
    }

    public int PendingCount
    {
        get
        {
            lock (_lock)
            {
                return _libraries.Count;
            }
        }
    }
}
