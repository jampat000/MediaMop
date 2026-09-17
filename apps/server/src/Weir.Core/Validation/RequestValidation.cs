using System.Globalization;
using System.Numerics;
using Weir.Core.Json;

namespace Weir.Core.Validation;

/// <summary>One pydantic error as FastAPI reports it in a 422 body.</summary>
public sealed record ValidationIssue(string Type, IReadOnlyList<object> Loc, string Msg, PyJson Input, PyDict? Ctx = null)
{
    public PyDict ToPyDict()
    {
        var dict = new PyDict()
            .Set("type", Type)
            .Set("loc", new PyList(Loc.Select(part => part is int i ? PyJson.Of(i) : PyJson.Of(Convert.ToString(part, CultureInfo.InvariantCulture)))))
            .Set("msg", Msg)
            .Set("input", Input);
        if (Ctx is not null)
        {
            dict.Set("ctx", Ctx);
        }

        return dict;
    }
}

/// <summary>FastAPI's <c>RequestValidationError</c>: answered with 422 and <c>{"detail": [...]}</c>.</summary>
public sealed class RequestValidationException : Exception
{
    public RequestValidationException()
    {
        Issues = [];
    }

    public RequestValidationException(string message)
        : base(message)
    {
        Issues = [];
    }

    public RequestValidationException(string message, Exception innerException)
        : base(message, innerException)
    {
        Issues = [];
    }

    public RequestValidationException(IReadOnlyList<ValidationIssue> issues)
        : base("Request validation failed.")
    {
        Issues = issues;
    }

    public IReadOnlyList<ValidationIssue> Issues { get; }

    public PyDict ToBody() => new PyDict().Set("detail", new PyList(Issues.Select(issue => (PyJson)issue.ToPyDict())));
}

/// <summary>Collects errors across path, query, header and body parameters in FastAPI's order.</summary>
public sealed class ValidationIssues
{
    private readonly List<ValidationIssue> _issues = [];

    public IReadOnlyList<ValidationIssue> All => _issues;

    public bool Any => _issues.Count > 0;

    public void Add(ValidationIssue issue) => _issues.Add(issue);

    public void ThrowIfAny()
    {
        if (_issues.Count > 0)
        {
            throw new RequestValidationException([.. _issues]);
        }
    }
}

/// <summary>
/// Pydantic v2 lax-mode validation for the scalar shapes Weir's request models use, producing the
/// same error <c>type</c>, <c>msg</c>, <c>input</c> and <c>ctx</c>.
/// </summary>
public static class PydanticRules
{
    private static readonly HashSet<string> TrueStrings = new(StringComparer.OrdinalIgnoreCase) { "1", "on", "t", "true", "y", "yes" };
    private static readonly HashSet<string> FalseStrings = new(StringComparer.OrdinalIgnoreCase) { "0", "off", "f", "false", "n", "no" };

    public static ValidationIssue Missing(IReadOnlyList<object> loc, PyJson input) => new("missing", loc, "Field required", input);

    public static bool TryStr(PyJson input, IReadOnlyList<object> loc, int? minLength, int? maxLength, ValidationIssues issues, out string value)
    {
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(issues);
        value = string.Empty;
        if (input is not PyStr s)
        {
            issues.Add(new ValidationIssue("string_type", loc, "Input should be a valid string", input));
            return false;
        }

        var length = CodePointLength(s.Value);
        if (minLength is { } min && length < min)
        {
            issues.Add(new ValidationIssue(
                "string_too_short", loc, $"String should have at least {min} {Plural(min, "character")}", input,
                new PyDict().Set("min_length", min)));
            return false;
        }

        if (maxLength is { } max && length > max)
        {
            issues.Add(new ValidationIssue(
                "string_too_long", loc, $"String should have at most {max} {Plural(max, "character")}", input,
                new PyDict().Set("max_length", max)));
            return false;
        }

        value = s.Value;
        return true;
    }

