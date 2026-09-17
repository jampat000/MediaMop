using Microsoft.Data.Sqlite;
using Weir.Core.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>The singleton <c>refiner_operator_settings</c> row (port of <c>refiner_operator_settings_service.py</c>).</summary>
public static class OperatorSettingsStore
{
    private const string Columns =
        "max_concurrent_files, runner_capacity, runner_cost_sd, runner_cost_720p, runner_cost_1080p, runner_cost_4k, " +
        "runner_cost_undetermined, work_temp_stale_sweep_enabled, failure_cleanup_enabled, keep_failed_work_files, " +
        "file_log_retention_days, verbose_detection_logging, min_file_age_seconds, refiner_min_input_file_size_mb, " +
        "minimum_free_disk_space_mb, movie_schedule_enabled, movie_schedule_hours_limited, movie_schedule_days, " +
        "movie_schedule_start, movie_schedule_end, tv_schedule_enabled, tv_schedule_hours_limited, tv_schedule_days, " +
        "tv_schedule_start, tv_schedule_end, updated_at";

    public static Task<RefinerOperatorSettingsRecord?> GetAsync(UnitOfWork uow) =>
        uow.QuerySingleAsync($"SELECT {Columns} FROM refiner_operator_settings WHERE id = 1", Read);

    /// <summary><c>ensure_refiner_operator_settings_row</c>.</summary>
    public static async Task<RefinerOperatorSettingsRecord> EnsureAsync(UnitOfWork uow)
    {
        var row = await GetAsync(uow).ConfigureAwait(false);
        if (row is not null)
        {
            return row;
        }

        await uow.ExecuteAsync(
            "INSERT INTO refiner_operator_settings (id, max_concurrent_files, runner_capacity, runner_cost_sd, runner_cost_720p, " +
            "runner_cost_1080p, runner_cost_4k, runner_cost_undetermined, work_temp_stale_sweep_enabled, failure_cleanup_enabled, " +
            "keep_failed_work_files, file_log_retention_days, verbose_detection_logging, min_file_age_seconds, " +
            "refiner_min_input_file_size_mb, minimum_free_disk_space_mb, movie_schedule_enabled, movie_schedule_hours_limited, " +
            "movie_schedule_days, movie_schedule_start, movie_schedule_end, tv_schedule_enabled, tv_schedule_hours_limited, " +
            "tv_schedule_days, tv_schedule_start, tv_schedule_end) VALUES (1, 1, 4, 0, 0, 1, 1, 0, 1, 0, 0, 90, 0, 60, 50, 5120, " +
            "1, 0, '', '00:00', '23:59', 1, 0, '', '00:00', '23:59')").ConfigureAwait(false);
        return await GetAsync(uow).ConfigureAwait(false) ?? throw new InvalidOperationException("refiner_operator_settings row was not created.");
    }

