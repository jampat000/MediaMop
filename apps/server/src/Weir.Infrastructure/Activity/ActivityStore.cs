using Weir.Core.Activity;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Activity;

/// <summary>Writes to <c>activity_events</c> (port of the write side of <c>weir.platform.activity.service</c>).</summary>
public static class ActivityStore
{
    private static readonly TimeSpan LoginFailedSuppress = TimeSpan.FromMinutes(2);
    private static readonly TimeSpan BootstrapDeniedSuppress = TimeSpan.FromSeconds(60);

    /// <summary><c>record_activity_event</c>: the facts are lifted from the detail; <c>created_at</c> is the database default.</summary>
    public static async Task<long> RecordAsync(UnitOfWork uow, string eventType, string module, string title, string? detail)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var facts = ActivityClassifier.Classify(eventType, detail);
        var id = await uow.ExecuteScalarWriteAsync(
            "INSERT INTO activity_events (event_type, module, title, detail, \"trigger\", result, library_id, relative_path, run_key) " +
            "VALUES ($type, $module, $title, $detail, $trigger, $result, $library, $path, $run) RETURNING id",
            ("$type", eventType),
            ("$module", module),
            ("$title", title),
            ("$detail", detail),
            ("$trigger", facts.Trigger),
            ("$result", facts.Result),
            ("$library", facts.LibraryId),
            ("$path", facts.RelativePath),
            ("$run", facts.RunKey)).ConfigureAwait(false);
        return Convert.ToInt64(id, System.Globalization.CultureInfo.InvariantCulture);
    }

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
