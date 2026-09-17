using TimeZoneConverter;

namespace Weir.Core.Time;

/// <summary>Looks up IANA time zone names the way <c>zoneinfo.ZoneInfo</c> does.</summary>
public interface ITimeZoneResolver
{
    bool TryFind(string name, out TimeZoneInfo zone);
}

/// <summary>The resolver every server component uses: <see cref="TimeZones.TryFind"/>.</summary>
public sealed class IanaTimeZoneResolver : ITimeZoneResolver
{
    public bool TryFind(string name, out TimeZoneInfo zone) => TimeZones.TryFind(name, out zone);
}

/// <summary>IANA time zones as Python's <c>ZoneInfo</c> (with the <c>tzdata</c> package) resolves them.</summary>
/// <remarks>
/// Weir runs with invariant globalization, and on Windows that leaves .NET unable to convert an IANA
/// id (the registry holds only Windows ids and the conversion needs ICU). TimeZoneConverter carries the
/// CLDR mapping and the IANA links, so the same names resolve on every platform. Only IANA names are
/// accepted, as with <c>ZoneInfo</c>: a Windows id such as <c>Eastern Standard Time</c> is unknown.
/// </remarks>
public static class TimeZones
{
    /// <summary><c>ZoneInfo(name)</c>: false where Python raises.</summary>
    public static bool TryFind(string? name, out TimeZoneInfo zone)
    {
        zone = TimeZoneInfo.Utc;
        if (string.IsNullOrEmpty(name) || name.Contains('\0', StringComparison.Ordinal) || !TZConvert.KnownIanaTimeZoneNames.Contains(name))
        {
            return false;
        }

        if (TZConvert.TryGetTimeZoneInfo(name, out var found))
        {
            zone = found;
            return true;
        }

        return false;
    }

    /// <summary>
    /// <c>ZoneInfo((name or "UTC").strip() or "UTC")</c>, falling back to UTC where that raises, as the
    /// schedule code does.
    /// </summary>
    public static TimeZoneInfo Find(string? name)
    {
        var id = (name ?? "UTC").Trim();
        if (id.Length == 0 || id == "UTC")
        {
            return TimeZoneInfo.Utc;
        }

        return TryFind(id, out var zone) ? zone : TimeZoneInfo.Utc;
    }

    public static DateTimeOffset ToLocal(DateTimeOffset now, string? name) => TimeZoneInfo.ConvertTime(now, Find(name));

    /// <summary>
    /// A wall-clock time in <paramref name="zone"/> as an instant. For an ambiguous or skipped time
    /// this takes the first offset (Python's <c>fold=0</c>).
    /// </summary>
    public static DateTimeOffset FromWallClock(DateTime wall, TimeZoneInfo zone)
    {
        ArgumentNullException.ThrowIfNull(zone);
        TimeSpan offset;
        if (zone.IsAmbiguousTime(wall))
        {
            offset = zone.GetAmbiguousTimeOffsets(wall).Max();
        }
        else if (zone.IsInvalidTime(wall))
        {
            offset = zone.GetUtcOffset(wall.AddHours(-1));
        }
        else
        {
            offset = zone.GetUtcOffset(wall);
        }

        return new DateTimeOffset(wall, offset);
    }
}
