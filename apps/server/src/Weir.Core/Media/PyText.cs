using System.Globalization;
using System.Numerics;
using System.Text;
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

    /// <summary><c>len(text)</c>: code points, not UTF-16 units.</summary>
    public static int Length(string text)
    {
        var count = 0;
        foreach (var _ in text.EnumerateRunes())
        {
            count++;
        }

        return count;
    }

    /// <summary><c>t[:max_chars] + "…(truncated)"</c> when longer than <paramref name="maxChars"/>.</summary>
    public static string Clip(string text, int maxChars) =>
        Length(text) > maxChars ? Py.Slice(text, maxChars) + "…(truncated)" : text;

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
        isFloat ? Py.FloatRepr(value) : ((long)value).ToString(CultureInfo.InvariantCulture);
}

/// <summary>Python's text forms of values the ffmpeg layer reports, for callers outside <c>Weir.Core</c>.</summary>
public static class PythonText
{
    /// <summary><c>repr(float)</c>, as Python would print a progress percentage or a duration.</summary>
    public static string FloatRepr(double value) => Py.FloatRepr(value);
}

/// <summary>A <c>json.dumps(..., ensure_ascii=True)</c> object writer with the default separators.</summary>
internal sealed class PyJsonObject
{
    private readonly StringBuilder _builder = new("{");
    private bool _first = true;

    public PyJsonObject Add(string key, string value)
    {
        Key(key);
        Py.AppendJsonString(_builder, value);
        return this;
    }

    public PyJsonObject Add(string key, bool value)
    {
        Key(key);
        _builder.Append(value ? "true" : "false");
        return this;
    }

    public PyJsonObject Add(string key, long value)
    {
        Key(key);
        _builder.Append(value.ToString(CultureInfo.InvariantCulture));
        return this;
    }

    public PyJsonObject Add(string key, double value)
    {
        Key(key);
        _builder.Append(double.IsNaN(value) ? "NaN" : double.IsPositiveInfinity(value) ? "Infinity" : double.IsNegativeInfinity(value) ? "-Infinity" : Py.FloatRepr(value));
        return this;
    }

    public PyJsonObject Add(string key, IEnumerable<string> values)
    {
        Key(key);
        _builder.Append('[');
        var first = true;
        foreach (var value in values)
        {
            if (!first)
            {
                _builder.Append(", ");
            }

            first = false;
            Py.AppendJsonString(_builder, value);
        }

        _builder.Append(']');
        return this;
    }

    public override string ToString() => _builder + "}";

    private void Key(string key)
    {
        if (!_first)
        {
            _builder.Append(", ");
        }

        _first = false;
        Py.AppendJsonString(_builder, key);
        _builder.Append(": ");
    }
}
