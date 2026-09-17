using System.Globalization;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Workers;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>Worker loop timings (Python's module constants), adjustable for tests.</summary>
public sealed record WorkerLoopTimings
{
    /// <summary><c>REFINER_WORKER_IDLE_SLEEP_SECONDS</c>.</summary>
    public TimeSpan IdleSleep { get; init; } = TimeSpan.FromSeconds(5);

    /// <summary><c>REFINER_WORKER_TICK_ERROR_BACKOFF_SECONDS</c>.</summary>
    public TimeSpan TickErrorBackoff { get; init; } = TimeSpan.FromSeconds(1);

    /// <summary><c>_CONCURRENT_FILES_CACHE_TTL</c>: how long a slot trusts the saved files-at-once value.</summary>
    public TimeSpan ConcurrencyCacheTtl { get; init; } = TimeSpan.FromSeconds(30);

    /// <summary><c>DEFAULT_REFINER_JOB_LEASE_SECONDS</c>.</summary>
    public int LeaseSeconds { get; init; } = RefinerJobProcessor.DefaultLeaseSeconds;
}

/// <summary>
/// Startup crash recovery, run before any worker starts (the synchronous part of Python's lifespan).
/// A failure stops startup, as in Python.
/// </summary>
public sealed class JobsStartupRecoveryService : IHostedService
{
    private readonly RefinerJobStore _store;
    private readonly WeirOptions _options;
    private readonly TimeProvider _time;
    private readonly ILogger<JobsStartupRecoveryService> _logger;

    public JobsStartupRecoveryService(RefinerJobStore store, WeirOptions options, TimeProvider time, ILogger<JobsStartupRecoveryService> logger)
    {
        _store = store;
        _options = options;
        _time = time;
        _logger = logger;
    }

    public StartupRecoveryReport? LastReport { get; private set; }

    public async Task StartAsync(CancellationToken cancellationToken) =>
        LastReport = await StartupRecovery.RunAsync(_store, _options.WeirHome, _time.GetUtcNow(), _logger, cancellationToken).ConfigureAwait(false);

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}

/// <summary>
/// The Refiner worker lane (port of <c>refiner_worker_run_forever</c> and
/// <c>start_refiner_worker_background_tasks</c>): <c>WEIR_REFINER_WORKER_COUNT</c> slots, of which the
/// saved "Files at once" value decides how many take work. Each slot reports heartbeats for readiness.
/// </summary>
public sealed class RefinerWorkerService : BackgroundService
{
    public const string HeartbeatModule = "refiner";

    private readonly RefinerJobProcessor _processor;
    private readonly RefinerJobStore _store;
    private readonly WorkerHeartbeats _heartbeats;
    private readonly WeirOptions _options;
    private readonly WorkerLoopTimings _timings;
    private readonly TimeProvider _time;
    private readonly ILogger<RefinerWorkerService> _logger;

    public RefinerWorkerService(
        RefinerJobProcessor processor,
        RefinerJobStore store,
        WorkerHeartbeats heartbeats,
        WeirOptions options,
        WorkerLoopTimings timings,
        TimeProvider time,
        ILogger<RefinerWorkerService> logger)
    {
        _processor = processor;
        _store = store;
        _heartbeats = heartbeats;
        _options = options;
        _timings = timings;
        _time = time;
        _logger = logger;
    }

    /// <summary><c>_lease_owner</c>: <c>{hostname}-{pid}-w{index}</c>.</summary>
    public static string LeaseOwner(int workerIndex) =>
        string.Create(CultureInfo.InvariantCulture, $"{System.Net.Dns.GetHostName()}-{Environment.ProcessId}-w{workerIndex}");

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await Task.Yield();
        // The shipped default is 8 slots; the saved files-at-once value gates how many are active (#329).
        _logger.LogDebug(
            "Refiner worker slot cap is {SlotCap}; the saved files-at-once setting gates how many are active.",
            _options.RefinerWorkerCount);
        var slots = Enumerable.Range(0, _options.RefinerWorkerCount)
            .Select(index => Task.Run(() => RunSlotAsync(index, stoppingToken), CancellationToken.None))
            .ToArray();
        await Task.WhenAll(slots).ConfigureAwait(false);
    }

    /// <summary>One slot: repeatedly process jobs until stopping.</summary>
    internal async Task RunSlotAsync(int workerIndex, CancellationToken stoppingToken)
    {
        var owner = LeaseOwner(workerIndex);
        _heartbeats.Started(HeartbeatModule, workerIndex);
        var cachedMaxConcurrent = 8;
        long cacheExpires = 0;
        var cacheValid = false;
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                _heartbeats.Beat(HeartbeatModule, workerIndex);
                if (!cacheValid || _time.GetTimestamp() >= cacheExpires)
                {
                    try
                    {
                        cachedMaxConcurrent = Math.Max(1, Math.Min(8, await ReadMaxConcurrentFilesAsync(stoppingToken).ConfigureAwait(false)));
                        cacheExpires = _time.GetTimestamp() + (long)(_timings.ConcurrencyCacheTtl.TotalSeconds * _time.TimestampFrequency);
                        cacheValid = true;
                    }
                    catch (Exception exception) when (exception is not OperationCanceledException)
                    {
                        // Python: keep the previous value and try again next pass.
                    }
                }

                if (workerIndex >= cachedMaxConcurrent)
                {
                    await IdleWithHeartbeatsAsync(workerIndex, stoppingToken).ConfigureAwait(false);
                    continue;
                }

                JobProcessOutcome outcome;
                try
                {
                    outcome = await _processor.ProcessOneAsync(owner, _timings.LeaseSeconds, cancellationToken: stoppingToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    break;
                }
#pragma warning disable CA1031 // The worker survives a crashed tick and tries again.
                catch (Exception exception)
#pragma warning restore CA1031
                {
                    _logger.LogError(exception, "Refiner worker tick crashed worker_index={WorkerIndex}", workerIndex);
                    await Task.Delay(_timings.TickErrorBackoff, _time, stoppingToken).ConfigureAwait(false);
                    continue;
                }

                if (stoppingToken.IsCancellationRequested)
                {
                    break;
                }

                if (outcome == JobProcessOutcome.Idle)
                {
                    await IdleWithHeartbeatsAsync(workerIndex, stoppingToken).ConfigureAwait(false);
                }

                // Processed: spin straight on to drain the queue.
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
        finally
        {
            _heartbeats.Stopped(HeartbeatModule, workerIndex);
        }
    }

    private async Task IdleWithHeartbeatsAsync(int workerIndex, CancellationToken stoppingToken)
    {
        var deadline = _time.GetTimestamp() + (long)(_timings.IdleSleep.TotalSeconds * _time.TimestampFrequency);
        while (!stoppingToken.IsCancellationRequested)
        {
            _heartbeats.Beat(HeartbeatModule, workerIndex);
            var remaining = TimeSpan.FromSeconds((deadline - _time.GetTimestamp()) / (double)_time.TimestampFrequency);
            if (remaining <= TimeSpan.Zero)
            {
                break;
            }

            await Task.Delay(remaining < TimeSpan.FromSeconds(1) ? remaining : TimeSpan.FromSeconds(1), _time, stoppingToken).ConfigureAwait(false);
        }
    }

    /// <summary>The saved "Files at once" value; the operator settings row defaults it to 1.</summary>
    private Task<int> ReadMaxConcurrentFilesAsync(CancellationToken cancellationToken) =>
        _store.InTransactionAsync(
            (connection, transaction) =>
            {
                var value = RefinerJobStore.Scalar(connection, transaction, "SELECT max_concurrent_files FROM refiner_operator_settings WHERE id = 1");
                return value is null or DBNull ? 1 : (int)Math.Clamp(Convert.ToInt64(value, CultureInfo.InvariantCulture), int.MinValue, int.MaxValue);
            },
            cancellationToken);
}

/// <summary>
/// <c>platform-job-rows-retention</c> (port of <c>_run_job_rows_retention_forever</c>): prune on start,
/// then every <c>WEIR_JOB_ROWS_RETENTION_SCHEDULE_INTERVAL_SECONDS</c>.
/// </summary>
public sealed class JobRowsRetentionTask : IPeriodicTask
{
    private readonly RefinerJobStore _store;
    private readonly WeirOptions _options;
    private readonly TimeProvider _time;
    private readonly ILogger<JobRowsRetentionTask> _logger;

    public JobRowsRetentionTask(RefinerJobStore store, WeirOptions options, TimeProvider time, ILogger<JobRowsRetentionTask> logger)
    {
        _store = store;
        _options = options;
        _time = time;
        _logger = logger;
    }

    public string Name => "platform-job-rows-retention";

    public TimeSpan Interval => TimeSpan.FromSeconds(_options.JobRowsRetentionScheduleIntervalSeconds);

    public bool RunAtStart => true;

    public TimeSpan? FailureCooldown => null;

    public string FailureMessage => "Job-row retention prune tick failed";

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        var counts = await Task.Run(
            () => JobRowsRetention.RunTickAsync(_store, _options.JobRowsRetentionDays, _time.GetUtcNow(), cancellationToken),
            cancellationToken).ConfigureAwait(false);
        if (counts.Total > 0)
        {
            _logger.LogInformation(
                "History retention pruned refiner jobs={RefinerJobs} activity events={ActivityEvents}",
                counts.Refiner,
                counts.Activity);
        }
    }
}