    public static async Task UpdateAsync(UnitOfWork uow, RefinerOperatorSettingsRecord before, RefinerOperatorSettingsRecord after)
    {
        var sets = new List<string>();
        var parameters = new List<(string, object?)>();
        void Compare<T>(string column, T left, T right, Func<T, object?> toDb)
        {
            if (!EqualityComparer<T>.Default.Equals(left, right))
            {
                sets.Add($"{column}=${column}");
                parameters.Add(($"${column}", toDb(right)));
            }
        }

        Compare("max_concurrent_files", before.MaxConcurrentFiles, after.MaxConcurrentFiles, v => v);
        Compare("runner_capacity", before.RunnerCapacity, after.RunnerCapacity, v => v);
        Compare("runner_cost_sd", before.RunnerCostSd, after.RunnerCostSd, v => v);
        Compare("runner_cost_720p", before.RunnerCost720P, after.RunnerCost720P, v => v);
        Compare("runner_cost_1080p", before.RunnerCost1080P, after.RunnerCost1080P, v => v);
        Compare("runner_cost_4k", before.RunnerCost4K, after.RunnerCost4K, v => v);
        Compare("runner_cost_undetermined", before.RunnerCostUndetermined, after.RunnerCostUndetermined, v => v);
        Compare("work_temp_stale_sweep_enabled", before.WorkTempStaleSweepEnabled, after.WorkTempStaleSweepEnabled, v => v ? 1 : 0);
        Compare("failure_cleanup_enabled", before.FailureCleanupEnabled, after.FailureCleanupEnabled, v => v ? 1 : 0);
        Compare("keep_failed_work_files", before.KeepFailedWorkFiles, after.KeepFailedWorkFiles, v => v ? 1 : 0);
        Compare("file_log_retention_days", before.FileLogRetentionDays, after.FileLogRetentionDays, v => v);
        Compare("verbose_detection_logging", before.VerboseDetectionLogging, after.VerboseDetectionLogging, v => v ? 1 : 0);
        Compare("min_file_age_seconds", before.MinFileAgeSeconds, after.MinFileAgeSeconds, v => v);
        Compare("refiner_min_input_file_size_mb", before.RefinerMinInputFileSizeMb, after.RefinerMinInputFileSizeMb, v => v);
        Compare("minimum_free_disk_space_mb", before.MinimumFreeDiskSpaceMb, after.MinimumFreeDiskSpaceMb, v => v);
        Compare("movie_schedule_enabled", before.MovieScheduleEnabled, after.MovieScheduleEnabled, v => v ? 1 : 0);
        Compare("movie_schedule_hours_limited", before.MovieScheduleHoursLimited, after.MovieScheduleHoursLimited, v => v ? 1 : 0);
        Compare("movie_schedule_days", before.MovieScheduleDays, after.MovieScheduleDays, v => v);
        Compare("movie_schedule_start", before.MovieScheduleStart, after.MovieScheduleStart, v => v);
        Compare("movie_schedule_end", before.MovieScheduleEnd, after.MovieScheduleEnd, v => v);
        Compare("tv_schedule_enabled", before.TvScheduleEnabled, after.TvScheduleEnabled, v => v ? 1 : 0);
        Compare("tv_schedule_hours_limited", before.TvScheduleHoursLimited, after.TvScheduleHoursLimited, v => v ? 1 : 0);
        Compare("tv_schedule_days", before.TvScheduleDays, after.TvScheduleDays, v => v);
        Compare("tv_schedule_start", before.TvScheduleStart, after.TvScheduleStart, v => v);
        Compare("tv_schedule_end", before.TvScheduleEnd, after.TvScheduleEnd, v => v);
        if (sets.Count == 0)
        {
            return;
        }

        sets.Add("updated_at=CURRENT_TIMESTAMP");
        await uow.ExecuteAsync($"UPDATE refiner_operator_settings SET {string.Join(", ", sets)} WHERE id = 1", [.. parameters]).ConfigureAwait(false);
    }

    private static RefinerOperatorSettingsRecord Read(SqliteDataReader reader) => new()
    {
        MaxConcurrentFiles = SqliteValues.GetInt64(reader, 0),
        RunnerCapacity = SqliteValues.GetInt64(reader, 1),
        RunnerCostSd = SqliteValues.GetInt64(reader, 2),
        RunnerCost720P = SqliteValues.GetInt64(reader, 3),
        RunnerCost1080P = SqliteValues.GetInt64(reader, 4),
        RunnerCost4K = SqliteValues.GetInt64(reader, 5),
        RunnerCostUndetermined = SqliteValues.GetInt64(reader, 6),
        WorkTempStaleSweepEnabled = SqliteValues.GetBool(reader, 7),
        FailureCleanupEnabled = SqliteValues.GetBool(reader, 8),
        KeepFailedWorkFiles = SqliteValues.GetBool(reader, 9),
        FileLogRetentionDays = SqliteValues.GetInt64(reader, 10),
        VerboseDetectionLogging = SqliteValues.GetBool(reader, 11),
        MinFileAgeSeconds = SqliteValues.GetInt64(reader, 12),
        RefinerMinInputFileSizeMb = SqliteValues.GetInt64(reader, 13),
        MinimumFreeDiskSpaceMb = SqliteValues.GetInt64(reader, 14),
        MovieScheduleEnabled = SqliteValues.GetBool(reader, 15),
        MovieScheduleHoursLimited = SqliteValues.GetBool(reader, 16),
        MovieScheduleDays = SqliteValues.GetString(reader, 17),
        MovieScheduleStart = SqliteValues.GetString(reader, 18),
        MovieScheduleEnd = SqliteValues.GetString(reader, 19),
        TvScheduleEnabled = SqliteValues.GetBool(reader, 20),
        TvScheduleHoursLimited = SqliteValues.GetBool(reader, 21),
        TvScheduleDays = SqliteValues.GetString(reader, 22),
        TvScheduleStart = SqliteValues.GetString(reader, 23),
        TvScheduleEnd = SqliteValues.GetString(reader, 24),
        UpdatedAt = SqliteValues.GetDateTime(reader, 25),
    };
}
