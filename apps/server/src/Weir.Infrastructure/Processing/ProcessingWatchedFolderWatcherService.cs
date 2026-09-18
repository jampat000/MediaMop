using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Weir.Core.Configuration;
using Weir.Core.Processing;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing;

/// <summary>
/// Filesystem events as the trigger, the periodic scan as the backstop (port of
/// <c>processing_watched_folder_watcher.py</c>). One <see cref="FileSystemWatcher"/> per enabled library with
/// a saved watched folder and filesystem events switched on, recursive, debounced into exactly the same
/// <c>processing.watched_folder.remux_scan_dispatch.v1</c> job the periodic timer enqueues
/// (<see cref="ProcessingWatchedFolderScanDispatchEnqueue.TryEnqueueForWatcherEventAsync"/>) — this decides
/// nothing about a file itself; extension checks, exclusions, size limits, the hold timer and size
/// settling all stay in the handler that already owns them.
/// </summary>
/// <remarks>
/// Two deliberate divergences from the Python port, both asked for by issue #552:
/// <list type="bullet">
/// <item>
/// <b>Overflow/error → full scan and restart.</b> <see cref="FileSystemWatcher"/> can report a lost-events
/// overflow (or another OS-level error) through its <c>Error</c> event, something Python's watchdog does
/// not surface the same way. On that event this immediately enqueues a scan for the affected library
/// (bypassing the debounce — events may have been lost, so waiting for another one is not safe) and
/// replaces that library's watcher, exactly as though it were only just being scheduled.
/// </item>
/// <item>
/// <b>Reacts to library create/update/delete without a restart.</b> Python's watcher reads the library
/// list once, at process startup, and never revisits it. This re-reads the enabled libraries and their
/// folders every tick (<see cref="TickInterval"/>) and reconciles the watch set to match — a library
/// created, edited (folder, enabled, or "watch for changes" toggled) or deleted takes effect within a
/// tick, with no restart needed. Watchers whose watched folder has not changed are left running, so a tick
/// never interrupts a debounce already in progress for an unrelated library.
/// </item>
/// </list>
/// </remarks>
public class ProcessingWatchedFolderWatcherService : BackgroundService
{
    /// <summary>How often the watch set is reconciled against the database and the debounce/overflow
    /// queues are drained. Small enough to keep the promise of "within seconds" and "picks up library
    /// changes quickly"; large enough not to spin or hammer the database.</summary>
    public static readonly TimeSpan TickInterval = TimeSpan.FromMilliseconds(500);

    private readonly SqliteDatabase _database;
    private readonly WeirOptions _options;
    private readonly ProcessingJobStore _jobStore;
    private readonly WatcherStateStore _state;
    private readonly TimeProvider _time;
    private readonly ILogger<ProcessingWatchedFolderWatcherService> _logger;

    public ProcessingWatchedFolderWatcherService(
        SqliteDatabase database,
        WeirOptions options,
        ProcessingJobStore jobStore,
        WatcherStateStore state,
        TimeProvider time,
        ILogger<ProcessingWatchedFolderWatcherService> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _jobStore = jobStore ?? throw new ArgumentNullException(nameof(jobStore));
        _state = state ?? throw new ArgumentNullException(nameof(state));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.ProcessingWatcherEnabled)
        {
            // One line, once. A per-tick warning about a switch an operator deliberately flipped off is
            // noise that buries the next real problem.
            _logger.LogInformation(
                "The filesystem watcher is switched off (WEIR_PROCESSING_WATCHER_ENABLED=0), so Weir " +
                "finds new files on the scan interval only.");
            _state.Clear();
            return;
        }