/// <summary>One family's periodic enqueue timer.</summary>
public interface IPeriodicEnqueuer
{
    /// <summary>A name for logs.</summary>
    string Name { get; }

    /// <summary>The job kind it enqueues; the timer runs only when this server has a handler for it.</summary>
    string JobKind { get; }

    TimeSpan Interval { get; }

    /// <summary>Whether the family is switched on, read once at startup as Python does.</summary>
    Task<bool> IsEnabledAsync(CancellationToken cancellationToken);

    Task EnqueueOnceAsync(CancellationToken cancellationToken);
}

/// <summary>
/// Runs every registered <see cref="IPeriodicEnqueuer"/> on its own timer (port of the
/// <c>_run_periodic_scope_enqueue</c> loops): enqueue, then wait the interval; after a failure, wait two
/// seconds and try again.
/// </summary>
/// <remarks>
/// A family is only timed when this server can run its job kind, for the same reason unported kinds
/// are not claimed: a .NET server must not fill the queue with work only another backend can do.
/// </remarks>
public sealed class PeriodicEnqueueService : BackgroundService
{
    private readonly IReadOnlyList<IPeriodicEnqueuer> _enqueuers;
    private readonly JobHandlerRegistry _handlers;
    private readonly TimeProvider _time;
    private readonly ILogger<PeriodicEnqueueService> _logger;

