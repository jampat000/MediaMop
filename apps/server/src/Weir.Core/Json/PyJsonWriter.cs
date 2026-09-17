using System.Globalization;
using System.Text;

namespace Weir.Core.Json;

/// <summary>How <see cref="PyJsonWriter"/> lays out JSON, mirroring <c>json.dumps</c> arguments.</summary>
/// <param name="EnsureAscii">Escape every non-ASCII character as <c>\uXXXX</c>.</param>
/// <param name="ItemSeparator">Between items.</param>
/// <param name="KeySeparator">Between a key and its value.</param>
/// <param name="Indent">Pretty-print with this many spaces, or <see langword="null"/> for one line.</param>
/// <param name="SortKeys">Sort object keys.</param>
public sealed record PyJsonFormat(bool EnsureAscii, string ItemSeparator, string KeySeparator, int? Indent, bool SortKeys)
{
    /// <summary>Starlette's <c>JSONResponse</c>: <c>ensure_ascii=False, separators=(",", ":")</c>.</summary>
    public static readonly PyJsonFormat Response = new(false, ",", ":", null, false);

    /// <summary><c>json.dumps(value)</c> with default arguments.</summary>
    public static readonly PyJsonFormat Default = new(true, ", ", ": ", null, false);

    /// <summary><c>json.dumps(value, indent=2, sort_keys=True)</c> (configuration snapshots).</summary>
    public static readonly PyJsonFormat IndentedSorted = new(true, ",", ": ", 2, true);

    /// <summary><c>json.dumps(value, indent=2)</c>.</summary>
    public static readonly PyJsonFormat Indented = new(true, ",", ": ", 2, false);

    /// <summary><c>json.dumps(value, separators=(",", ":"))</c>.</summary>
    public static readonly PyJsonFormat Compact = new(true, ",", ":", null, false);
}

/// <summary><c>json.dumps</c>: Python's float <c>repr</c>, its escaping rules and its separators.</summary>
public static class PyJsonWriter
{
    public static string Dumps(PyJson value, PyJsonFormat format)
    {
        ArgumentNullException.ThrowIfNull(value);
        ArgumentNullException.ThrowIfNull(format);
        var builder = new StringBuilder();
        Write(builder, value, format, 0);
        return builder.ToString();
    }

    public static byte[] DumpsUtf8(PyJson value, PyJsonFormat format) => Encoding.UTF8.GetBytes(Dumps(value, format));

    /// <summary>Python's <c>repr(float)</c>.</summary>
    public static string FloatRepr(double value)
    {
        if (double.IsNaN(value))
        {
            return "NaN";
        }

        if (double.IsPositiveInfinity(value))
        {
            return "Infinity";
        }

        if (double.IsNegativeInfinity(value))
        {
            return "-Infinity";
        }

        if (value == 0)
        {
            return double.IsNegative(value) ? "-0.0" : "0.0";
        }

        // Shortest round-trip digits and the decimal exponent, then Python's layout rules.
        var shortest = Math.Abs(value).ToString("R", CultureInfo.InvariantCulture);
        var (digits, decimalPoint) = SplitDigits(shortest);
        var sign = value < 0 ? "-" : string.Empty;
        if (decimalPoint > -4 && decimalPoint <= 16)
        {
            string text;
            if (decimalPoint <= 0)
            {
                text = "0." + new string('0', -decimalPoint) + digits;
            }
            else if (decimalPoint >= digits.Length)
            {
                text = digits + new string('0', decimalPoint - digits.Length) + ".0";
            }
            else
            {
                text = digits[..decimalPoint] + "." + digits[decimalPoint..];
            }

            return sign + text;
        }

        var exponent = decimalPoint - 1;
        var mantissa = digits.Length == 1 ? digits : digits[0] + "." + digits[1..];
        var expSign = exponent < 0 ? "-" : "+";
        return sign + mantissa + "e" + expSign + Math.Abs(exponent).ToString("00", CultureInfo.InvariantCulture);
    }

    /// <summary>Digits without leading/trailing zeros and the position of the decimal point (value = 0.digits × 10^point).</summary>
    private static (string Digits, int DecimalPoint) SplitDigits(string invariantText)
    {
        var exponent = 0;
        var mantissa = invariantText;
        var e = invariantText.IndexOfAny(['E', 'e']);
        if (e >= 0)
        {
            exponent = int.Parse(invariantText[(e + 1)..], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
            mantissa = invariantText[..e];
        }

        var dot = mantissa.IndexOf('.', StringComparison.Ordinal);
        var integerPart = dot < 0 ? mantissa : mantissa[..dot];
        var fraction = dot < 0 ? string.Empty : mantissa[(dot + 1)..];
        var all = integerPart + fraction;
        var point = integerPart.Length + exponent;
        var leading = 0;
        while (leading < all.Length - 1 && all[leading] == '0')
        {
            leading++;
        }

        all = all[leading..];
        point -= leading;
        all = all.TrimEnd('0');
        if (all.Length == 0)
        {
            all = "0";
        }

        return (all, point);
    }

    private static void Write(StringBuilder builder, PyJson value, PyJsonFormat format, int level)
    {
        switch (value)
        {
            case PyNull:
                builder.Append("null");
                break;
            case PyBool b:
                builder.Append(b.Value ? "true" : "false");
                break;
            case PyInt i:
                builder.Append(i.Value.ToString(CultureInfo.InvariantCulture));
                break;
            case PyFloat f:
                builder.Append(FloatRepr(f.Value));
                break;
            case PyStr s:
                WriteString(builder, s.Value, format.EnsureAscii);
                break;
            case PyList list:
                WriteList(builder, list, format, level);
                break;
            case PyDict dict:
                WriteDict(builder, dict, format, level);
                break;
            default:
                throw new InvalidOperationException("Unknown JSON value.");
        }
    }

    private static void WriteList(StringBuilder builder, PyList list, PyJsonFormat format, int level)
    {
        if (list.Items.Count == 0)
        {
            builder.Append("[]");
            return;
        }

        builder.Append('[');
        for (var i = 0; i < list.Items.Count; i++)
        {
            if (i > 0)
            {
                builder.Append(format.ItemSeparator);
            }

            NewLine(builder, format, level + 1);
            Write(builder, list.Items[i], format, level + 1);
        }

        NewLine(builder, format, level);
        builder.Append(']');
    }

    private static void WriteDict(StringBuilder builder, PyDict dict, PyJsonFormat format, int level)
    {
        if (dict.Count == 0)
        {
            builder.Append("{}");
            return;
        }

        IEnumerable<string> keys = dict.Keys;
        if (format.SortKeys)
        {
            keys = keys.OrderBy(k => k, StringComparer.Ordinal);
        }

        builder.Append('{');
        var first = true;
        foreach (var key in keys)
        {
            if (!first)
            {
                builder.Append(format.ItemSeparator);
            }

            first = false;
            NewLine(builder, format, level + 1);
            WriteString(builder, key, format.EnsureAscii);
            builder.Append(format.KeySeparator);
            Write(builder, dict[key], format, level + 1);
        }

        NewLine(builder, format, level);
        builder.Append('}');
    }

    private static void NewLine(StringBuilder builder, PyJsonFormat format, int level)
    {
        if (format.Indent is { } indent)
        {
            builder.Append('\n').Append(' ', indent * level);
        }
    }

    /// <summary><c>py_encode_basestring(_ascii)</c>.</summary>
    public static void WriteString(StringBuilder builder, string value, bool ensureAscii)
    {
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(value);
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
                    if (c < 0x20 || (ensureAscii && c > '~'))
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

        builder.Append('"');
    }
}
