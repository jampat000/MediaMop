using System.Globalization;
using System.Numerics;
using System.Text.Json;
using Weir.Core.Configuration;
using Weir.Core.Json;

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
    /// <summary><c>str.lower()</c>.</summary>
    public static string Lower(string value) => value.ToLowerInvariant();

    /// <summary><c>str.upper()</c>.</summary>
    public static string Upper(string value) => value.ToUpperInvariant();

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
        if (!PythonCompat.TryParseInt(PyStrings.Strip(text), out var parsed))
        {
            throw new RulesInputException("ValueError", $"invalid literal for int() with base 10: {Repr(text)}");
        }

        return parsed;
    }

    /// <summary><c>int(text)</c> for a Python <c>str</c>, or null where it raises <c>ValueError</c>.</summary>
    public static long? TryIntFromText(string text) => PythonCompat.TryParseInt(PyStrings.Strip(text), out var parsed) ? parsed : null;

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
        var s = Lower(PyStrings.Strip(text));
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
        JsonValueKind.Number when IsFloatNumber(value) => PyConvert.FloatRepr(value.GetDouble()),
        JsonValueKind.Number => BigInteger.Parse(value.GetRawText(), CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture),
        JsonValueKind.Array => "[" + string.Join(", ", value.EnumerateArray().Select(Repr)) + "]",
        JsonValueKind.Object => "{" + string.Join(", ", Items(value).Select(kv => Repr(kv.Key) + ": " + Repr(kv.Value))) + "}",
        _ => string.Empty,
    };

    /// <summary><c>repr(text)</c> for a <c>str</c>.</summary>
    public static string Repr(string text) => PyStrings.Repr(text);

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
