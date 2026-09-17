using Microsoft.Extensions.Logging;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Logging;
using Weir.Infrastructure.Settings;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Scheduling;

/// <summary>
/// Background work that runs on a schedule. The jobs port (#521) hosts these next to the workers;
/// until then nothing runs them, and each one's logic is exercised directly by tests.
/// </summary>
public interface IPeriodicTask
{
    /// <summary>The asyncio task name Python used, for logs.</summary>
    string Name { get; }

    /// <summary>Time between runs.</summary>
    TimeSpan Interval { get; }

    /// <summary>Run once as soon as the host starts, rather than after the first interval.</summary>
    bool RunAtStart { get; }

    /// <summary>How long to wait after a failed run before trying again (the interval when <see langword="null"/>).</summary>
    TimeSpan? FailureCooldown { get; }

    Task RunOnceAsync(CancellationToken cancellationToken);
}

/// <summary><c>auth-session-cleanup</c>: delete sessions that can no longer authenticate, hourly.</summary>
public sealed class SessionCleanupTask : IPeriodicTask
{
    private readonly SqliteDatabase _database;
    private readonly AuthService _auth;
    private readonly ILogger _logger;

    public SessionCleanupTask(SqliteDatabase database, AuthService auth, ILoggerFactory loggerFactory)
    {
        ArgumentNullException.ThrowIfNull(loggerFactory);
        _database = database;
        _auth = auth;
        _logger = loggerFactory.CreateLogger("weir.platform.auth.session_cleanup");
    }

    public string Name => "auth-session-cleanup";

    public TimeSpan Interval => TimeSpan.FromSeconds(3600);

    public bool RunAtStart => false;

    public TimeSpan? FailureCooldown => null;

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            var removed = await _auth.CleanupInactiveSessionsAsync(uow).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
            if (removed > 0)
            {
                _logger.LogInformation("auth event: cleaned up inactive sessions (count={Count})", removed);
            }
            else
            {
                _logger.LogDebug("auth event: inactive session cleanup found nothing to remove");
            }
        }
    }
}

/// <summary><c>suite-log-retention</c>: checked hourly, prunes <c>weir.log</c> at most once a day.</summary>
public sealed class LogRetentionTask : IPeriodicTask
{
    public static readonly TimeSpan MinRunInterval = TimeSpan.FromHours(24);

    private readonly SqliteDatabase _database;
    private readonly WeirLogFile _logFile;
    private readonly TimeProvider _time;
    private DateTimeOffset? _lastPruneAt;

    public LogRetentionTask(SqliteDatabase database, WeirLogFile logFile, TimeProvider time)
    {
        _database = database;
        _logFile = logFile;
        _time = time;
    }

    public string Name => "suite-log-retention";

    public TimeSpan Interval => TimeSpan.FromSeconds(3600);

    public bool RunAtStart => true;

    public TimeSpan? FailureCooldown => null;

    public Task RunOnceAsync(CancellationToken cancellationToken) => TickAsync(null, cancellationToken);

    /// <summary><c>run_log_retention_tick</c>: 1 when the log was pruned.</summary>
    public async Task<int> TickAsync(DateTimeOffset? now, CancellationToken cancellationToken)
    {
        var when = now ?? _time.GetUtcNow();
        if (_lastPruneAt is { } last && when - last < MinRunInterval)
        {
            return 0;
        }

        var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            var suite = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
            _logFile.Prune((int)Math.Max(1, Math.Min(int.MaxValue, suite.LogRetentionDays)));
        }

        _lastPruneAt = when;
        return 1;
    }
}

/// <summary><c>suite-configuration-backup</c>: every minute, write a snapshot when one is due.</summary>
public sealed class ConfigurationBackupTask : IPeriodicTask
{
    private readonly SqliteDatabase _database;
    private readonly ConfigurationBackups _backups;

    public ConfigurationBackupTask(SqliteDatabase database, ConfigurationBackups backups)
    {
        _database = database;
        _backups = backups;
    }

    public string Name => "suite-configuration-backup";

    public TimeSpan Interval => TimeSpan.FromSeconds(60);

    public bool RunAtStart => true;

    public TimeSpan? FailureCooldown => TimeSpan.FromSeconds(5);

    public Task RunOnceAsync(CancellationToken cancellationToken) => _backups.RunTickAsync(_database, null, cancellationToken);
}

/// <summary>What the host registers for the jobs port to run.</summary>
public static class PeriodicTaskRegistry
{
    public static IReadOnlyList<Type> TaskTypes { get; } = [typeof(SessionCleanupTask), typeof(LogRetentionTask), typeof(ConfigurationBackupTask)];
}
