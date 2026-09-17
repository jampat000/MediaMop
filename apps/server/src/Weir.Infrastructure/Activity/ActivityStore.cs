using Weir.Core.Activity;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Activity;

/// <summary>The auth-side Activity helpers of <c>weir.platform.activity.service</c>, written through <see cref="SqliteActivityWriter"/>.</summary>
public static class ActivityStore
{
    private static readonly TimeSpan LoginFailedSuppress = TimeSpan.FromMinutes(2);
    private static readonly TimeSpan BootstrapDeniedSuppress = TimeSpan.FromSeconds(60);

    /// <summary><c>record_activity_event</c> inside the caller's unit of work.</summary>
    public static Task<long> RecordAsync(UnitOfWork uow, string eventType, string module, string title, string? detail) =>
        SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(eventType, module, title, detail));

    /// <summary><c>maybe_record_login_failed</c>: one event per username per two minutes.</summary>
    public static async Task MaybeRecordLoginFailedAsync(UnitOfWork uow, string username, PyDateTime now)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var cutoff = PyDateTime.FromUtc(now.AsUtc - LoginFailedSuppress);
        var exists = await uow.ScalarAsync(
            "SELECT activity_events.id FROM activity_events WHERE activity_events.event_type = $type AND activity_events.detail = $detail " +
            "AND activity_events.created_at >= $cutoff LIMIT 1 OFFSET 0",
            ("$type", ActivityEventTypes.AuthLoginFailed),
            ("$detail", username),
            ("$cutoff", cutoff.ToSqlite())).ConfigureAwait(false);
        if (exists is not null)
        {
            return;
        }

        await RecordAsync(uow, ActivityEventTypes.AuthLoginFailed, "auth", "Sign-in failed", username).ConfigureAwait(false);
    }

    /// <summary><c>maybe_record_bootstrap_denied</c>: at most one per minute.</summary>
    public static async Task MaybeRecordBootstrapDeniedAsync(UnitOfWork uow, PyDateTime now)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var cutoff = PyDateTime.FromUtc(now.AsUtc - BootstrapDeniedSuppress);
        var exists = await uow.ScalarAsync(
            "SELECT activity_events.id FROM activity_events WHERE activity_events.event_type = $type AND activity_events.created_at >= $cutoff LIMIT 1 OFFSET 0",
            ("$type", ActivityEventTypes.AuthBootstrapDenied),
            ("$cutoff", cutoff.ToSqlite())).ConfigureAwait(false);
        if (exists is not null)
        {
            return;
        }

        await RecordAsync(uow, ActivityEventTypes.AuthBootstrapDenied, "auth", "Bootstrap not allowed", "An admin account already exists.").ConfigureAwait(false);
    }
}

/// <summary>Port of <c>weir.platform.suite_settings.operational_history</c>.</summary>
public static class OperationalHistoryStore
{
    private const string TerminalStatuses = "('completed', 'failed', 'handler_ok_finalize_failed', 'cancelled')";

    public sealed record ResetResult(long ActivityEventsDeleted, long RefinerJobsDeleted)
    {
        public long TotalDeleted => ActivityEventsDeleted + RefinerJobsDeleted;
    }

    public static async Task<ResetResult> PreviewAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var activity = await uow.CountAsync("SELECT count(*) FROM activity_events").ConfigureAwait(false);
        var jobs = await uow.CountAsync($"SELECT count(*) FROM refiner_jobs WHERE refiner_jobs.status IN {TerminalStatuses}").ConfigureAwait(false);
        return new ResetResult(activity, jobs);
    }

    public static async Task<ResetResult> ResetAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var counts = await PreviewAsync(uow).ConfigureAwait(false);
        await uow.ExecuteAsync("DELETE FROM activity_events").ConfigureAwait(false);
        await uow.ExecuteAsync($"DELETE FROM refiner_jobs WHERE refiner_jobs.status IN {TerminalStatuses}").ConfigureAwait(false);
        return counts;
    }
}
