using Weir.Core.Time;

namespace Weir.Core.Jobs;

/// <summary>The stored schedule grid is not a usable schedule (<c>ScheduleGridError</c>).</summary>
public sealed class ScheduleGridException : Exception
{
    public ScheduleGridException()
    {
    }

    public ScheduleGridException(string message)
        : base(message)
    {
    }

    public ScheduleGridException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// A 7x24 schedule at 15-minute resolution stored as 672 <c>0</c>/<c>1</c> characters (port of
/// <c>weir.refiner.refiner_schedule_grid</c>). Day 0 is Monday. An empty grid means no restriction.
/// </summary>
public static class ScheduleGrid
{
    public const int SlotsPerHour = 4;
    public const int SlotsPerDay = 24 * SlotsPerHour;
    public const int SlotsPerWeek = 7 * SlotsPerDay;
    public const int SlotMinutes = 60 / SlotsPerHour;

    /// <summary>Monday-first day names, as <c>schedule_wall_clock.DAY_NAMES</c>.</summary>
    public static readonly IReadOnlyList<string> DayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    /// <summary><c>normalize_grid</c>: validate and canonicalise stored grid text.</summary>
    public static string Normalize(string? raw)
    {
        var text = PythonStrip(raw ?? string.Empty);
        if (text.Length == 0)
        {
            return string.Empty;
        }

        if (text.Length != SlotsPerWeek)
        {
            throw new ScheduleGridException(
                $"A schedule grid must be exactly {SlotsPerWeek} characters " +
                $"(7 days x {SlotsPerDay} quarter-hours); this one has {text.Length}.");
        }

        if (text.Any(c => c is not ('0' or '1')))
        {
            throw new ScheduleGridException("A schedule grid may only contain 0 and 1.");
        }

        return text;
    }

    /// <summary><c>slot_index</c>: Monday is weekday 0.</summary>
    public static int SlotIndex(int weekday, int hour, int minute) =>
        (PythonMod(weekday, 7) * SlotsPerDay) + (hour * SlotsPerHour) + PythonFloorDiv(minute, SlotMinutes);

    /// <summary>
    /// <c>grid_allows</c>: an empty grid allows everything, and so does one that fails to parse, so a
    /// display bug never becomes a stoppage.
    /// </summary>
    public static bool Allows(string? grid, string? timezoneName, DateTimeOffset now)
    {
        string text;
        try
        {
            text = Normalize(grid);
        }
        catch (ScheduleGridException)
        {
            return true;
        }

        if (text.Length == 0)
        {
            return true;
        }

        var local = TimeZones.ToLocal(now, timezoneName);
        return text[SlotIndex(PythonWeekday(local.DayOfWeek), local.Hour, local.Minute)] == '1';
    }

    /// <summary><c>grid_from_days_and_times</c>: the grid a day/start/end window describes, or no restriction.</summary>
    public static string FromDaysAndTimes(string? days, string? start, string? end)
    {
        var wanted = (days ?? string.Empty).Split(',')
            .Where(d => PythonStrip(d).Length > 0)
            .Select(d => Prefix3(PythonStrip(d).ToLowerInvariant()))
            .ToHashSet(StringComparer.Ordinal);
        if (wanted.Count == 0)
        {
            return string.Empty;
        }

        if (!TryParseHourMinute(string.IsNullOrEmpty(start) ? "00:00" : start, out var startHour, out var startMinute) ||
            !TryParseHourMinute(string.IsNullOrEmpty(end) ? "23:59" : end, out var endHour, out var endMinute))
        {
            return string.Empty;
        }

        var startSlot = (startHour * SlotsPerHour) + PythonFloorDiv(startMinute, SlotMinutes);
        var endSlot = (endHour * SlotsPerHour) + PythonFloorDiv(endMinute, SlotMinutes);
        if (startSlot is < 0 or >= SlotsPerDay || endSlot is < 0 or >= SlotsPerDay)
        {
            return string.Empty;
        }

        var slots = Enumerable.Repeat('0', SlotsPerWeek).ToArray();
        for (var dayIndex = 0; dayIndex < DayNames.Count; dayIndex++)
        {
            if (!wanted.Contains(Prefix3(DayNames[dayIndex].ToLowerInvariant())))
            {
                continue;
            }

            var baseSlot = dayIndex * SlotsPerDay;
            if (startSlot <= endSlot)
            {
                for (var s = startSlot; s <= endSlot; s++)
                {
                    slots[baseSlot + s] = '1';
                }
            }
            else
            {
                for (var s = startSlot; s < SlotsPerDay; s++)
                {
                    slots[baseSlot + s] = '1';
                }

                for (var s = 0; s <= endSlot; s++)
                {
                    slots[(((dayIndex + 1) % 7) * SlotsPerDay) + s] = '1';
                }
            }
        }

        return new string(slots);
    }

    /// <summary><c>next_open_slot</c>: when the grid next allows work, or null if never or unrestricted.</summary>
    public static DateTimeOffset? NextOpenSlot(string? grid, string? timezoneName, DateTimeOffset now)
    {
        string text;
        try
        {
            text = Normalize(grid);
        }
        catch (ScheduleGridException)
        {
            return null;
        }

        if (text.Length == 0 || !text.Contains('1', StringComparison.Ordinal))
        {
            return null;
        }

        var zone = TimeZones.Find(timezoneName);
        var local = TimeZoneInfo.ConvertTime(now, zone);
        var start = SlotIndex(PythonWeekday(local.DayOfWeek), local.Hour, local.Minute);
        for (var ahead = 1; ahead <= SlotsPerWeek; ahead++)
        {
            if (text[(start + ahead) % SlotsPerWeek] != '1')
            {
                continue;
            }

            // Python adds minutes to the *wall clock* (aware datetime arithmetic keeps the tzinfo and
            // ignores DST transitions), then converts back to UTC with the offset of the result.
            var aligned = new DateTime(local.Year, local.Month, local.Day, local.Hour, (local.Minute / SlotMinutes) * SlotMinutes, 0, DateTimeKind.Unspecified);
            var wall = aligned.AddMinutes(SlotMinutes * ahead);
            return TimeZones.FromWallClock(wall, zone).ToUniversalTime();
        }

        return null;
    }

    /// <summary><c>datetime.weekday()</c>: Monday is 0.</summary>
    public static int PythonWeekday(DayOfWeek day) => ((int)day + 6) % 7;

    internal static string PythonStrip(string value) => value.Trim();

    private static string Prefix3(string value) => value.Length <= 3 ? value : value[..3];

    private static bool TryParseHourMinute(string text, out int hour, out int minute)
    {
        hour = 0;
        minute = 0;
        // Python: (int(x) for x in text.split(":", 1)) unpacked into exactly two values.
        var parts = text.Split(':', 2);
        return parts.Length == 2 &&
               TryPythonInt(parts[0], out hour) &&
               TryPythonInt(parts[1], out minute);
    }

    internal static bool TryPythonInt(string raw, out int value)
    {
        value = 0;
        if (!PythonCompatInt(raw, out var parsed) || parsed is < int.MinValue or > int.MaxValue)
        {
            return false;
        }

        value = (int)parsed;
        return true;
    }

    private static bool PythonCompatInt(string raw, out long value) =>
        Configuration.PythonCompat.TryParseInt(raw, out value);

    private static int PythonMod(int value, int divisor) => ((value % divisor) + divisor) % divisor;

    private static int PythonFloorDiv(int value, int divisor) => (int)Math.Floor(value / (double)divisor);
}
