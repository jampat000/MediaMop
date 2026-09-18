using System.Globalization;
using System.Text.RegularExpressions;

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

    // The C0/C1 control range (\p{Cc}: 0x00-0x1F and 0x7F-0x9F, so this already covers DEL and NEL) plus the
    // two Unicode line-breaking separators that are not themselves "Cc". A single Regex.Replace over this,
    // rather than a hand-rolled character loop, is also what lets static analysis (CodeQL's cs/log-forging
    // barrier recognition included) see this as removing the dangerous characters rather than just another
    // pass-through of tainted input.
    private static readonly Regex ControlCharacterPattern = new(
        "[\\p{Cc}" + LineSeparator + ParagraphSeparator + "]",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    /// <summary>
    /// <paramref name="value"/> with every C0/C1 control character, and the Unicode line/paragraph
    /// separators some consoles and log viewers treat as newlines, replaced by a printable escape
    /// (<c>\r</c>, <c>\n</c>, <c>\t</c> or <c>\xHH</c> / <c>\uHHHH</c>). Everything else passes through
    /// unchanged, including non-ASCII text.
    /// </summary>
    public static string Sanitize(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        return ControlCharacterPattern.Replace(value, EscapeMatch);
    }

    private static string EscapeMatch(Match match)
    {
        var c = match.Value[0];
        return c switch
        {
            '\r' => "\\r",
            '\n' => "\\n",
            '\t' => "\\t",
            LineSeparator => "\\u2028",
            ParagraphSeparator => "\\u2029",
            NextLine => "\\u0085",
            _ => "\\x" + ((int)c).ToString("x2", CultureInfo.InvariantCulture),
        };
    }
}
