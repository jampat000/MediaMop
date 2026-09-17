using System.Globalization;
using System.Numerics;
using System.Text;
using Weir.Core.Json;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>
/// The Python text behaviour the ffmpeg layer depends on: <c>format(x, ".1f")</c>, <c>str.splitlines()</c>,
/// <c>bytes.decode("utf-8", "replace")</c>, subprocess newline translation, code-point slicing and the
/// messages <c>subprocess.TimeoutExpired</c> prints.
/// </summary>
internal static class PyText
{
    private static readonly UTF8Encoding Utf8Replace = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: false);

    /// <summary><c>t[:max_chars] + "…(truncated)"</c> when longer than <paramref name="maxChars"/>.</summary>
    public static string Clip(string text, int maxChars) =>
        PyStrings.Length(text) > maxChars ? PyStrings.Slice(text, maxChars) + "…(truncated)" : text;

    /// <summary><c>bytes.decode("utf-8", errors="replace")</c>.</summary>
    public static string DecodeUtf8(ReadOnlySpan<byte> bytes)
    {
        var text = Utf8Replace.GetString(bytes);
        // Python drops a leading BOM only for the utf-8-sig codec; "utf-8" keeps it, and so does GetString.
        return text;
    }

    /// <summary>What <c>subprocess.run(..., text=True)</c> hands back: decoded, then <c>\r\n</c> and <c>\r</c> become <c>\n</c>.</summary>
    public static string TranslateNewlines(string text) =>
        text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n');

    /// <summary><c>str.splitlines()</c>, without keeping the line ends.</summary>
    public static List<string> SplitLines(string text)
    {
        var lines = new List<string>();
        var start = 0;
        var i = 0;
        while (i < text.Length)
        {
            var c = text[i];
            if (IsLineBoundary(c))
            {
                lines.Add(text[start..i]);
                i += c == '\r' && i + 1 < text.Length && text[i + 1] == '\n' ? 2 : 1;
                start = i;
            }
            else
            {
                i++;
            }
        }

        if (start < text.Length)
        {
            lines.Add(text[start..]);
        }

        return lines;
    }

    private const char LineSeparator = (char)0x2028;

    private const char ParagraphSeparator = (char)0x2029;

    private static bool IsLineBoundary(char c) =>
        c is '\n' or '\r' or '\v' or '\f' or (char)0x1c or (char)0x1d or (char)0x1e or (char)0x85 or LineSeparator or ParagraphSeparator;

    /// <summary><c>format(value, ".{decimals}f")</c>: exact decimal expansion, ties to even.</summary>
    public static string FormatFixed(double value, int decimals)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(decimals);
        if (double.IsNaN(value))
        {
            return "nan";
        }

        if (double.IsInfinity(value))
        {
            return value > 0 ? "inf" : "-inf";
        }

        var negative = double.IsNegative(value);
        var bits = BitConverter.DoubleToInt64Bits(Math.Abs(value));
        var exponentBits = (int)((bits >> 52) & 0x7FF);
        var fraction = bits & 0xFFFFFFFFFFFFFL;
        BigInteger mantissa;
        int exponent;
        if (exponentBits == 0)
        {
            mantissa = fraction;
            exponent = -1074;
        }
        else
        {
            mantissa = fraction | (1L << 52);
            exponent = exponentBits - 1075;
        }

        // |value| * 10^decimals = numerator / denominator, exactly.
        var numerator = mantissa * BigInteger.Pow(10, decimals);
        var denominator = BigInteger.One;
        if (exponent >= 0)
        {
            numerator <<= exponent;
        }
        else
        {
            denominator <<= -exponent;
        }

        var quotient = BigInteger.DivRem(numerator, denominator, out var remainder);
        var twice = remainder * 2;
        if (twice > denominator || (twice == denominator && !quotient.IsEven))
        {
            quotient += 1;
        }

        var digits = quotient.ToString(CultureInfo.InvariantCulture);
        if (decimals > 0)
        {
            digits = digits.PadLeft(decimals + 1, '0');
            digits = digits[..^decimals] + "." + digits[^decimals..];
        }

        return (negative ? "-" : string.Empty) + digits;
    }

    /// <summary><c>str(subprocess.TimeoutExpired(cmd=argv, timeout=...))</c>.</summary>
    public static string TimeoutExpiredMessage(IEnumerable<string> argv, string timeoutText) =>
        $"Command '{ListRepr(argv)}' timed out after {timeoutText} seconds";

    /// <summary><c>str(list_of_str)</c>.</summary>
    public static string ListRepr(IEnumerable<string> items) => "[" + string.Join(", ", items.Select(Py.Repr)) + "]";

    /// <summary><c>str(int)</c> or <c>str(float)</c> for a timeout as the reference passes it.</summary>
    public static string NumberText(double value, bool isFloat) =>
        isFloat ? PyConvert.FloatRepr(value) : ((long)value).ToString(CultureInfo.InvariantCulture);
}
