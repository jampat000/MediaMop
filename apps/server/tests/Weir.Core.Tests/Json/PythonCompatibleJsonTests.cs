using Weir.Core.Json;
using Weir.Core.Validation;

namespace Weir.Core.Tests.Json;

/// <summary>JSON read and written the way CPython's <c>json</c> module and pydantic do (values taken from the Python backend).</summary>
public sealed class PythonCompatibleJsonTests
{
    [Theory]
    [InlineData("{bad", "Expecting property name enclosed in double quotes", 1)]
    [InlineData("{\"a\": [1, 2,]}", "Expecting value", 12)]
    [InlineData("{\"a\": \"x\\q\"}", "Invalid \\escape", 8)]
    [InlineData("{} x", "Extra data", 3)]
    [InlineData("", "Expecting value", 0)]
    [InlineData("{\"a\" 1}", "Expecting ':' delimiter", 5)]
    [InlineData("{\"a\": 1 \"b\": 2}", "Expecting ',' delimiter", 8)]
    [InlineData("\"abc", "Unterminated string starting at", 0)]
    [InlineData("\"a\u0001\"", "Invalid control character at", 2)]
    [InlineData("\"\\u12\"", "Invalid \\uXXXX escape", 2)]
    [InlineData("[1,]", "Expecting value", 3)]
    [InlineData("01", "Extra data", 1)]
    [InlineData("\uFEFF{}", "Unexpected UTF-8 BOM (decode using utf-8-sig)", 0)]
    public void Decode_errors_carry_the_c_scanner_message_and_position(string text, string message, int position)
    {
        var error = Assert.Throws<PyJsonDecodeException>(() => PyJsonParser.Parse(text));
        Assert.Equal(message, error.Detail);
        Assert.Equal(position, error.Position);
    }

    [Fact]
    public void Values_keep_python_types_order_and_duplicate_key_rules()
    {
        var value = Assert.IsType<PyDict>(PyJsonParser.Parse("{\"b\": 1, \"a\": 2.0, \"b\": 3, \"n\": NaN, \"big\": 123456789012345678901234567890, \"s\": \"\\ud83d\\ude00\"}"));
        Assert.Equal(["b", "a", "n", "big", "s"], value.Keys);
        Assert.Equal(3, (int)Assert.IsType<PyInt>(value["b"]).Value);
        Assert.IsType<PyFloat>(value["a"]);
        Assert.True(double.IsNaN(Assert.IsType<PyFloat>(value["n"]).Value));
        Assert.Equal("123456789012345678901234567890", value["big"].ToString());
        Assert.Equal("\U0001F600", Assert.IsType<PyStr>(value["s"]).Value);
    }

    [Theory]
    [InlineData(0.5723745822906494, "0.5723745822906494")]
    [InlineData(1.0, "1.0")]
    [InlineData(1e-7, "1e-07")]
    [InlineData(1e22, "1e+22")]
    [InlineData(123456789012345678.0, "1.2345678901234568e+17")]
    [InlineData(2.5e-5, "2.5e-05")]
    [InlineData(0.0001, "0.0001")]
    [InlineData(1234567890123456.0, "1234567890123456.0")]
    [InlineData(-3.25, "-3.25")]
    public void Floats_are_written_as_python_repr(double value, string expected) => Assert.Equal(expected, PyJsonWriter.FloatRepr(value));

    [Fact]
    public void Response_json_is_compact_and_keeps_non_ascii_while_json_dumps_escapes_it()
    {
        var value = new PyDict().Set("a", "é\u2028<>&'\u007f\u0001\"\\/").Set("n", PyJson.Null).Set("l", new PyList([PyJson.Of(1), PyJson.Of(true)]));
        Assert.Equal("{\"a\":\"é\u2028<>&'\u007f\\u0001\\\"\\\\/\",\"n\":null,\"l\":[1,true]}", PyJsonWriter.Dumps(value, PyJsonFormat.Response));
        Assert.Equal("{\"a\": \"\\u00e9\\u2028<>&'\\u007f\\u0001\\\"\\\\/\", \"n\": null, \"l\": [1, true]}", PyJsonWriter.Dumps(value, PyJsonFormat.Default));
        Assert.Equal("{\n  \"l\": [\n    1,\n    true\n  ],\n  \"n\": null\n}", PyJsonWriter.Dumps(new PyDict().Set("n", PyJson.Null).Set("l", new PyList([PyJson.Of(1), PyJson.Of(true)])), PyJsonFormat.IndentedSorted));
    }

    [Theory]
    [InlineData("  30  ", true, 30)]
    [InlineData("+30", true, 30)]
    [InlineData("3_0", true, 30)]
    [InlineData("30.0", true, 30)]
    [InlineData("30.5", false, 0)]
    [InlineData("1e2", false, 0)]
    [InlineData("", false, 0)]
    [InlineData("0x1f", false, 0)]
    [InlineData("\u0663", false, 0)]
    public void Integer_strings_follow_pydantic(string raw, bool ok, int expected)
    {
        var issues = new ValidationIssues();
        Assert.Equal(ok, PydanticRules.TryInt(new PyStr(raw), ["body", "i"], null, null, issues, out var value));
        if (ok)
        {
            Assert.Equal(expected, (int)value);
        }
        else
        {
            Assert.Equal("int_parsing", Assert.Single(issues.All).Type);
        }
    }

