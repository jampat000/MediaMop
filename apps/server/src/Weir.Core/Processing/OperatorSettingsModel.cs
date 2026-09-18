using Weir.Core.Jobs;
using Weir.Core.Time;

namespace Weir.Core.Processing;

/// <summary>The singleton <c>operator_settings</c> row (id = 1).</summary>
public sealed record ProcessingOperatorSettingsRecord
{
    public long MaxConcurrentFiles { get; init; } = 1;
    public long RunnerCapacity { get; init; } = 4;
    public long RunnerCostSd { get; init; }
    public long RunnerCost720P { get; init; }
    public long RunnerCost1080P { get; init; } = 1;
    public long RunnerCost4K { get; init; } = 1;
    public long RunnerCostUndetermined { get; init; }
    public bool WorkTempStaleSweepEnabled { get; init; } = true;
    public bool FailureCleanupEnabled { get; init; }
    public bool KeepFailedWorkFiles { get; init; }
    public long FileLogRetentionDays { get; init; } = 90;
    public bool VerboseDetectionLogging { get; init; }
    public long MinFileAgeSeconds { get; init; } = 60;
    public long ProcessingMinInputFileSizeMb { get; init; } = 50;
    public long MinimumFreeDiskSpaceMb { get; init; } = 5120;
    public bool MovieScheduleEnabled { get; init; } = true;
    public bool MovieScheduleHoursLimited { get; init; }
    public string MovieScheduleDays { get; init; } = string.Empty;
    public string MovieScheduleStart { get; init; } = "00:00";
    public string MovieScheduleEnd { get; init; } = "23:59";
    public bool TvScheduleEnabled { get; init; } = true;
    public bool TvScheduleHoursLimited { get; init; }
    public string TvScheduleDays { get; init; } = string.Empty;
    public string TvScheduleStart { get; init; } = "00:00";
    public string TvScheduleEnd { get; init; } = "23:59";
    public PyDateTime UpdatedAt { get; init; }
}

/// <summary>A schedule-window setting is not usable (<c>ValueError</c> from <c>schedule_csv_validate</c>).</summary>
public sealed class ScheduleWindowException : Exception
{
    public ScheduleWindowException(string message)
        : base(message)
    {
    }
}

/// <summary>
/// Weekday-CSV and HH:MM validation, and wall-clock window evaluation, shared by Processing's Movies/TV
/// schedule pair (port of <c>weir.platform.media_managers.schedule_csv_validate</c> and
/// <c>schedule_wall_clock</c> — small enough to live with Processing rather than wait on the media-manager port).
/// </summary>
public static class ScheduleWindow
{
    /// <summary><c>validate_schedule_days_csv</c>.</summary>
    public static string ValidateDaysCsv(string? raw)
    {
        var text = (raw ?? string.Empty).Trim();
        if (text.Length == 0)
        {
            return string.Empty;
        }

        var tokens = text.Split(',').Select(t => t.Trim()).Where(t => t.Length > 0).ToList();
        if (tokens.Any(t => !ScheduleGrid.DayNames.Contains(t, StringComparer.Ordinal)))
        {
            throw new ScheduleWindowException("Days must be written like Mon, Tue, Wed with commas between them.");
        }

        return string.Join(",", tokens);
    }

    /// <summary><c>normalize_hhmm</c>.</summary>
    public static string NormalizeHhmm(string? raw, string fallback)
    {
        var text = (raw ?? string.Empty).Trim();
        if (text.Length == 0)
        {
            return fallback;
        }

        var parts = text.Split(':');
        if (parts.Length != 2 || !int.TryParse(parts[0], out var hour) || !int.TryParse(parts[1], out var minute) ||
            hour is < 0 or > 23 || minute is < 0 or > 59)
        {
            throw new ScheduleWindowException("Times must look like 09:30 (hour and minute).");
        }

        return $"{hour:D2}:{minute:D2}";
    }

    private static TimeOnly ParseHhmmOrDefault(string? raw, TimeOnly fallback)
    {
        var parts = (raw ?? string.Empty).Trim().Split(':');
        if (parts.Length == 2 && int.TryParse(parts[0], out var hour) && int.TryParse(parts[1], out var minute) &&
            hour is >= 0 and <= 23 && minute is >= 0 and <= 59)
        {
            return new TimeOnly(hour, minute);
        }

        return fallback;
    }

    /// <summary><c>schedule_time_window_active</c>: true when the current wall clock is inside the window.</summary>
    public static bool IsActive(bool scheduleEnabled, string? scheduleDays, string? scheduleStart, string? scheduleEnd, string? timezoneName, DateTimeOffset nowUtc, ITimeZoneResolver zones)
    {
        ArgumentNullException.ThrowIfNull(zones);
        if (!scheduleEnabled)
        {
            return true;
        }

        var zone = zones.TryFind((timezoneName ?? "UTC").Trim() is { Length: > 0 } name ? name : "UTC", out var found) ? found : TimeZoneInfo.Utc;
        var local = TimeZoneInfo.ConvertTime(nowUtc, zone);
        var day = ScheduleGrid.DayNames[ScheduleGrid.PythonWeekday(local.DayOfWeek)];
        var allowedDays = (scheduleDays ?? string.Empty).Trim() is { Length: > 0 } daysText
            ? daysText.Split(',').Select(t => t.Trim()).Where(t => ScheduleGrid.DayNames.Contains(t, StringComparer.Ordinal)).ToHashSet(StringComparer.Ordinal)
            : [];
        if (allowedDays.Count == 0)
        {
            allowedDays = [.. ScheduleGrid.DayNames];
        }

        if (!allowedDays.Contains(day))
        {
            return false;
        }

        var start = ParseHhmmOrDefault(scheduleStart, new TimeOnly(0, 0));
        var end = ParseHhmmOrDefault(scheduleEnd, new TimeOnly(23, 59));
        var current = new TimeOnly(local.Hour, local.Minute);
        return start <= end ? current >= start && current <= end : current >= start || current <= end;
    }
}

/// <summary>Clamping and normalization for <c>operator_settings</c> (port of the module-level helpers
/// in <c>operator_settings_service.py</c>).</summary>
public static class OperatorSettingsRules
{
    public static long ClampMaxConcurrentFiles(long raw) => Math.Clamp(raw, 1, 8);

    public static long ClampMinFileAgeSeconds(long raw) => Math.Clamp(raw, 0, 7 * 24 * 3600);

    public static long ClampSizeMb(long raw) => Math.Clamp(raw, 0, 1024 * 1024);

    public static long ClampRunnerCapacity(long raw) => Math.Clamp(raw, 1, 64);

    public static long ClampRunnerCost(long raw) => Math.Clamp(raw, 0, 64);

    public static long ClampFileLogRetentionDays(long raw) => Math.Clamp(raw, 0, 3650);
}