    public static bool TryInt(PyJson input, IReadOnlyList<object> loc, long? ge, long? le, ValidationIssues issues, out BigInteger value)
    {
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(issues);
        value = BigInteger.Zero;
        switch (input)
        {
            case PyInt i:
                value = i.Value;
                break;
            case PyBool b:
                value = b.Value ? BigInteger.One : BigInteger.Zero;
                break;
            case PyFloat f:
                if (double.IsNaN(f.Value) || double.IsInfinity(f.Value))
                {
                    issues.Add(new ValidationIssue("finite_number", loc, "Input should be a finite number", input));
                    return false;
                }

                if (Math.Truncate(f.Value) != f.Value)
                {
                    issues.Add(new ValidationIssue("int_from_float", loc, "Input should be a valid integer, got a number with a fractional part", input));
                    return false;
                }

                if (f.Value is > long.MaxValue or < long.MinValue)
                {
                    issues.Add(new ValidationIssue("int_parsing_size", loc, "Unable to parse input string as an integer, exceeded maximum size", input));
                    return false;
                }

                value = new BigInteger(f.Value);
                break;
            case PyStr s:
                if (!TryParseIntString(s.Value, out value))
                {
                    issues.Add(new ValidationIssue("int_parsing", loc, "Input should be a valid integer, unable to parse string as an integer", input));
                    return false;
                }

                break;
            default:
                issues.Add(new ValidationIssue("int_type", loc, "Input should be a valid integer", input));
                return false;
        }

        if (le is { } maximum && value > maximum)
        {
            issues.Add(new ValidationIssue("less_than_equal", loc, $"Input should be less than or equal to {maximum}", input, new PyDict().Set("le", maximum)));
            return false;
        }

        if (ge is { } minimum && value < minimum)
        {
            issues.Add(new ValidationIssue("greater_than_equal", loc, $"Input should be greater than or equal to {minimum}", input, new PyDict().Set("ge", minimum)));
            return false;
        }

        return true;
    }

    public static bool TryBool(PyJson input, IReadOnlyList<object> loc, ValidationIssues issues, out bool value)
    {
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(issues);
        value = false;
        switch (input)
        {
            case PyBool b:
                value = b.Value;
                return true;
            case PyInt i when i.Value.IsZero || i.Value.IsOne:
                value = i.Value.IsOne;
                return true;
            case PyInt:
                issues.Add(BoolParsing(loc, input));
                return false;
            case PyFloat f when f.Value is 0.0 or 1.0:
                value = f.Value == 1.0;
                return true;
            case PyStr s when TrueStrings.Contains(s.Value):
                value = true;
                return true;
            case PyStr s when FalseStrings.Contains(s.Value):
                value = false;
                return true;
            case PyStr:
                issues.Add(BoolParsing(loc, input));
                return false;
            default:
                issues.Add(new ValidationIssue("bool_type", loc, "Input should be a valid boolean", input));
                return false;
        }
    }

    public static bool TryLiteral(PyJson input, IReadOnlyList<object> loc, IReadOnlyList<string> allowed, ValidationIssues issues, out string value)
    {
        ArgumentNullException.ThrowIfNull(allowed);
        ArgumentNullException.ThrowIfNull(issues);
        value = string.Empty;
        if (input is PyStr s && allowed.Contains(s.Value, StringComparer.Ordinal))
        {
            value = s.Value;
            return true;
        }

        var quoted = allowed.Select(item => "'" + item + "'").ToList();
        var expected = quoted.Count == 1 ? quoted[0] : string.Join(", ", quoted.Take(quoted.Count - 1)) + " or " + quoted[^1];
        issues.Add(new ValidationIssue("literal_error", loc, "Input should be " + expected, input, new PyDict().Set("expected", expected)));
        return false;
    }

    public static bool TryStrList(PyJson input, IReadOnlyList<object> loc, ValidationIssues issues, out List<string> value)
    {
        ArgumentNullException.ThrowIfNull(loc);
        ArgumentNullException.ThrowIfNull(issues);
        value = [];
        if (input is not PyList list)
        {
            issues.Add(new ValidationIssue("list_type", loc, "Input should be a valid list", input));
            return false;
        }

        var ok = true;
        for (var index = 0; index < list.Items.Count; index++)
        {
            if (list.Items[index] is PyStr item)
            {
                value.Add(item.Value);
            }
            else
            {
                issues.Add(new ValidationIssue("string_type", [.. loc, index], "Input should be a valid string", list.Items[index]));
                ok = false;
            }
        }

        return ok;
    }

    public static bool TryDict(PyJson input, IReadOnlyList<object> loc, ValidationIssues issues, out PyDict value)
    {
        ArgumentNullException.ThrowIfNull(issues);
        value = new PyDict();
        if (input is PyDict dict)
        {
            value = dict;
            return true;
        }

        issues.Add(new ValidationIssue("dict_type", loc, "Input should be a valid dictionary", input));
        return false;
    }

    /// <summary>Pydantic's UUID parsing, with the uuid crate's error sentences.</summary>
    public static bool TryUuid(string text, IReadOnlyList<object> loc, ValidationIssues issues, out Guid value)
    {
        ArgumentNullException.ThrowIfNull(text);
        ArgumentNullException.ThrowIfNull(issues);
        var error = UuidError(text, out value);
        if (error is null)
        {
            return true;
        }

        issues.Add(new ValidationIssue("uuid_parsing", loc, "Input should be a valid UUID, " + error, PyJson.Of(text), new PyDict().Set("error", error)));
        return false;
    }

