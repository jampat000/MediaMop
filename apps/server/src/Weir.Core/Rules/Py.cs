using System.Globalization;
using System.Numerics;
using System.Text;
using System.Text.Json;
using Weir.Core.Configuration;

namespace Weir.Core.Rules;

/// <summary>
/// The Python built-ins the rules engine applies to ffprobe JSON: truthiness, <c>int()</c>,
/// <c>float()</c>, <c>str()</c>, <c>repr()</c>, <c>str.strip()</c> and <c>json.dumps</c> string
/// encoding. ffprobe values are untyped in the reference (a bit rate arrives as a string, a
/// disposition flag may be a string), so matching its decisions means matching these exactly,
/// including where they raise.
/// </summary>
internal static class Py
{
    /// <summary><c>str.isspace()</c> for one UTF-16 unit (every Python whitespace character is in the BMP).</summary>
    public static bool IsSpace(char c) => c switch
    {
        '\t' or '\n' or '\v' or '\f' or '\r' or ' ' => true,
        '\x1c' or '\x1d' or '\x1e' or '\x1f' or '\x85' or '\xa0' => true,
        '\x1680' or '\x2028' or '\x2029' or '\x202f' or '\x205f' or '\x3000' => true,
        >= '\x2000' and <= '\x200a' => true,
        _ => false,
    };

    /// <summary><c>str.strip()</c>.</summary>
    public static string Strip(string value)
    {
        var start = 0;
        var end = value.Length;
        while (start < end && IsSpace(value[start]))
        {
            start++;
        }

        while (end > start && IsSpace(value[end - 1]))
        {
            end--;
        }

        return value[start..end];
    }

    /// <summary><c>str.lower()</c>.</summary>
    public static string Lower(string value) => value.ToLowerInvariant();

    /// <summary><c>str.upper()</c>.</summary>
    public static string Upper(string value) => value.ToUpperInvariant();

    /// <summary><c>text[:count]</c>, counted in code points as Python strings are.</summary>
    public static string Slice(string value, int count)
    {
        var builder = new StringBuilder();
        var taken = 0;
        foreach (var rune in value.EnumerateRunes())
        {
            if (taken++ == count)
            {
                break;
            }

            builder.Append(rune.ToString());
        }

        return builder.ToString();
    }

    // --- JSON values -------------------------------------------------------------------

    /// <summary><c>dict.get(name)</c> on a parsed JSON object: the last duplicate wins, as in <c>json.loads</c>.</summary>
    public static JsonElement? Get(JsonElement obj, string name)
    {
        JsonElement? found = null;
        foreach (var property in obj.EnumerateObject())
        {
            if (property.NameEquals(name))
            {
                found = property.Value;
            }
        }

        return found;
    }

    /// <summary><c>dict[name]</c>: <c>KeyError</c> when absent.</summary>
    public static JsonElement Item(JsonElement obj, string name) =>
        Get(obj, name) ?? throw new RulesInputException("KeyError", $"'{name}'");

    /// <summary><c>dict.items()</c>, with duplicate keys collapsed to the first position and last value.</summary>
    public static List<KeyValuePair<string, JsonElement>> Items(JsonElement obj)
    {
        var order = new List<string>();
        var values = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (var property in obj.EnumerateObject())
        {
            if (!values.ContainsKey(property.Name))
            {
                order.Add(property.Name);
            }

            values[property.Name] = property.Value;
        }

        return order.Select(name => new KeyValuePair<string, JsonElement>(name, values[name])).ToList();
    }

    public static bool IsNone(JsonElement? value) => value is null || value.Value.ValueKind == JsonValueKind.Null;

    public static bool IsDict(JsonElement? value) => value is { ValueKind: JsonValueKind.Object };

    public static bool IsList(JsonElement? value) => value is { ValueKind: JsonValueKind.Array };

    public static bool IsStr(JsonElement? value) => value is { ValueKind: JsonValueKind.String };

    /// <summary><c>json.loads</c> reads a number with a fraction or exponent as <c>float</c>, otherwise <c>int</c>.</summary>
    private static bool IsFloatNumber(JsonElement value) => value.GetRawText().AsSpan().IndexOfAny('.', 'e', 'E') >= 0;

