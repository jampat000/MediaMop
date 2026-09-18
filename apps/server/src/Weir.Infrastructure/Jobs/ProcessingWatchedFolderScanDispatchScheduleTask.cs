using Microsoft.Extensions.Logging;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Processing;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// Periodic tick for <c>processing.watched_folder.remux_scan_dispatch.v1</c> (port of
/// <c>processing_watched_folder_remux_scan_dispatch_periodic_enqueue.py</c>'s asyncio loop), run as an
/// <see cref="IPeriodicTask"/> on a short fixed poll rather than Python's dynamically computed sleep — the
/// per-library due times are tracked in <see cref="_nextRunByLibrary"/> exactly as Python's
/// <c>next_run_by_library</c> dict, so the *decision* of when a library is due is identical; only the
/// polling mechanism differs (see <see cref="PeriodicSchedule"/> for the shared timing arithmetic).
/// </summary>
/// <remarks>
/// <b>The fix for #533</b> has two independent parts, both honoured here, and both must allow a scope
/// before it is ever scheduled:
/// <list type="bullet">
/// <item>
/// <see cref="WeirOptions.ProcessingWatchedFolderRemuxScanDispatchScheduleEnabled"/>
/// (<c>WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED</c>, default on): a global kill
/// switch for every scope's periodic timer. This is the variable the issue names, and the one a fossil
/// test-helper comment on the Python side already documented as real configuration while nothing in
/// <c>WeirSettings</c> actually parsed it (removed there in #329 for exactly that reason — reporting a
/// switch as live while it does nothing is worse than not having it). This port reintroduces it as a
/// switch that actually works, following the same "env kill switch beside a saved setting" shape already
/// used for the work-temp-stale-sweep and failure-cleanup families in <c>JobServices.cs</c>.
/// </item>
/// <item>
/// The operator settings singleton's per-scope <c>movie_schedule_enabled</c>/<c>tv_schedule_enabled</c>
/// column — the switch an operator sees and toggles on the Settings screen. Python's own scheduler never
/// read this column (only <c>library.enabled</c>), so it was exactly as dead as the removed env var; this
/// port adds the missing check so the screen stops lying about it too.
/// </item>
/// </list>
/// A scope or library excluded either way is skipped identically to one with <c>enabled = false</c>: it is
/// simply never scheduled, exactly as though it did not exist for the periodic timer. Manual scans do not
/// consult any of this — see <see cref="ProcessingWatchedFolderScanDispatchEnqueue.EnqueueScanDispatchJobAsync"/>,
/// which the manual HTTP route calls directly.
/// <para>
/// <c>..._PERIODIC_ENQUEUE_REMUX_JOBS</c> (<see cref="WeirOptions.ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs"/>)
/// remains a third, orthogonal switch: it controls what a periodic scan *does* once it runs (queue files
/// for processing, or only check and record state) — never whether it runs at all. With either
/// schedule-enabled switch off, no periodic scan happens for that scope regardless of this flag; with both
/// schedule switches on and this flag off, scans keep running (and file state keeps getting recorded and
/// shown on the Files screen) without queuing remux work.
/// </para>
/// </remarks>
public sealed class ProcessingWatchedFolderScanDispatchScheduleTask : IPeriodicTask
{
    private readonly SqliteDatabase _database;
    private readonly WeirOptions _options;
    private readonly ProcessingJobStore _jobStore;
    private readonly TimeProvider _time;
    private readonly ILogger<ProcessingWatchedFolderScanDispatchScheduleTask> _logger;
    private readonly Dictionary<long, DateTimeOffset> _nextRunByLibrary = [];