    public PeriodicEnqueueService(
        IEnumerable<IPeriodicEnqueuer> enqueuers,
        JobHandlerRegistry handlers,
        TimeProvider time,
        ILogger<PeriodicEnqueueService> logger)
    {
        _enqueuers = [.. enqueuers];
        _handlers = handlers;
        _time = time;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await Task.Yield();
        var running = new List<Task>();
        foreach (var enqueuer in _enqueuers)
        {
            if (!_handlers.Contains(enqueuer.JobKind))
            {
                continue;
            }

            bool enabled;
            try
            {
                enabled = await enqueuer.IsEnabledAsync(stoppingToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                _logger.LogError(exception, "Refiner could not read whether {Name} is enabled; leaving it off.", enqueuer.Name);
                enabled = false;
            }

            if (enabled && enqueuer.Interval > TimeSpan.Zero)
            {
                running.Add(Task.Run(() => RunAsync(enqueuer, stoppingToken), CancellationToken.None));
            }
        }

        await Task.WhenAll(running).ConfigureAwait(false);
    }

    internal Task RunAsync(IPeriodicEnqueuer enqueuer, CancellationToken stoppingToken) =>
        PeriodicTaskRunner.RunAsync(new EnqueueTask(enqueuer), _time, _logger, stoppingToken);

    /// <summary>One family as a periodic task: enqueue at once, then every interval; two seconds after a failure.</summary>
    private sealed class EnqueueTask(IPeriodicEnqueuer enqueuer) : IPeriodicTask
    {
        public string Name => enqueuer.Name;

        public TimeSpan Interval => enqueuer.Interval;

        public bool RunAtStart => true;

        public TimeSpan? FailureCooldown => PeriodicSchedule.FailureCooldown;

        public string FailureMessage => $"Refiner periodic enqueue failed ({enqueuer.Name})";

        public Task RunOnceAsync(CancellationToken cancellationToken) => enqueuer.EnqueueOnceAsync(cancellationToken);
    }
}

/// <summary>Job kinds and dedupe keys of the periodic families (<c>*_job_kinds.py</c>).</summary>
public static class PeriodicJobKinds
{
    public const string WorkTempStaleSweep = "refiner.work_temp_stale_sweep.v1";
    public const string WorkTempStaleSweepDedupeKeyMovie = "refiner.work_temp_stale_sweep:v1:movie";
    public const string WorkTempStaleSweepDedupeKeyTv = "refiner.work_temp_stale_sweep:v1:tv";
    public const string MovieFailureCleanupSweep = "refiner.movie_failure_cleanup_sweep.v1";
    public const string TvFailureCleanupSweep = "refiner.tv_failure_cleanup_sweep.v1";
    public const string MovieFailureCleanupSweepDedupeKey = "refiner.movie_failure_cleanup_sweep:v1";
    public const string TvFailureCleanupSweepDedupeKey = "refiner.tv_failure_cleanup_sweep:v1";
}

/// <summary>
/// <c>enqueue_refiner_work_temp_stale_sweep_job</c> on a timer: one row per scope, deduped per scope.
/// Enabled by <c>refiner_operator_settings.work_temp_stale_sweep_enabled</c>; an explicit
/// <c>WEIR_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED=0</c> is a kill switch.
/// </summary>
public sealed class WorkTempStaleSweepEnqueuer : IPeriodicEnqueuer
{
    private readonly RefinerJobStore _store;
    private readonly string _scope;
    private readonly bool _killSwitch;