    [Fact]
    public void Pydantic_error_shapes_match_fastapi_422_bodies()
    {
        var issues = new ValidationIssues();
        var model = new BodyModel(PyJsonParser.Parse("{\"password\": 5, \"csrf_token\": \"\", \"zzz\": 1}"), issues);
        model.Str("username", minLength: 1, maxLength: 64);
        model.Str("password", minLength: 8, maxLength: 512);
        model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        Assert.Equal(
            "{\"detail\":[{\"type\":\"missing\",\"loc\":[\"body\",\"username\"],\"msg\":\"Field required\",\"input\":{\"password\":5,\"csrf_token\":\"\",\"zzz\":1}}," +
            "{\"type\":\"string_type\",\"loc\":[\"body\",\"password\"],\"msg\":\"Input should be a valid string\",\"input\":5}," +
            "{\"type\":\"string_too_short\",\"loc\":[\"body\",\"csrf_token\"],\"msg\":\"String should have at least 1 character\",\"input\":\"\",\"ctx\":{\"min_length\":1}}," +
            "{\"type\":\"extra_forbidden\",\"loc\":[\"body\",\"zzz\"],\"msg\":\"Extra inputs are not permitted\",\"input\":1}]}",
            PyJsonWriter.Dumps(new RequestValidationException(issues.All).ToBody(), PyJsonFormat.Response));
    }

    [Theory]
    [InlineData("true", true, null)]
    [InlineData("\"Yes\"", true, null)]
    [InlineData("\"t\"", true, null)]
    [InlineData("0", false, null)]
    [InlineData("1.0", true, null)]
    [InlineData("\" true \"", null, "bool_parsing")]
    [InlineData("2", null, "bool_parsing")]
    [InlineData("\"\"", null, "bool_parsing")]
    [InlineData("null", null, "bool_type")]
    [InlineData("[]", null, "bool_type")]
    [InlineData("1.5", null, "bool_type")]
    public void Booleans_follow_pydantic_lax_mode(string json, bool? expected, string? errorType)
    {
        var issues = new ValidationIssues();
        var ok = PydanticRules.TryBool(PyJsonParser.Parse(json), ["b"], issues, out var value);
        Assert.Equal(expected is not null, ok);
        if (expected is { } e)
        {
            Assert.Equal(e, value);
        }
        else
        {
            Assert.Equal(errorType, Assert.Single(issues.All).Type);
        }
    }

    [Theory]
    [InlineData("not-a-uuid", "invalid character: found `n` at 1")]
    [InlineData("1234", "invalid length: expected length 32 for simple format, found 4")]
    [InlineData("6f1c2a8e-0000-4000-8000-00000000000g", "invalid character: found `g` at 36")]
    [InlineData("6f1c2a8e0000400080000000000000000000", "invalid length: expected length 32 for simple format, found 36")]
    [InlineData("6f1c2a8e-0000-4000-8000000-000000000000", "invalid group length in group 3: expected 4, found 7")]
    [InlineData("{6f1c2a8e-0000-4000-8000-000000000000}", null)]
    [InlineData("urn:uuid:6f1c2a8e-0000-4000-8000-000000000000", null)]
    [InlineData("6F1C2A8E000040008000000000000000", null)]
    public void Uuids_follow_pydantic(string raw, string? error)
    {
        Assert.Equal(error, PydanticRules.UuidError(raw, out var value));
        if (error is null)
        {
            Assert.Equal(Guid.Parse("6f1c2a8e-0000-4000-8000-000000000000"), value);
        }
    }

    [Fact]
    public void Literal_and_int_constraint_messages_match()
    {
        var issues = new ValidationIssues();
        PydanticRules.TryLiteral(new PyStr("Nope"), ["body", "mode"], ["Auto", "DownloadOnly", "NotifyOnly"], issues, out _);
        PydanticRules.TryInt(PyJson.Of(0), ["body", "m"], 1, 10080, issues, out _);
        PydanticRules.TryInt(new PyFloat(30.5), ["body", "m"], 1, 10080, issues, out _);
        PydanticRules.TryInt(new PyStr("99999999999999999999999"), ["body", "m"], 1, 10080, issues, out _);
        Assert.Equal(
            "{\"detail\":[{\"type\":\"literal_error\",\"loc\":[\"body\",\"mode\"],\"msg\":\"Input should be 'Auto', 'DownloadOnly' or 'NotifyOnly'\",\"input\":\"Nope\",\"ctx\":{\"expected\":\"'Auto', 'DownloadOnly' or 'NotifyOnly'\"}}," +
            "{\"type\":\"greater_than_equal\",\"loc\":[\"body\",\"m\"],\"msg\":\"Input should be greater than or equal to 1\",\"input\":0,\"ctx\":{\"ge\":1}}," +
            "{\"type\":\"int_from_float\",\"loc\":[\"body\",\"m\"],\"msg\":\"Input should be a valid integer, got a number with a fractional part\",\"input\":30.5}," +
            "{\"type\":\"less_than_equal\",\"loc\":[\"body\",\"m\"],\"msg\":\"Input should be less than or equal to 10080\",\"input\":\"99999999999999999999999\",\"ctx\":{\"le\":10080}}]}",
            PyJsonWriter.Dumps(new RequestValidationException(issues.All).ToBody(), PyJsonFormat.Response));
    }
}
