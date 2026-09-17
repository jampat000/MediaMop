using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>One maintenance family's current state (<c>MaintenanceFamilyStateOut</c>).</summary>
public sealed record MaintenanceFamilyState(
    string Family,
    bool Enabled,
    string Description,
    long Pending,
    long Running,
    PyDateTime? LastCompletedAt,
    PyDateTime? LastFailedAt,
    string? LastError);

/// <summary>Port of <c>refiner_maintenance_api.py</c>'s read model and manual trigger.</summary>
public static class MaintenanceStore
{
    private static readonly Dictionary<string, IReadOnlyList<string>> FamilyJobKinds = new(StringComparer.Ordinal)
    {
        ["work_temp_stale_sweep"] = [PeriodicJobKinds.WorkTempStaleSweep],
        ["failure_cleanup"] = [PeriodicJobKinds.MovieFailureCleanupSweep, PeriodicJobKinds.TvFailureCleanupSweep],
    };

    private static readonly Dictionary<string, string> FamilyDescriptions = new(StringComparer.Ordinal)
    {
        ["work_temp_stale_sweep"] = "Reclaims Weir's own stale working files. Safe, and switched on by default.",
        ["failure_cleanup"] = "Removes the source release folder after a file has failed terminally. This deletes the original, so it stays switched off until you choose it.",
    };

    public static async Task<MaintenanceFamilyState> StateForAsync(UnitOfWork uow, string family, bool enabled)
    {
        var kinds = FamilyJobKinds[family];
        var placeholders = string.Join(",", kinds.Select((_, i) => $"@kind{i}"));
        var parameters = kinds.Select((k, i) => ($"@kind{i}", (object?)k)).ToArray();
        var rows = await uow.QueryAsync(
            $"SELECT status, updated_at, last_error FROM refiner_jobs WHERE job_kind IN ({placeholders}) ORDER BY id DESC",
            reader => (Status: reader.GetString(0), UpdatedAt: SqliteValues.GetDateTime(reader, 1), LastError: SqliteValues.GetStringOrNull(reader, 2)),
            parameters).ConfigureAwait(false);

        var pending = rows.Count(r => r.Status == "pending");
        var running = rows.Count(r => r.Status == "leased");
        var completed = rows.FirstOrDefault(r => r.Status == "completed");
        var failed = rows.FirstOrDefault(r => r.Status == "failed");

        return new MaintenanceFamilyState(
            family, enabled, FamilyDescriptions[family], pending, running,
            completed.Status is null ? null : completed.UpdatedAt,
            failed.Status is null ? null : failed.UpdatedAt,
            failed.Status is null ? null : failed.LastError);
    }

    /// <summary><c>enqueue_refiner_work_temp_stale_sweep_job</c>: single-flight per scope, ignores the schedule toggle.</summary>
    public static Task EnqueueWorkTempStaleSweepAsync(RefinerJobStore jobStore, string mediaScope, string trigger)
    {
        var scope = mediaScope == "tv" ? "tv" : "movie";
        var dedupe = scope == "tv" ? PeriodicJobKinds.WorkTempStaleSweepDedupeKeyTv : PeriodicJobKinds.WorkTempStaleSweepDedupeKeyMovie;
        var payload = PyJsonWriter.Dumps(new PyDict().Set("media_scope", scope).Set("trigger", trigger), PyJsonFormat.Compact);
        return jobStore.EnqueueOrGetAsync(dedupe, PeriodicJobKinds.WorkTempStaleSweep, payload);
    }

    /// <summary>
    /// <c>enqueue_refiner_failure_cleanup_sweep_job</c>: returns the existing row when one is already queued
    /// or running, else inserts a new one — in the same transaction as the caller's other work, unlike the
    /// periodic <see cref="FailureCleanupSweepEnqueuer"/> in <c>JobServices.cs</c>, whose helper is internal
    /// to that file and runs on its own <see cref="RefinerJobStore"/> connection.
    /// </summary>
    public static async Task<(long JobId, bool Inserted)> EnqueueFailureCleanupSweepAsync(UnitOfWork uow, string mediaScope, string trigger)
    {
        var scope = mediaScope == "tv" ? "tv" : "movie";
        var jobKind = scope == "tv" ? PeriodicJobKinds.TvFailureCleanupSweep : PeriodicJobKinds.MovieFailureCleanupSweep;
        var dedupeBase = scope == "tv" ? PeriodicJobKinds.TvFailureCleanupSweepDedupeKey : PeriodicJobKinds.MovieFailureCleanupSweepDedupeKey;

        var active = await uow.QueryAsync(
            "SELECT id FROM refiner_jobs WHERE job_kind = @kind AND status IN ('pending', 'leased') ORDER BY id ASC LIMIT 1",
            reader => reader.GetInt64(0), ("@kind", jobKind)).ConfigureAwait(false);
        if (active.Count > 0)
        {
            return (active[0], false);
        }

        var dedupe = $"{dedupeBase}:{Guid.NewGuid():N}";
        var payload = PyJsonWriter.Dumps(new PyDict().Set("media_scope", scope).Set("trigger", trigger), PyJsonFormat.Compact);
        var inserted = await uow.ExecuteScalarWriteAsync(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, max_attempts, runner_cost, priority) " +
            "VALUES (@dedupe, @kind, @payload, 'pending', 3, 0, 0) ON CONFLICT (dedupe_key) DO NOTHING RETURNING id",
            ("@dedupe", dedupe), ("@kind", jobKind), ("@payload", payload)).ConfigureAwait(false);
        var jobId = inserted is null or DBNull
            ? await uow.ScalarAsync("SELECT id FROM refiner_jobs WHERE dedupe_key = @dedupe", ("@dedupe", dedupe)).ConfigureAwait(false)
            : inserted;
        return (Convert.ToInt64(jobId, System.Globalization.CultureInfo.InvariantCulture), true);
    }
}