    internal static string? UuidError(string input, out Guid value)
    {
        value = Guid.Empty;
        var s = input;
        var offset = 0;
        if (s.Length == 38 && s[0] == '{' && s[^1] == '}')
        {
            s = s[1..^1];
            offset = 1;
        }
        else if (s.Length == 45 && s.StartsWith("urn:uuid:", StringComparison.Ordinal))
        {
            s = s[9..];
            offset = 9;
        }

        var hyphens = 0;
        var groupBounds = new int[4];
        for (var index = 0; index < s.Length; index++)
        {
            var c = s[index];
            if (c == '-')
            {
                if (hyphens < 4)
                {
                    groupBounds[hyphens] = index;
                }

                hyphens++;
            }
            else if (!char.IsAsciiHexDigit(c))
            {
                return $"invalid character: found `{c}` at {index + offset + 1}";
            }
        }

        if (hyphens == 0)
        {
            if (s.Length != 32)
            {
                return $"invalid length: expected length 32 for simple format, found {s.Length}";
            }
        }
        else if (hyphens != 4)
        {
            return $"invalid group count: expected 5, found {hyphens + 1}";
        }
        else
        {
            int[] starts = [0, 9, 14, 19, 24];
            int[] lengths = [8, 4, 4, 4, 12];
            for (var group = 0; group < 4; group++)
            {
                if (groupBounds[group] != starts[group + 1] - 1)
                {
                    var groupStart = group == 0 ? 0 : groupBounds[group - 1] + 1;
                    return $"invalid group length in group {group}: expected {lengths[group]}, found {groupBounds[group] - groupStart}";
                }
            }

            if (s.Length != 36)
            {
                return $"invalid group length in group 4: expected 12, found {s.Length - 24}";
            }
        }

        value = Guid.ParseExact(s.Replace("-", string.Empty, StringComparison.Ordinal), "N");
        return null;
    }

    /// <summary>Strings pydantic reads as integers: whitespace, a sign, digits with underscores, and an all-zero fraction.</summary>
    internal static bool TryParseIntString(string raw, out BigInteger value)
    {
        value = BigInteger.Zero;
        var text = raw.Trim();
        var dot = text.IndexOf('.', StringComparison.Ordinal);
        if (dot >= 0)
        {
            var fraction = text[(dot + 1)..];
            if (fraction.Length == 0 || fraction.Any(c => c != '0'))
            {
                return false;
            }

            text = text[..dot];
        }

        if (text.Any(c => c > 127))
        {
            return false;
        }

        return PyConvert.TryParseIntLiteral(text, out value);
    }

    private static ValidationIssue BoolParsing(IReadOnlyList<object> loc, PyJson input) =>
        new("bool_parsing", loc, "Input should be a valid boolean, unable to interpret input", input);

    private static string Plural(int count, string noun) => count == 1 ? noun : noun + "s";

    private static int CodePointLength(string value)
    {
        var count = 0;
        for (var i = 0; i < value.Length; i++)
        {
            if (char.IsHighSurrogate(value[i]) && i + 1 < value.Length && char.IsLowSurrogate(value[i + 1]))
            {
                i++;
            }

            count++;
        }

        return count;
    }
}

/// <summary>How a request model treats keys it does not declare.</summary>
public enum ExtraFields
{
    Ignore,
    Forbid,
}

/// <summary>
/// Validates one JSON body against a pydantic model, field by field in declaration order.
/// Create it, read each field once, then call <see cref="Finish"/>.
/// </summary>
public sealed class BodyModel
{
    private static readonly object[] BodyLoc = ["body"];

    private readonly PyDict? _dict;
    private readonly ValidationIssues _issues;
    private readonly HashSet<string> _declared = new(StringComparer.Ordinal);
    private bool _valid = true;

    /// <param name="body">The parsed body, or <see langword="null"/> when the request had none.</param>
    /// <param name="issues">Where errors are collected.</param>
    public BodyModel(PyJson? body, ValidationIssues issues)
    {
        ArgumentNullException.ThrowIfNull(issues);
        _issues = issues;
        if (body is null or PyNull)
        {
            issues.Add(PydanticRules.Missing(BodyLoc, PyNull.Instance));
            _valid = false;
            IsPresent = false;
        }
        else if (body is PyDict dict)
        {
            _dict = dict;
            IsPresent = true;
        }
        else
        {
            issues.Add(new ValidationIssue("model_attributes_type", BodyLoc, "Input should be a valid dictionary or object to extract fields from", body));
            _valid = false;
            IsPresent = true;
        }
    }