    /// <summary><c>bool(value)</c>.</summary>
    public static bool Truthy(JsonElement? value)
    {
        if (value is not { } v)
        {
            return false;
        }

        return v.ValueKind switch
        {
            JsonValueKind.Null or JsonValueKind.Undefined or JsonValueKind.False => false,
            JsonValueKind.True => true,
            JsonValueKind.String => v.GetString()!.Length > 0,
            JsonValueKind.Number => IsFloatNumber(v) ? v.GetDouble() != 0.0 : !BigInteger.Parse(v.GetRawText(), CultureInfo.InvariantCulture).IsZero,
            JsonValueKind.Array => v.GetArrayLength() > 0,
            JsonValueKind.Object => v.EnumerateObject().Any(),
            _ => false,
        };
    }

    /// <summary><c>value or fallback</c> for a string fallback, then <c>str()</c>.</summary>
    public static string StrOr(JsonElement? value, string fallback) => Truthy(value) ? Str(value) : fallback;

    /// <summary>
    /// <c>(value or "")</c> followed by a string method: a truthy value that is not a string has no
    /// <c>strip</c>, so Python raises <c>AttributeError</c>.
    /// </summary>
    public static string StrMethodTarget(JsonElement? value)
    {
        if (!Truthy(value))
        {
            return string.Empty;
        }

        if (!IsStr(value))
        {
            throw new RulesInputException("AttributeError", $"'{TypeName(value)}' object has no attribute 'strip'");
        }

        return value!.Value.GetString()!;
    }

    /// <summary><c>int(value)</c>, raising what Python raises.</summary>
    public static long Int(JsonElement? value)
    {
        if (value is not { } v || v.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            throw new RulesInputException("TypeError", "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'");
        }

        switch (v.ValueKind)
        {
            case JsonValueKind.True:
                return 1;
            case JsonValueKind.False:
                return 0;
            case JsonValueKind.Number when IsFloatNumber(v):
                return FloatToInt(v.GetDouble());
            case JsonValueKind.Number:
                return BigToLong(BigInteger.Parse(v.GetRawText(), CultureInfo.InvariantCulture));
            case JsonValueKind.String:
                return IntFromText(v.GetString()!);
            default:
                throw new RulesInputException("TypeError", $"int() argument must be a string, a bytes-like object or a real number, not '{TypeName(v)}'");
        }
    }

    /// <summary><c>int(value)</c> inside <c>try: … except (TypeError, ValueError)</c>.</summary>
    public static bool TryInt(JsonElement? value, out long result)
    {
        try
        {
            result = Int(value);
            return true;
        }
        catch (RulesInputException error) when (error.PythonError is "TypeError" or "ValueError")
        {
            result = 0;
            return false;
        }
    }

    /// <summary><c>int(text)</c> for a Python <c>str</c>.</summary>
    public static long IntFromText(string text)
    {
        if (!PythonCompat.TryParseInt(Strip(text), out var parsed))
        {
            throw new RulesInputException("ValueError", $"invalid literal for int() with base 10: {Repr(text)}");
        }

        return parsed;
    }

    /// <summary><c>int(text)</c> for a Python <c>str</c>, or null where it raises <c>ValueError</c>.</summary>
    public static long? TryIntFromText(string text) => PythonCompat.TryParseInt(Strip(text), out var parsed) ? parsed : null;

    private static long FloatToInt(double value)
    {
        if (double.IsNaN(value))
        {
            throw new RulesInputException("ValueError", "cannot convert float NaN to integer");
        }

        if (double.IsInfinity(value))
        {
            throw new RulesInputException("OverflowError", "cannot convert float infinity to integer");
        }

        return BigToLong(new BigInteger(Math.Truncate(value)));
    }

    private static long BigToLong(BigInteger value) =>
        value >= long.MinValue && value <= long.MaxValue
            ? (long)value
            : throw new RulesInputException("OverflowError", "integer is outside the range the .NET engine supports");

    /// <summary>Narrows a Python int to the <see cref="int"/> the plan records use.</summary>
    public static int ToInt32(long value) =>
        value is >= int.MinValue and <= int.MaxValue
            ? (int)value
            : throw new RulesInputException("OverflowError", "integer is outside the range the .NET engine supports");

