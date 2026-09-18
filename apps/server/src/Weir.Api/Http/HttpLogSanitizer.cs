using System.Text;

namespace Weir.Api.Http;

/// <summary>
/// Neutralises control characters in a request-derived value before it reaches a text log line.
/// </summary>
/// <remarks>
/// ASP.NET Core decodes the request path (and headers, query values, etc.) before handler code ever sees
/// them, so a request to <c>/foo%0Afake-log-line</c> hands a handler a <c>Path.Value</c> that contains a
/// real line feed. Writing that straight into a text log sink forges an extra log line (CWE-117,
/// <c>cs/log-forging</c>). <see cref="Sanitize"/> replaces every control character with a visible escape,
/// so the value stays readable in the log but can never start a new line or otherwise confuse a log
/// reader. It does not change the value for any purpose other than logging — callers must not persist or
/// return the sanitized text as if it were the original.
/// </remarks>
public static class HttpLogSanitizer
{
    private const char LineSeparator = (char)0x2028;
    private const char ParagraphSeparator = (char)0x2029;
    private const char NextLine = (char)0x0085;
    private const char Delete = (char)0x007f;

    /// <summary>
    /// <paramref name="value"/> with every C0 control character, DEL, and the Unicode line/paragraph
    /// separators some consoles and log viewers treat as newlines, replaced by a printable escape
    /// (<c>\r</c>, <c>\n</c>, <c>\t</c> or <c>\xHH</c> / <c>\uHHHH</c>). Everything else passes through
    /// unchanged, including non-ASCII text.
    /// </summary>
    public static string Sanitize(string value)
    {
        ArgumentNullException.ThrowIfNull(value);

        StringBuilder? builder = null;
        for (var i = 0; i < value.Length; i++)
        {
            var c = value[i];
            var escape = Escape(c);
            if (escape is null)
            {
                builder?.Append(c);
                continue;
            }

            builder ??= new StringBuilder(value.Length + 8).Append(value, 0, i);
            builder.Append(escape);
        }

        return builder?.ToString() ?? value;
    }

    private static string? Escape(char c) => c switch
    {
        '\r' => "\\r",
        '\n' => "\\n",
        '\t' => "\\t",
        LineSeparator => "\\u2028",
        ParagraphSeparator => "\\u2029",
        NextLine => "\\u0085",
        < ' ' or Delete => "\\x" + ((int)c).ToString("x2", System.Globalization.CultureInfo.InvariantCulture),
        _ => null,
    };
}
