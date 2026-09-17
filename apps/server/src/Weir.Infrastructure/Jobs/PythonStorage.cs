using System.Globalization;
using Weir.Core.Time;

namespace Weir.Infrastructure.Jobs;

/// <summary>
/// Timestamps exactly as the Python backend writes them into SQLite, so either backend can read,
/// compare and claim rows the other wrote.
/// </summary>
/// <remarks>
/// Python stores time in two shapes. Values bound into raw SQL (the claim's <c>:now</c> and
/// <c>:lease_exp</c>) go through its <c>sqlite3</c> adapter, <c>isoformat(sep=" ")</c>:
/// <c>2026-04-10 13:00:00.123456+00:00</c>, microseconds omitted when zero. Values written through
/// the ORM (<c>not_before</c>, prune cutoffs, <c>processing_paused_until</c>) drop the offset and always
/// carry microseconds: <c>2026-04-10 12:00:30.123456</c>. The claim compares them as text, which is
/// reproduced by writing the same text.
/// </remarks>
public static class PythonTimestamps
{
    /// <summary>The <c>sqlite3</c> adapter shape, for values bound into raw SQL.</summary>
    public static string Adapter(DateTimeOffset value) =>
        PyDateTime.FromDateTimeOffset(value.ToUniversalTime()).IsoFormat(' ');

    /// <summary>The SQLAlchemy SQLite <c>DATETIME</c> storage shape, for values written through the ORM.</summary>
    public static string Orm(DateTimeOffset value) => PyDateTime.FromDateTimeOffset(value.ToUniversalTime()).ToSqlite();

    /// <summary>Read any of the stored shapes (including <c>CURRENT_TIMESTAMP</c>); a value without an offset is UTC.</summary>
    public static DateTimeOffset? Parse(object? value)
    {
        if (value is null or DBNull)
        {
            return null;
        }

        var text = Convert.ToString(value, CultureInfo.InvariantCulture)!.Trim();
        if (text.Length == 0)
        {
            return null;
        }

        var styles = DateTimeStyles.AllowWhiteSpaces;
        var hasOffset = text.Length > 19 && (text.EndsWith('Z') || text.LastIndexOfAny(['+', '-']) > 10);
        if (hasOffset)
        {
            return DateTimeOffset.Parse(text.Replace(' ', 'T'), CultureInfo.InvariantCulture, styles);
        }

        var parsed = DateTime.Parse(text.Replace(' ', 'T'), CultureInfo.InvariantCulture, styles | DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal);
        return new DateTimeOffset(DateTime.SpecifyKind(parsed, DateTimeKind.Utc));
    }
}