    public WorkTempStaleSweepEnqueuer(RefinerJobStore store, string mediaScope, TimeSpan interval, bool killSwitch)
    {
        _store = store;
        _scope = RefinerLibraryFolders.NormalizeMediaScope(mediaScope);
        Interval = interval;
        _killSwitch = killSwitch;
    }

    public string Name => $"work temp stale sweep ({_scope})";

    public string JobKind => PeriodicJobKinds.WorkTempStaleSweep;

    public TimeSpan Interval { get; }

    public Task<bool> IsEnabledAsync(CancellationToken cancellationToken) =>
        _killSwitch ? Task.FromResult(false) : OperatorSettingFlagAsync(_store, "work_temp_stale_sweep_enabled", defaultValue: true, cancellationToken);

    public Task EnqueueOnceAsync(CancellationToken cancellationToken) =>
        _store.EnqueueOrGetAsync(
            _scope == "tv" ? PeriodicJobKinds.WorkTempStaleSweepDedupeKeyTv : PeriodicJobKinds.WorkTempStaleSweepDedupeKeyMovie,
            PeriodicJobKinds.WorkTempStaleSweep,
            PyJsonWriter.Dumps(new PyDict().Set("media_scope", _scope).Set("trigger", "scheduled"), PyJsonFormat.Compact),
            cancellationToken: cancellationToken);