    /// <summary><c>float(text)</c> for a Python <c>str</c>, or null where it raises <c>ValueError</c>.</summary>
    public static double? TryFloatFromText(string text)
    {
        var s = Lower(Strip(text));
        var body = s;
        var sign = 1.0;
        if (body.StartsWith('+') || body.StartsWith('-'))
        {
            sign = body[0] == '-' ? -1.0 : 1.0;
            body = body[1..];
        }

        if (body is "inf" or "infinity")
        {
            return sign * double.PositiveInfinity;
        }

        if (body == "nan")
        {
            return double.NaN;
        }

        if (!IsFloatLiteral(body))
        {
            return null;
        }

        return sign * double.Parse(body.Replace("_", string.Empty, StringComparison.Ordinal), NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent, CultureInfo.InvariantCulture);
    }

    /// <summary>Python's float literal grammar: digits with single underscores between them, a point, an exponent.</summary>
    private static bool IsFloatLiteral(string body)
    {
        var i = 0;
        var mantissaDigits = ReadDigits(body, ref i);
        if (mantissaDigits < 0)
        {
            return false;
        }

        if (i < body.Length && body[i] == '.')
        {
            i++;
            var fraction = ReadDigits(body, ref i);
            if (fraction < 0)
            {
                return false;
            }

            mantissaDigits += fraction;
        }

        if (mantissaDigits == 0)
        {
            return false;
        }

        if (i < body.Length && body[i] == 'e')
        {
            i++;
            if (i < body.Length && (body[i] == '+' || body[i] == '-'))
            {
                i++;
            }

            if (ReadDigits(body, ref i) <= 0)
            {
                return false;
            }
        }

        return i == body.Length;
    }

    /// <summary>Digits with single underscores between them. Returns the digit count, or -1 when malformed.</summary>
    private static int ReadDigits(string text, ref int i)
    {
        var count = 0;
        while (i < text.Length)
        {
            if (char.IsAsciiDigit(text[i]))
            {
                count++;
                i++;
            }
            else if (text[i] == '_' && count > 0 && i + 1 < text.Length && char.IsAsciiDigit(text[i + 1]))
            {
                i++;
            }
            else
            {
                break;
            }
        }

        return count;
    }

    /// <summary><c>str(value)</c>.</summary>
    public static string Str(JsonElement? value)
    {
        if (value is not { } v)
        {
            return "None";
        }

        return v.ValueKind == JsonValueKind.String ? v.GetString()! : Repr(v);
    }

    /// <summary><c>repr(value)</c>.</summary>
    public static string Repr(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Null or JsonValueKind.Undefined => "None",
        JsonValueKind.True => "True",
        JsonValueKind.False => "False",
        JsonValueKind.String => Repr(value.GetString()!),
        JsonValueKind.Number when IsFloatNumber(value) => FloatRepr(value.GetDouble()),
        JsonValueKind.Number => BigInteger.Parse(value.GetRawText(), CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture),
        JsonValueKind.Array => "[" + string.Join(", ", value.EnumerateArray().Select(Repr)) + "]",
        JsonValueKind.Object => "{" + string.Join(", ", Items(value).Select(kv => Repr(kv.Key) + ": " + Repr(kv.Value))) + "}",
        _ => string.Empty,
    };

    /// <summary><c>repr(text)</c> for a <c>str</c>.</summary>
    public static string Repr(string text)
    {
        var quote = text.Contains('\'', StringComparison.Ordinal) && !text.Contains('"', StringComparison.Ordinal) ? '"' : '\'';
        var builder = new StringBuilder(text.Length + 2);
        builder.Append(quote);
        foreach (var rune in text.EnumerateRunes())
        {
            var cp = rune.Value;
            if (cp == quote || cp == '\\')
            {
                builder.Append('\\').Append((char)cp);
            }
            else if (cp == '\t')
            {
                builder.Append("\\t");
            }
            else if (cp == '\n')
            {
                builder.Append("\\n");
            }
            else if (cp == '\r')
            {
                builder.Append("\\r");
            }
            else if (cp < 0x20 || cp == 0x7f)
            {
                builder.Append(CultureInfo.InvariantCulture, $"\\x{cp:x2}");
            }
            else if (cp < 0x7f || IsPrintable(rune))
            {
                builder.Append(rune.ToString());
            }
            else if (cp < 0x100)
            {
                builder.Append(CultureInfo.InvariantCulture, $"\\x{cp:x2}");
            }
            else if (cp < 0x10000)
            {
                builder.Append(CultureInfo.InvariantCulture, $"\\u{cp:x4}");
            }
            else
            {
                builder.Append(CultureInfo.InvariantCulture, $"\\U{cp:x8}");
            }
        }

        builder.Append(quote);
        return builder.ToString();
    }

