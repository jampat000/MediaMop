using System.Globalization;
using System.Numerics;
using System.Text;

namespace Weir.Core.Json;

/// <summary>A Python <c>ValueError</c> raised by a builtin conversion, with Python's message.</summary>
public sealed class PyValueErrorException : Exception
{
    public PyValueErrorException()
    {
    }

    public PyValueErrorException(string message)
        : base(message)
    {
    }

    public PyValueErrorException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>A Python <c>TypeError</c>: not caught by the handlers that catch <c>ValueError</c>, so it surfaces as a 500.</summary>
public sealed class PyTypeErrorException : Exception
{
    public PyTypeErrorException()
    {
    }

    public PyTypeErrorException(string message)
        : base(message)
    {
    }

    public PyTypeErrorException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>Python builtins applied to JSON values: <c>str()</c>, <c>repr()</c>, <c>int()</c>, <c>bool()</c>.</summary>
public static class PyConvert
{
    /// <summary><c>str(value)</c>.</summary>
    public static string Str(PyJson value) => value switch
    {
        PyStr s => s.Value,
        _ => Repr(value),
    };

    /// <summary><c>repr(value)</c>.</summary>
    public static string Repr(PyJson value)
    {
        ArgumentNullException.ThrowIfNull(value);
        return value switch
        {
            PyNull => "None",
            PyBool b => b.Value ? "True" : "False",
            PyInt i => i.Value.ToString(CultureInfo.InvariantCulture),
            PyFloat f => FloatRepr(f.Value),
            PyStr s => PyStrings.Repr(s.Value),
            PyList l => "[" + string.Join(", ", l.Items.Select(Repr)) + "]",
            PyDict d => "{" + string.Join(", ", d.Items.Select(p => PyStrings.Repr(p.Key) + ": " + Repr(p.Value))) + "}",
            _ => throw new InvalidOperationException("Unknown JSON value."),
        };
    }

    /// <summary><c>repr(float)</c>: shortest round-trip digits, and <c>nan</c>, <c>inf</c>, <c>-inf</c>.</summary>
    public static string FloatRepr(double value) =>
        double.IsNaN(value) ? "nan" : double.IsInfinity(value) ? (value > 0 ? "inf" : "-inf") : PyJsonWriter.FloatRepr(value);

    /// <summary><c>int(value)</c>.</summary>
    public static BigInteger ToInt(PyJson value)
    {
        ArgumentNullException.ThrowIfNull(value);
        switch (value)
        {
            case PyInt i:
                return i.Value;
            case PyBool b:
                return b.Value ? BigInteger.One : BigInteger.Zero;
            case PyFloat f:
                if (double.IsNaN(f.Value))
                {
                    throw new PyValueErrorException("cannot convert float NaN to integer");
                }

                if (double.IsInfinity(f.Value))
                {
                    throw new PyTypeErrorException("cannot convert float infinity to integer");
                }

                return new BigInteger(Math.Truncate(f.Value));
            case PyStr s:
                if (TryParseIntLiteral(s.Value, out var parsed))
                {
                    return parsed;
                }

                throw new PyValueErrorException($"invalid literal for int() with base 10: {PyStrings.Repr(s.Value)}");
            default:
                throw new PyTypeErrorException(
                    $"int() argument must be a string, a bytes-like object or a real number, not '{value.PythonTypeName}'");
        }
    }

    /// <summary><c>int(str)</c> in base 10: surrounding whitespace, a sign, digits with single underscores between them.</summary>
    public static bool TryParseIntLiteral(string raw, out BigInteger value)
    {
        ArgumentNullException.ThrowIfNull(raw);
        value = BigInteger.Zero;
        var text = raw.Trim();
        if (text.Length == 0)
        {
            return false;
        }

        var negative = false;
        if (text[0] is '+' or '-')
        {
            negative = text[0] == '-';
            text = text[1..];
        }

        if (text.Length == 0 || text[0] == '_' || text[^1] == '_' || text.Contains("__", StringComparison.Ordinal))
        {
            return false;
        }

        var digits = new StringBuilder(text.Length);
        foreach (var c in text)
        {
            if (c == '_')
            {
                continue;
            }

            if (!char.IsDigit(c))
            {
                return false;
            }

            digits.Append((char)('0' + (int)char.GetNumericValue(c)));
        }

        value = BigInteger.Parse(digits.ToString(), NumberStyles.None, CultureInfo.InvariantCulture);
        if (negative)
        {
            value = -value;
        }

        return true;
    }

    /// <summary><c>bool(value)</c>.</summary>
    public static bool Bool(PyJson value)
    {
        ArgumentNullException.ThrowIfNull(value);
        return value.IsTruthy;
    }

    /// <summary>A SQLite storage value as the Python value SQLAlchemy would hand back for an untyped column.</summary>
    public static PyJson FromDatabase(object? value) => value switch
    {
        null or DBNull => PyNull.Instance,
        long l => new PyInt(l),
        int i => new PyInt(i),
        double d => new PyFloat(d),
        string s => new PyStr(s),
        byte[] bytes => new PyStr(Encoding.UTF8.GetString(bytes)),
        bool b => PyJson.Of(b),
        _ => new PyStr(Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty),
    };

    /// <summary>A JSON value as a SQLite parameter, the way the sqlite3 driver binds it.</summary>
    public static object ToDatabase(PyJson value) => value switch
    {
        PyNull => DBNull.Value,
        PyBool b => b.Value ? 1L : 0L,
        PyInt i => i.Value >= long.MinValue && i.Value <= long.MaxValue
            ? (long)i.Value
            : throw new PyTypeErrorException("Python int too large to convert to SQLite INTEGER"),
        PyFloat f => f.Value,
        PyStr s => s.Value,
        _ => throw new PyTypeErrorException($"Error binding parameter - type '{value.PythonTypeName}' is not supported"),
    };
}