    /// <summary>A body was sent (even if it is not an object).</summary>
    public bool IsPresent { get; }

    /// <summary>Every field read so far validated.</summary>
    public bool IsValid => _valid;

    public string Str(string name, int? minLength = null, int? maxLength = null) =>
        Read(name, required: true, input => PydanticRules.TryStr(input, Loc(name), minLength, maxLength, _issues, out var v) ? v : null) ?? string.Empty;

    public string? OptionalStr(string name, string? defaultValue = null, int? minLength = null, int? maxLength = null) =>
        ReadNullable(name, defaultValue, input => PydanticRules.TryStr(input, Loc(name), minLength, maxLength, _issues, out var v) ? (true, v) : (false, null));

    public long Number(string name, long defaultValue, bool required, long? ge = null, long? le = null)
    {
        var result = Read<long?>(name, required, input => PydanticRules.TryInt(input, Loc(name), ge, le, _issues, out var v) ? Saturate(v) : null);
        return result ?? defaultValue;
    }

    public long? OptionalInt(string name, long? ge = null, long? le = null) =>
        ReadNullableStruct<long>(name, input => PydanticRules.TryInt(input, Loc(name), ge, le, _issues, out var v) ? (true, Saturate(v)) : (false, 0));

    public bool Bool(string name, bool defaultValue, bool required = false)
    {
        var result = Read<bool?>(name, required, input => PydanticRules.TryBool(input, Loc(name), _issues, out var v) ? v : null);
        return result ?? defaultValue;
    }

    public bool? OptionalBool(string name) =>
        ReadNullableStruct<bool>(name, input => PydanticRules.TryBool(input, Loc(name), _issues, out var v) ? (true, v) : (false, false));

    public string Literal(string name, IReadOnlyList<string> allowed, string? defaultValue = null) =>
        Read(name, required: defaultValue is null, input => PydanticRules.TryLiteral(input, Loc(name), allowed, _issues, out var v) ? v : null) ?? defaultValue ?? string.Empty;

    public List<string> StrList(string name, IReadOnlyList<string> defaultValue) =>
        Read(name, required: false, input => PydanticRules.TryStrList(input, Loc(name), _issues, out var v) ? v : null) ?? [.. defaultValue];

    public PyDict Dict(string name) =>
        Read(name, required: true, input => PydanticRules.TryDict(input, Loc(name), _issues, out var v) ? v : null) ?? new PyDict();

    /// <summary>Report undeclared keys when the model forbids them.</summary>
    public void Finish(ExtraFields extra)
    {
        if (_dict is null || extra == ExtraFields.Ignore)
        {
            return;
        }

        foreach (var (key, value) in _dict.Items)
        {
            if (!_declared.Contains(key))
            {
                _issues.Add(new ValidationIssue("extra_forbidden", Loc(key), "Extra inputs are not permitted", value));
                _valid = false;
            }
        }
    }

    private static object[] Loc(string name) => ["body", name];

    private static long Saturate(BigInteger value) =>
        value > long.MaxValue ? long.MaxValue : value < long.MinValue ? long.MinValue : (long)value;

    private T? Read<T>(string name, bool required, Func<PyJson, T?> validate)
    {
        _declared.Add(name);
        if (_dict is null)
        {
            return default;
        }

        if (!_dict.TryGetValue(name, out var input))
        {
            if (required)
            {
                _issues.Add(PydanticRules.Missing(Loc(name), _dict));
                _valid = false;
            }

            return default;
        }

        var result = validate(input);
        if (result is null)
        {
            _valid = false;
        }

        return result;
    }

    private string? ReadNullable(string name, string? defaultValue, Func<PyJson, (bool Ok, string? Value)> validate)
    {
        _declared.Add(name);
        if (_dict is null || !_dict.TryGetValue(name, out var input))
        {
            return defaultValue;
        }

        if (input is PyNull)
        {
            return null;
        }

        var (ok, value) = validate(input);
        _valid &= ok;
        return value;
    }

    private T? ReadNullableStruct<T>(string name, Func<PyJson, (bool Ok, T Value)> validate)
        where T : struct
    {
        _declared.Add(name);
        if (_dict is null || !_dict.TryGetValue(name, out var input) || input is PyNull)
        {
            return null;
        }

        var (ok, value) = validate(input);
        _valid &= ok;
        return ok ? value : null;
    }
}