        var pending = new WatchedFolderPendingChanges();
        var immediateScans = new ConcurrentQueue<long>();
        var restarts = new ConcurrentQueue<long>();
        var watches = new Dictionary<long, LibraryWatch>();

        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    await ReconcileAsync(watches, pending, immediateScans, restarts, stoppingToken).ConfigureAwait(false);
                }
                catch (Exception exception) when (exception is not OperationCanceledException)
                {
                    _logger.LogError(exception, "Filesystem watcher could not read library settings; keeping the previous watch set.");
                }

                RestartFlagged(watches, pending, immediateScans, restarts);

                var debounce = TimeSpan.FromSeconds(Math.Clamp(_options.ProcessingWatcherDebounceSeconds, 0.25, 300.0));
                var now = _time.GetUtcNow();
                var ready = pending.DrainQuiet(now, debounce);
                var immediate = DrainAll(immediateScans);
                var toScan = ready.Union(immediate).ToList();
                if (toScan.Count > 0)
                {
                    await EnqueueScansAsync(toScan, stoppingToken).ConfigureAwait(false);
                }

                try
                {
                    await Task.Delay(TickInterval, stoppingToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
            }
        }
        finally
        {
            foreach (var watch in watches.Values)
            {
                DisposeWatcher(watch.Watcher);
            }

            _state.Clear();
        }
    }

    private async Task ReconcileAsync(
        Dictionary<long, LibraryWatch> watches,
        WatchedFolderPendingChanges pending,
        ConcurrentQueue<long> immediateScans,
        ConcurrentQueue<long> restarts,
        CancellationToken cancellationToken)
    {
        List<ProcessingLibraryRecord> libraries;
        await using (var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false))
        {
            libraries = await LibraryStore.ListAsync(uow, enabledOnly: true).ConfigureAwait(false);
        }

        var toWatch = libraries.Where(row => HasWatchedFolder(row) && row.FileSystemEventsEnabled).ToDictionary(row => row.Id);
        var disabled = libraries.Where(row => HasWatchedFolder(row) && !row.FileSystemEventsEnabled).ToList();

        // Libraries no longer eligible at all (disabled, or the watched folder was cleared): tear down
        // and stop reporting.
        foreach (var goneId in watches.Keys.Where(id => !toWatch.ContainsKey(id)).ToList())
        {
            DisposeWatcher(watches[goneId].Watcher);
            watches.Remove(goneId);
            pending.Forget(goneId);
            _state.Forget(goneId);
        }

        foreach (var row in disabled)
        {
            _state.Record(new WatcherReport(
                row.Id,
                row.Name,
                row.WatchedFolder,
                WatcherStatus.Disabled,
                $"Filesystem events are switched off for {row.Name}, so Weir finds new files on the scan interval."));
        }

        foreach (var (id, library) in toWatch)
        {
            var folder = library.WatchedFolder.Trim();
            if (watches.TryGetValue(id, out var existing))
            {
                // Keep the library record fresh (output folder, media type, etc. may have changed) without
                // disturbing a running watcher — recreating it on every tick could interrupt a debounce
                // already in progress.
                existing.Library = library;
                if (string.Equals(existing.WatchedFolder, folder, StringComparison.Ordinal))
                {
                    continue;
                }

                // The watched folder itself changed: the old watch no longer points at the right place.
                DisposeWatcher(existing.Watcher);
                watches.Remove(id);
                pending.Forget(id);
            }

            watches[id] = CreateWatch(library, folder, pending, immediateScans, restarts);
        }
    }

    private void RestartFlagged(
        Dictionary<long, LibraryWatch> watches, WatchedFolderPendingChanges pending, ConcurrentQueue<long> immediateScans, ConcurrentQueue<long> restarts)
    {
        foreach (var libraryId in DrainAll(restarts))
        {
            if (!watches.TryGetValue(libraryId, out var watch))
            {
                continue;
            }

            DisposeWatcher(watch.Watcher);
            watches[libraryId] = CreateWatch(watch.Library, watch.WatchedFolder, pending, immediateScans, restarts);
        }
    }

    /// <summary>Test seam (<c>InternalsVisibleTo</c> to Weir.Infrastructure.Tests): lets a test substitute a
    /// <see cref="FileSystemWatcher"/> subclass that can raise a synthetic <c>Error</c> event, since a real
    /// buffer-overflow exception cannot be triggered deterministically from a test.</summary>
    internal virtual FileSystemWatcher CreateFileSystemWatcher(string folder) => new(folder);

    private LibraryWatch CreateWatch(
        ProcessingLibraryRecord library,
        string folder,
        WatchedFolderPendingChanges pending,
        ConcurrentQueue<long> immediateScans,
        ConcurrentQueue<long> restarts)
    {
        try
        {
            if (!Directory.Exists(folder))
            {
                throw new DirectoryNotFoundException($"{folder} is not a folder Weir can see");
            }

            var watcher = CreateFileSystemWatcher(folder);
            watcher.IncludeSubdirectories = true;
            watcher.NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName | NotifyFilters.LastWrite | NotifyFilters.Size;

            try
            {
                // Larger than the 8 KiB default, to make a genuine overflow (the Error handler below) less
                // likely under a burst of writes; still bounded, per FileSystemWatcher's own guidance.
                watcher.InternalBufferSize = 65536;
            }
            catch (ArgumentException)
            {
                // Some platforms refuse an oversized buffer; the default still works, just more eagerly.
            }

            var libraryId = library.Id;
            void OnEvent(object sender, FileSystemEventArgs e)
            {
                // A directory event is always accompanied by the file event that matters, and Deletions
                // are not work appearing — this only subscribes Created/Changed/Renamed, so a delete never
                // reaches here at all.
                if (Directory.Exists(e.FullPath))
                {
                    return;
                }

                pending.Note(libraryId, _time.GetUtcNow());
            }

            watcher.Created += OnEvent;
            watcher.Changed += OnEvent;
            watcher.Renamed += (sender, e) => OnEvent(sender, e);
            watcher.Error += (sender, e) =>
            {
                _logger.LogWarning(
                    e.GetException(),
                    "The filesystem watcher for {Library} reported an error; queuing a full scan and restarting the watcher.",
                    library.Name);
                immediateScans.Enqueue(libraryId);
                restarts.Enqueue(libraryId);
            };

            watcher.EnableRaisingEvents = true;

            var report = new WatcherReport(
                library.Id,
                library.Name,
                folder,
                WatcherStatus.Watching,
                $"Watching {folder} for changes. The periodic scan still runs as a backstop.");
            _state.Record(report);
            return new LibraryWatch(library, folder, watcher);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or System.ComponentModel.Win32Exception)
        {
            var report = new WatcherReport(
                library.Id,
                library.Name,
                folder,
                WatcherStatus.PollingFallback,
                $"Weir could not watch {folder} for changes, so it is finding new files on the scan interval " +
                $"instead. This is normal for network shares and some container mounts. The system reported: {exception.Message}.");
            _state.Record(report);
            return new LibraryWatch(library, folder, null);
        }
    }

    private async Task EnqueueScansAsync(IReadOnlyList<long> libraryIds, CancellationToken cancellationToken)
    {
        try
        {
            await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
            foreach (var libraryId in libraryIds)
            {
                var fresh = await LibraryStore.GetAsync(uow, libraryId).ConfigureAwait(false);
                if (fresh is null || !fresh.Enabled)
                {
                    continue;
                }

                var (inserted, skip) = await ProcessingWatchedFolderScanDispatchEnqueue.TryEnqueueForWatcherEventAsync(
                    uow, _jobStore, fresh, _options.ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs).ConfigureAwait(false);
                if (inserted)
                {
                    _logger.LogInformation("Queued a scan of {Library} because its watched folder changed.", fresh.Name);
                }
                else
                {
                    _logger.LogDebug("Did not queue a watcher scan for {Library}: {Skip}", fresh.Name, skip);
                }
            }

            await uow.CommitAsync().ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            // A failed enqueue must not kill the watcher: the periodic scan is still running, and the next
            // event (or tick, for an overflow) gets another attempt.
            _logger.LogError(exception, "Filesystem watcher could not queue a scan.");
        }
    }

    private static bool HasWatchedFolder(ProcessingLibraryRecord row) => !string.IsNullOrWhiteSpace(row.WatchedFolder);

    private static List<long> DrainAll(ConcurrentQueue<long> queue)
    {
        var seen = new List<long>();
        while (queue.TryDequeue(out var id))
        {
            if (!seen.Contains(id))
            {
                seen.Add(id);
            }
        }

        return seen;
    }

    private static void DisposeWatcher(FileSystemWatcher? watcher)
    {
        if (watcher is null)
        {
            return;
        }

        try
        {
            watcher.EnableRaisingEvents = false;
        }
        catch (ObjectDisposedException)
        {
            return;
        }

        watcher.Dispose();
    }

    private sealed class LibraryWatch(ProcessingLibraryRecord library, string watchedFolder, FileSystemWatcher? watcher)
    {
        public ProcessingLibraryRecord Library { get; set; } = library;

        public string WatchedFolder { get; } = watchedFolder;

        public FileSystemWatcher? Watcher { get; } = watcher;
    }
}
