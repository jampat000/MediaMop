using System.Globalization;
using System.Text;
using System.Text.Json;
using Weir.Core.Jobs;

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
        JobQueueRules.PythonIsoFormat(JobQueueRules.ToMicroseconds(value.ToUniversalTime()), ' ');

    /// <summary>The SQLAlchemy SQLite <c>DATETIME</c> storage shape, for values written through the ORM.</summary>
    public static string Orm(DateTimeOffset value)
    {
        var utc = JobQueueRules.ToMicroseconds(value.ToUniversalTime());
        var microseconds = (utc.Ticks % TimeSpan.TicksPerSecond) / 10;
        return utc.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) + "." +
               microseconds.ToString("D6", CultureInfo.InvariantCulture);
    }

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

/// <summary>
/// <c>json.dumps(value, separators=(",", ":"))</c>: compact, keys in insertion order, and non-ASCII
/// escaped as <c>\uXXXX</c> (<c>ensure_ascii=True</c>).
/// </summary>
public sealed class PythonJsonObject
{
    private readonly List<(string Key, string Json)> _members = [];

    public PythonJsonObject Add(string key, string? value)
    {
        _members.Add((key, value is null ? "null" : PythonJson.Quote(value)));
        return this;
    }

    public PythonJsonObject Add(string key, long value)
    {
        _members.Add((key, value.ToString(CultureInfo.InvariantCulture)));
        return this;
    }

    public PythonJsonObject Add(string key, bool value)
    {
        _members.Add((key, value ? "true" : "false"));
        return this;
    }

    /// <summary>A value copied from parsed JSON, re-serialised the way Python would.</summary>
    public PythonJsonObject AddRaw(string key, JsonElement value)
    {
        _members.Add((key, PythonJson.Element(value)));
        return this;
    }

    public override string ToString() =>
        "{" + string.Join(",", _members.Select(member => PythonJson.Quote(member.Key) + ":" + member.Json)) + "}";
}

/// <summary>Python's JSON encoder for the scalar shapes the queue writes.</summary>
public static class PythonJson
{
    public static string Quote(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        var builder = new StringBuilder(value.Length + 2);
        builder.Append('"');
        foreach (var c in value)
        {
            switch (c)
            {
                case '"':
                    builder.Append("\\\"");
                    break;
                case '\\':
                    builder.Append("\\\\");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                case '\t':
                    builder.Append("\\t");
                    break;
                case '\b':
                    builder.Append("\\b");
                    break;
                case '\f':
                    builder.Append("\\f");
                    break;
                default:
                    if (c < 0x20 || c > 0x7E)
                    {
                        builder.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        builder.Append(c);
                    }

                    break;
            }
        }

        return builder.Append('"').ToString();
    }

    public static string Element(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => Quote(value.GetString()!),
        JsonValueKind.True => "true",
        JsonValueKind.False => "false",
        JsonValueKind.Null => "null",
        JsonValueKind.Number => value.GetRawText(),
        JsonValueKind.Object => "{" + string.Join(",", value.EnumerateObject().Select(p => Quote(p.Name) + ":" + Element(p.Value))) + "}",
        JsonValueKind.Array => "[" + string.Join(",", value.EnumerateArray().Select(Element)) + "]",
        _ => "null",
    };
}
