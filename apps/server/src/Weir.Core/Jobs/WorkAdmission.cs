using System.Text.Json;
using Weir.Core.Settings;
using Weir.Core.Time;

namespace Weir.Core.Jobs;

/// <summary>Wall-clock schedule windows in an IANA zone (port of <c>schedule_wall_clock</c>).</summary>
public static class ScheduleWallClock
{
    /// <summary><c>schedule_time_window_active</c>.</summary>
    public static bool TimeWindowActive(
        bool scheduleEnabled,
        string? scheduleDays,
        string? scheduleStart,
        string? scheduleEnd,
        string? timezoneName,
        DateTimeOffset now)
    {
        if (!scheduleEnabled)
        {
            return true;
        }

        var local = TimeZones.ToLocal(now, timezoneName);
        var day = ScheduleGrid.DayNames[ScheduleGrid.PythonWeekday(local.DayOfWeek)];
        if (!ParseDays(scheduleDays).Contains(day))
        {
            return false;
        }

        var start = ParseHourMinute(scheduleStart, new TimeSpan(0, 0, 0));
        var end = ParseHourMinute(scheduleEnd, new TimeSpan(23, 59, 0));
        var current = new TimeSpan(local.Hour, local.Minute, 0);
        return start <= end ? start <= current && current <= end : current >= start || current <= end;
    }

    private static TimeSpan ParseHourMinute(string? text, TimeSpan fallback)
    {
        var parts = (text ?? string.Empty).Trim().Split(':');
        if (parts.Length != 2 ||
            !ScheduleGrid.TryPythonInt(parts[0], out var hour) ||
            !ScheduleGrid.TryPythonInt(parts[1], out var minute) ||
            hour is < 0 or > 23 || minute is < 0 or > 59)
        {
            return fallback;
        }

        return new TimeSpan(hour, minute, 0);
    }

    private static HashSet<string> ParseDays(string? text)
    {
        var trimmed = (text ?? string.Empty).Trim();
        if (trimmed.Length == 0)
        {
            return [];
        }

        var valid = trimmed.Split(',')
            .Select(token => token.Trim())
            .Where(token => token.Length > 0 && ScheduleGrid.DayNames.Contains(token))
            .ToHashSet(StringComparer.Ordinal);
        return valid.Count > 0 ? valid : [.. ScheduleGrid.DayNames];
    }
}

/// <summary>Total runner capacity and what each resolution class costs (port of <c>RunnerBudget</c>).</summary>
public sealed record RunnerBudget(int Capacity, IReadOnlyDictionary<string, int> Costs)
{
    /// <summary>The budget when the operator settings row does not exist.</summary>
    public static RunnerBudget Default { get; } = new(4, new Dictionary<string, int>(StringComparer.Ordinal));

    /// <summary><c>budget_from_settings</c>: zero capacity means the default of four, like Python's <c>or 4</c>.</summary>
    public static RunnerBudget FromSettings(long capacity, long costSd, long cost720p, long cost1080p, long cost4k, long costUndetermined) =>
        new(
            (int)Math.Clamp(capacity == 0 ? 4 : capacity, 1, int.MaxValue),
            new Dictionary<string, int>(StringComparer.Ordinal)
            {
                ["sd"] = NonNegative(costSd),
                ["720p"] = NonNegative(cost720p),
                ["1080p"] = NonNegative(cost1080p),
                ["4k"] = NonNegative(cost4k),
                ["undetermined"] = NonNegative(costUndetermined),
            });

    public int CostFor(string? resolutionClass)
    {
        var name = (resolutionClass ?? "undetermined").Trim().ToLowerInvariant();
        if (name.Length == 0)
        {
            name = "undetermined";
        }

        if (!Costs.ContainsKey(name))
        {
            name = "undetermined";
        }

        return Math.Max(0, Costs.TryGetValue(name, out var cost) ? cost : 0);
    }

    public int Available(long inUse) => (int)Math.Max(0, Capacity - Math.Max(0, inUse));

    private static int NonNegative(long value) => (int)Math.Clamp(value, 0, int.MaxValue);
}

/// <summary>The <c>suite_settings</c> fields admission reads.</summary>
public sealed record SuitePauseSettings(string? AppTimezone, bool ProcessingPaused, PyDateTime? ProcessingPausedUntil, bool ScanWhilePaused);