    /// <summary>A boolean column of the operator settings row; Python creates the row with its defaults when missing.</summary>
    internal static Task<bool> OperatorSettingFlagAsync(RefinerJobStore store, string column, bool defaultValue, CancellationToken cancellationToken) =>
        store.InTransactionAsync(
            (connection, transaction) =>
            {
                var value = RefinerJobStore.Scalar(connection, transaction, $"SELECT {column} FROM refiner_operator_settings WHERE id = 1");
                return value is null or DBNull ? defaultValue : WorkAdmissionReader.Bool(value);
            },
            cancellationToken);
}

/// <summary>
/// <c>enqueue_refiner_failure_cleanup_sweep_job</c> on a timer. A sweep still queued or running is not
/// duplicated; a skipped Activity entry says so instead.
/// </summary>
public sealed class FailureCleanupSweepEnqueuer : IPeriodicEnqueuer
{
    private readonly RefinerJobStore _store;
    private readonly string _scope;
    private readonly bool _killSwitch;

    public FailureCleanupSweepEnqueuer(RefinerJobStore store, string mediaScope, TimeSpan interval, bool killSwitch)
    {
        _store = store;
        _scope = string.Equals(mediaScope.Trim(), "tv", StringComparison.OrdinalIgnoreCase) ? "tv" : "movie";
        Interval = interval;
        _killSwitch = killSwitch;
    }

    public string Name => $"failure cleanup sweep ({_scope})";

    public string JobKind => _scope == "tv" ? PeriodicJobKinds.TvFailureCleanupSweep : PeriodicJobKinds.MovieFailureCleanupSweep;

    public TimeSpan Interval { get; }

    public Task<bool> IsEnabledAsync(CancellationToken cancellationToken) =>
        _killSwitch
            ? Task.FromResult(false)
            : WorkTempStaleSweepEnqueuer.OperatorSettingFlagAsync(_store, "failure_cleanup_enabled", defaultValue: false, cancellationToken);

    public Task EnqueueOnceAsync(CancellationToken cancellationToken) =>
        _store.InTransactionAsync(
            (connection, transaction) =>
            {
                var (job, inserted) = EnqueueSweep(connection, transaction, _store, _scope, "scheduled");
                if (!inserted)
                {
                    var label = _scope == "tv" ? "TV" : "Movies";
                    var detail = new PyDict()
                        .Set("media_scope", _scope)
                        .Set("cleanup_run_status", "skipped")
                        .Set("reason", "Previous cleanup job is still queued or running.")
                        .Set("existing_job_id", job.Id)
                        .Set("result", "skipped")
                        .Set("trigger", "scheduled");
                    SqliteActivityWriter.Record(
                        connection,
                        transaction,
                        new ActivityEventDraft(ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "refiner", $"Refiner cleanup skipped for {label}", PyJsonWriter.Dumps(detail, PyJsonFormat.Compact)));
                }

                return inserted;
            },
            cancellationToken);