    public ProcessingWatchedFolderScanDispatchScheduleTask(
        SqliteDatabase database, WeirOptions options, ProcessingJobStore jobStore, TimeProvider time, ILogger<ProcessingWatchedFolderScanDispatchScheduleTask> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _jobStore = jobStore ?? throw new ArgumentNullException(nameof(jobStore));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public string Name => "processing-watched-folder-remux-scan-dispatch-enqueue";

    /// <summary>A short, fixed poll. Python computes a dynamic sleep to the nearest due library, capped at
    /// 60s; a 1s poll reaches the same per-library due times (tracked below) with a simpler, more directly
    /// testable mechanism, at the cost of a slightly busier idle loop.</summary>
    public TimeSpan Interval => TimeSpan.FromSeconds(1);

    public bool RunAtStart => true;

    public TimeSpan? FailureCooldown => PeriodicSchedule.FailureCooldown;

    public string FailureMessage => "Watched-folder scheduler failed.";

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        if (!_options.ProcessingWatchedFolderRemuxScanDispatchScheduleEnabled)
        {
            // #533: the global kill switch is off. No scope is scheduled — clear any due times a
            // library earned before the switch was flipped, so turning it back on starts clean rather
            // than immediately firing a catch-up for every library that missed its window meanwhile.
            _nextRunByLibrary.Clear();
            return;
        }

        var now = _time.GetUtcNow();
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        var libraries = (await LibraryStore.ListAsync(uow, enabledOnly: true).ConfigureAwait(false))
            .Where(ScanDispatchScheduleGateEnabled)
            .ToList();
        var operatorSettings = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        // Release any write lock EnsureAsync took creating the singleton row on first run: the enqueue
        // below opens its own connection through ProcessingJobStore, and SQLite allows only one writer.
        await uow.CommitAsync().ConfigureAwait(false);

        var activeIds = libraries.Select(l => l.Id).ToHashSet();
        foreach (var staleId in _nextRunByLibrary.Keys.Where(id => !activeIds.Contains(id)).ToList())
        {
            _nextRunByLibrary.Remove(staleId);
        }

        foreach (var library in libraries)
        {
            var scope = ProcessingMediaScopes.Normalize(library.MediaType);
            if (!ScanDispatchScheduleGate.ScopePeriodicScanEnabled(operatorSettings.MovieScheduleEnabled, operatorSettings.TvScheduleEnabled, scope))
            {
                // #533: this scope's own "run periodic scans" switch is off. Never schedule it — not even
                // a delayed catch-up — exactly as if the library did not exist for this timer.
                _nextRunByLibrary.Remove(library.Id);
                continue;
            }

            var interval = TimeSpan.FromSeconds(PeriodicSchedule.WatchedFolderScanIntervalSeconds(library.ScanIntervalSeconds));
            var due = _nextRunByLibrary.TryGetValue(library.Id, out var existing) ? existing : now;
            if (now < due)
            {
                continue;
            }

            var missed = PeriodicSchedule.MissedDueRunCount(now.ToUnixTimeMilliseconds() / 1000.0, due.ToUnixTimeMilliseconds() / 1000.0, interval.TotalSeconds);
            if (missed > 0)
            {
                _logger.LogWarning(
                    "Watched-folder scheduler missed {Missed} run(s) for library {Library}; enqueueing one catch-up scan",
                    missed, library.Name);
            }

            TimeSpan nextDelay;
            try
            {
                var (inserted, skip) = await ProcessingWatchedFolderScanDispatchEnqueue.TryEnqueuePeriodicAsync(
                    uow, _jobStore, library, _options.ProcessingWatchedFolderRemuxScanDispatchPeriodicEnqueueRemuxJobs).ConfigureAwait(false);
                await uow.CommitAsync().ConfigureAwait(false);
                var activeSkip = !inserted && skip is not null && skip.StartsWith("active_scan_already_queued_", StringComparison.Ordinal);
                nextDelay = activeSkip ? TimeSpan.FromSeconds(Math.Min(interval.TotalSeconds, 5.0)) : interval;
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                _logger.LogError(exception, "Watched-folder scheduler failed for library {Library}", library.Name);
                nextDelay = PeriodicSchedule.FailureCooldown;
            }

            _nextRunByLibrary[library.Id] = now + nextDelay;
        }
    }

    private static bool ScanDispatchScheduleGateEnabled(ProcessingLibraryRecord library) =>
        ScanDispatchScheduleGate.LibraryPeriodicScanEnabled(library.Enabled);
}