/// <summary>The <c>libraries</c> fields admission reads.</summary>
public sealed record LibraryAdmissionSnapshot(
    long Id,
    bool Enabled,
    bool ScheduleEnabled,
    string? ScheduleGrid,
    bool ScheduleHoursLimited,
    string? ScheduleDays,
    string? ScheduleStart,
    string? ScheduleEnd,
    long MaxConcurrentFiles);

/// <summary>A leased job as admission counts it.</summary>
public sealed record LeasedJobSnapshot(long RunnerCost, string? PayloadJson);

/// <summary>What a worker is allowed to pick up on this pass (port of <c>WorkAdmission</c>).</summary>
public sealed record WorkAdmission(
    PauseState Pause,
    IReadOnlySet<long> BlockedLibraryIds,
    string TimezoneName = "UTC",
    int AvailableUnits = 0,
    int Capacity = 0)
{
    public bool BlocksProcessing => Pause.Paused;

    public bool BlocksDetection => Pause.Paused && !Pause.ScanWhilePaused;

    public bool AllowsJobKind(string jobKind) =>
        !Pause.Paused || (WorkAdmissionRules.IsDetectionJobKind(jobKind) && Pause.ScanWhilePaused);
}

/// <summary>Pure rules of <c>weir.processing.processing_work_admission</c>.</summary>
public static class WorkAdmissionRules
{
    /// <summary>Detection job kinds keep running through a pause when "scan while paused" is on.</summary>
    public static readonly IReadOnlyList<string> DetectionJobKindPrefixes = ["processing.watched_folder.remux_scan_dispatch"];

    public static bool IsDetectionJobKind(string jobKind)
    {
        ArgumentNullException.ThrowIfNull(jobKind);
        return DetectionJobKindPrefixes.Any(prefix => jobKind.StartsWith(prefix, StringComparison.Ordinal));
    }

    /// <summary><c>library_window_open</c>: the grid wins when drawn, else the day/start/end trio.</summary>
    public static bool LibraryWindowOpen(LibraryAdmissionSnapshot library, string? timezoneName, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(library);
        if (!library.ScheduleEnabled)
        {
            return true;
        }

        var grid = (library.ScheduleGrid ?? string.Empty).Trim();
        if (grid.Length > 0)
        {
            return ScheduleGrid.Allows(grid, timezoneName, now);
        }

        if (!library.ScheduleHoursLimited)
        {
            return true;
        }

        return ScheduleWallClock.TimeWindowActive(
            scheduleEnabled: true,
            (library.ScheduleDays ?? string.Empty).Trim(),
            OrDefault(library.ScheduleStart, "00:00").Trim(),
            OrDefault(library.ScheduleEnd, "23:59").Trim(),
            timezoneName,
            now);
    }

    /// <summary><c>library_window_reopens_at</c>: only knowable from a grid.</summary>
    public static DateTimeOffset? LibraryWindowReopensAt(LibraryAdmissionSnapshot library, string? timezoneName, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(library);
        var grid = (library.ScheduleGrid ?? string.Empty).Trim();
        return grid.Length == 0 ? null : ScheduleGrid.NextOpenSlot(grid, timezoneName, now);
    }

