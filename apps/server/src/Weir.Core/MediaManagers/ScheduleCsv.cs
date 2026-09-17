using System.Globalization;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>Search-lane schedule fields (port of <c>schedule_csv_validate</c>).</summary>
public static class ScheduleCsv
{
    /// <summary><c>validate_schedule_days_csv</c>. Throws <see cref="PyValueErrorException"/> with the operator's sentence.</summary>
    public static string ValidateScheduleDaysCsv(string? raw)
    {
        var text = PyStrings.Strip(raw ?? string.Empty);
        if (text.Length == 0)
        {
            return string.Empty;
        }

        var tokens = text.Split(',').Select(PyStrings.Strip).Where(t => t.Length > 0).ToList();
        if (tokens.Any(token => !ScheduleGrid.DayNames.Contains(token)))
        {
            throw new PyValueErrorException("Days must be written like Mon, Tue, Wed with commas between them.");
        }

        return string.Join(',', tokens);
    }

    /// <summary><c>normalize_hhmm</c>. Throws <see cref="PyValueErrorException"/> for a time it cannot read.</summary>
    public static string NormalizeHhmm(string? raw, string fallback)
    {
        var text = PyStrings.Strip(raw ?? string.Empty);
        if (text.Length == 0)
        {
            return fallback;
        }

        var parts = text.Split(':');
        if (parts.Length != 2)
        {
            throw new PyValueErrorException("Times must look like 09:30 (hour and minute).");
        }

        if (!PythonCompat.TryParseInt(PyStrings.Strip(parts[0]), out var hour) || !PythonCompat.TryParseInt(PyStrings.Strip(parts[1]), out var minute))
        {
            throw new PyValueErrorException("Times must look like 09:30 (hour and minute).");
        }

        if (hour is < 0 or > 23 || minute is < 0 or > 59)
        {
            throw new PyValueErrorException("Hour must be 0–23 and minute must be 0–59.");
        }

        return hour.ToString("00", CultureInfo.InvariantCulture) + ":" + minute.ToString("00", CultureInfo.InvariantCulture);
    }
}