    internal static (RefinerJob Job, bool Inserted) EnqueueSweep(
        Microsoft.Data.Sqlite.SqliteConnection connection,
        Microsoft.Data.Sqlite.SqliteTransaction transaction,
        RefinerJobStore store,
        string scope,
        string trigger)
    {
        var jobKind = scope == "tv" ? PeriodicJobKinds.TvFailureCleanupSweep : PeriodicJobKinds.MovieFailureCleanupSweep;
        var dedupeBase = scope == "tv" ? PeriodicJobKinds.TvFailureCleanupSweepDedupeKey : PeriodicJobKinds.MovieFailureCleanupSweepDedupeKey;
        var active = RefinerJobStore.Query(
            connection,
            transaction,
            "SELECT id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count, max_attempts, " +
            "last_error, not_before, runner_cost, priority, created_at, updated_at FROM refiner_jobs " +
            "WHERE job_kind = @kind AND status IN (@pending, @leased) ORDER BY id ASC LIMIT 1",
            ("@kind", jobKind),
            ("@pending", RefinerJobStatus.Pending),
            ("@leased", RefinerJobStatus.Leased)).FirstOrDefault();
        if (active is not null)
        {
            return (active, false);
        }

        var dedupe = $"{dedupeBase}:{Guid.NewGuid():N}";
        var payload = PyJsonWriter.Dumps(new PyDict().Set("media_scope", scope).Set("trigger", trigger), PyJsonFormat.Compact);
        return (store.EnqueueOrGet(connection, transaction, dedupe, jobKind, payload, JobQueueRules.DefaultMaxAttempts, 0, 0), true);
    }
}

/// <summary>Registers the durable job queue, crash recovery, workers, retention and periodic enqueue.</summary>
public static class WeirJobs
{
    /// <summary>
    /// Adds everything #521 ports. Job handlers are added separately as <see cref="IJobHandler"/>
    /// singletons by the areas that port them; with none registered, the workers only refuse retired rows.
    /// </summary>
    public static IServiceCollection AddWeirJobs(this IServiceCollection services, WeirOptions options, RuntimeEnvironment runtime)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(runtime);
        services.AddWeirPlatform(options);
        services.TryAddSingleton<IJobQueueMetrics>(NoJobQueueMetrics.Instance);
        services.TryAddSingleton<IJobNotifications, NoJobNotifications>();
        services.TryAddSingleton<IUnhandledJobFailureRecorder, NoUnhandledJobFailureRecorder>();
        services.TryAddSingleton(new WorkerLoopTimings { LeaseSeconds = options.RefinerJobLeaseSeconds });
        services.TryAddSingleton(sp => new RefinerJobStore(
            sp.GetRequiredService<SqliteDatabase>(), sp.GetRequiredService<TimeProvider>(), sp.GetRequiredService<IJobQueueMetrics>()));
        services.TryAddSingleton(sp => new JobHandlerRegistry(sp.GetServices<IJobHandler>()));
        services.TryAddSingleton<RefinerJobProcessor>();

        // Kill switches: an explicitly set variable that reads as off wins over the saved setting.
        const string sweepVariable = "WEIR_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED";
        const string cleanupVariable = "WEIR_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED";
        var sweepKilled = runtime.IsSet(sweepVariable) && !options.RefinerWorkTempStaleSweepMovieScheduleEnabled;
        var cleanupKilled = runtime.IsSet(cleanupVariable) && !options.RefinerMovieFailureCleanupScheduleEnabled;
        services.AddSingleton<IPeriodicEnqueuer>(sp => new WorkTempStaleSweepEnqueuer(
            sp.GetRequiredService<RefinerJobStore>(), "movie", TimeSpan.FromSeconds(options.RefinerWorkTempStaleSweepMovieScheduleIntervalSeconds), sweepKilled));
        services.AddSingleton<IPeriodicEnqueuer>(sp => new WorkTempStaleSweepEnqueuer(
            sp.GetRequiredService<RefinerJobStore>(), "tv", TimeSpan.FromSeconds(options.RefinerWorkTempStaleSweepTvScheduleIntervalSeconds), sweepKilled));
        services.AddSingleton<IPeriodicEnqueuer>(sp => new FailureCleanupSweepEnqueuer(
            sp.GetRequiredService<RefinerJobStore>(), "movie", TimeSpan.FromSeconds(options.RefinerMovieFailureCleanupScheduleIntervalSeconds), cleanupKilled));
        services.AddSingleton<IPeriodicEnqueuer>(sp => new FailureCleanupSweepEnqueuer(
            sp.GetRequiredService<RefinerJobStore>(), "tv", TimeSpan.FromSeconds(options.RefinerTvFailureCleanupScheduleIntervalSeconds), cleanupKilled));

        // Hosted services start in this order: recovery completes before any worker claims.
        services.AddSingleton<JobsStartupRecoveryService>();
        services.AddHostedService(sp => sp.GetRequiredService<JobsStartupRecoveryService>());
        services.AddSingleton<IPeriodicTask, JobRowsRetentionTask>();
        services.AddWeirPeriodicTasks();
        services.AddHostedService<PeriodicEnqueueService>();
        if (options.RefinerWorkerCount > 0)
        {
            services.AddHostedService<RefinerWorkerService>();
        }

        return services;
    }
}