    /// <summary>
    /// <c>evaluate_work_admission</c>: the pause, every library window and the runner budget, once per
    /// worker pass. <paramref name="libraries"/> must be ordered by id.
    /// </summary>
    public static WorkAdmission Evaluate(
        SuitePauseSettings? suite,
        RunnerBudget? budget,
        IEnumerable<LeasedJobSnapshot> leasedJobs,
        IEnumerable<LibraryAdmissionSnapshot> libraries,
        DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(leasedJobs);
        ArgumentNullException.ThrowIfNull(libraries);
        if (suite is null)
        {
            // #540 item 4: a missing suite_settings row must not starve every job kind of runner
            // capacity; nothing is running yet, so the whole default budget is free.
            return new WorkAdmission(
                new PauseState(false, null, ScanWhilePaused: true),
                new HashSet<long>(),
                AvailableUnits: RunnerBudget.Default.Available(0),
                Capacity: RunnerBudget.Default.Capacity);
        }

        var timezoneName = (suite.AppTimezone ?? "UTC").Trim();
        if (timezoneName.Length == 0)
        {
            timezoneName = "UTC";
        }

        var pause = PauseState.Resolve(suite.ProcessingPaused, suite.ProcessingPausedUntil, suite.ScanWhilePaused, now.UtcDateTime);
        var effectiveBudget = budget ?? RunnerBudget.Default;

        long unitsInUse = 0;
        var runningPerLibrary = new Dictionary<long, int>();
        foreach (var job in leasedJobs)
        {
            unitsInUse += Math.Max(0, job.RunnerCost);
            if (JobPayload.LibraryIdForAdmission(job.PayloadJson) is { } libraryId)
            {
                runningPerLibrary[libraryId] = runningPerLibrary.GetValueOrDefault(libraryId) + 1;
            }
        }

        var blocked = new HashSet<long>();
        foreach (var library in libraries)
        {
            if (!library.Enabled || !LibraryWindowOpen(library, timezoneName, now))
            {
                blocked.Add(library.Id);
                continue;
            }

            // A per-library cap so one library cannot occupy the whole budget and starve the others.
            var cap = Math.Max(1, library.MaxConcurrentFiles == 0 ? 1 : library.MaxConcurrentFiles);
            if (runningPerLibrary.GetValueOrDefault(library.Id) >= cap)
            {
                blocked.Add(library.Id);
            }
        }

        return new WorkAdmission(
            pause,
            blocked,
            timezoneName,
            effectiveBudget.Available(unitsInUse),
            effectiveBudget.Capacity);
    }

    private static string OrDefault(string? value, string fallback) => string.IsNullOrEmpty(value) ? fallback : value;
}

/// <summary>Reads job payload fields the way the Python worker does.</summary>
public static class JobPayload
{
    /// <summary>
    /// <c>_library_id_of</c>: the payload's <c>library_id</c> when it is a JSON integer, not a boolean.
    /// </summary>
    /// <remarks>
    /// #540 item 5: Python's <c>isinstance(value, int)</c> also accepts a bool (a bool is an int in
    /// Python), so <c>library_id: true</c> counted as library 1 when tallying jobs running per
    /// library. Fixed here to reject booleans and only accept a genuine JSON integer literal.
    /// </remarks>
    public static long? LibraryIdForAdmission(string? payloadJson) => StrictInteger(ParseObject(payloadJson), "library_id");

    /// <summary>A payload object, or null when the text is empty, invalid or not an object.</summary>
    public static JsonElement? ParseObject(string? payloadJson)
    {
        var raw = (payloadJson ?? string.Empty).Trim();
        if (raw.Length == 0)
        {
            return null;
        }

        try
        {
            using var document = JsonDocument.Parse(raw);
            return document.RootElement.ValueKind == JsonValueKind.Object ? document.RootElement.Clone() : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>A string property, or null when absent or not a string.</summary>
    public static string? StringProperty(JsonElement? payload, string name) =>
        payload is { } element && element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    /// <summary>
    /// An integer property that is not a boolean (<c>isinstance(x, int) and not isinstance(x, bool)</c>
    /// as the activity classifier reads it), or null.
    /// </summary>
    public static long? StrictInteger(JsonElement? payload, string name) =>
        payload is { } element && element.TryGetProperty(name, out var value) &&
        value.ValueKind == JsonValueKind.Number && IsIntegerLiteral(value) && value.TryGetInt64(out var number)
            ? number
            : null;

    /// <summary>An integer property where a JSON boolean also counts (plain <c>isinstance(x, int)</c>).</summary>
    public static long? LooseInteger(JsonElement? payload, string name)
    {
        if (payload is not { } element || !element.TryGetProperty(name, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => 1,
            JsonValueKind.False => 0,
            JsonValueKind.Number when IsIntegerLiteral(value) && value.TryGetInt64(out var number) => number,
            _ => null,
        };
    }

    /// <summary>Python's <c>json.loads</c> makes <c>1.0</c> a float, so only literals without a fraction or exponent are ints.</summary>
    private static bool IsIntegerLiteral(JsonElement value)
    {
        var text = value.GetRawText();
        return !text.Contains('.', StringComparison.Ordinal) && !text.Contains('e', StringComparison.Ordinal) && !text.Contains('E', StringComparison.Ordinal);
    }
}