    private static bool IsPrintable(Rune rune) => Rune.GetUnicodeCategory(rune) switch
    {
        UnicodeCategory.Control or UnicodeCategory.Format or UnicodeCategory.Surrogate or UnicodeCategory.PrivateUse
            or UnicodeCategory.OtherNotAssigned or UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator
            or UnicodeCategory.SpaceSeparator => rune.Value == ' ',
        _ => true,
    };

    /// <summary><c>repr(float)</c>: the shortest round-trip digits, fixed notation between 1e-4 and 1e16.</summary>
    public static string FloatRepr(double value)
    {
        if (double.IsNaN(value))
        {
            return "nan";
        }

        if (double.IsInfinity(value))
        {
            return value > 0 ? "inf" : "-inf";
        }

        var roundTrip = value.ToString("R", CultureInfo.InvariantCulture);
        var negative = roundTrip.StartsWith('-');
        if (negative)
        {
            roundTrip = roundTrip[1..];
        }

        var exponentAt = roundTrip.IndexOf('E', StringComparison.Ordinal);
        var mantissa = exponentAt < 0 ? roundTrip : roundTrip[..exponentAt];
        var exponent = exponentAt < 0 ? 0 : int.Parse(roundTrip[(exponentAt + 1)..], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
        var point = mantissa.IndexOf('.', StringComparison.Ordinal);
        var digits = point < 0 ? mantissa : mantissa.Remove(point, 1);
        // Python's decpt: value = 0.<digits> x 10^decpt.
        var decpt = (point < 0 ? mantissa.Length : point) + exponent;
        var leading = digits.Length - digits.TrimStart('0').Length;
        digits = digits.TrimStart('0');
        decpt -= leading;
        digits = digits.TrimEnd('0');
        var sign = negative ? "-" : string.Empty;
        if (digits.Length == 0)
        {
            return sign + "0.0";
        }

        if (decpt is > -4 and <= 16)
        {
            if (decpt <= 0)
            {
                return sign + "0." + new string('0', -decpt) + digits;
            }

            if (decpt >= digits.Length)
            {
                return sign + digits + new string('0', decpt - digits.Length) + ".0";
            }

            return sign + digits[..decpt] + "." + digits[decpt..];
        }

        var mantissaText = digits.Length == 1 ? digits : digits[..1] + "." + digits[1..];
        var e = decpt - 1;
        return sign + mantissaText + "e" + (e < 0 ? "-" : "+") + Math.Abs(e).ToString("00", CultureInfo.InvariantCulture);
    }

    /// <summary>A string as <c>json.dumps</c> writes it with the default <c>ensure_ascii=True</c>.</summary>
    public static void AppendJsonString(StringBuilder builder, string text)
    {
        builder.Append('"');
        foreach (var c in text)
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
                case >= ' ' and <= '~':
                    builder.Append(c);
                    break;
                default:
                    builder.Append(CultureInfo.InvariantCulture, $"\\u{(int)c:x4}");
                    break;
            }
        }

        builder.Append('"');
    }

    private static string TypeName(JsonElement? value) => value?.ValueKind switch
    {
        null or JsonValueKind.Null or JsonValueKind.Undefined => "NoneType",
        JsonValueKind.True or JsonValueKind.False => "bool",
        JsonValueKind.String => "str",
        JsonValueKind.Number when IsFloatNumber(value.Value) => "float",
        JsonValueKind.Number => "int",
        JsonValueKind.Array => "list",
        JsonValueKind.Object => "dict",
        _ => "object",
    };
}
