using System.Globalization;
using System.Numerics;
using System.Text;

namespace Weir.Core.Json;

/// <summary><c>json.JSONDecodeError</c>: the C scanner's message and the character position.</summary>
public sealed class PyJsonDecodeException : Exception
{
    public PyJsonDecodeException()
    {
        Detail = string.Empty;
    }

    public PyJsonDecodeException(string message)
        : base(message)
    {
        Detail = message;
    }

    public PyJsonDecodeException(string message, Exception innerException)
        : base(message, innerException)
    {
        Detail = message;
    }

    public PyJsonDecodeException(string detail, int position)
        : base($"{detail}: char {position}")
    {
        Detail = detail;
        Position = position;
    }

    /// <summary>The message without position, e.g. <c>Expecting value</c>.</summary>
    public string Detail { get; }

    public int Position { get; }
}

/// <summary>Bytes that are not text in the detected encoding (Python raises <c>UnicodeDecodeError</c>).</summary>
public sealed class PyJsonEncodingException : Exception
{
    public PyJsonEncodingException()
    {
    }

    public PyJsonEncodingException(string message)
        : base(message)
    {
    }

    public PyJsonEncodingException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// <c>json.loads</c> with CPython 3.11's C scanner behaviour: the same accepted input (including
/// <c>NaN</c> and <c>Infinity</c>), the same error messages and positions.
/// </summary>
public static class PyJsonParser
{
    private static readonly UTF8Encoding StrictUtf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    /// <summary><c>json.loads(bytes)</c>: detect the encoding the way <c>json.detect_encoding</c> does, then parse.</summary>
    public static PyJson ParseBytes(ReadOnlySpan<byte> bytes) => Parse(DecodeBytes(bytes));

    public static string DecodeBytes(ReadOnlySpan<byte> b)
    {
        try
        {
            if (b.StartsWith(new byte[] { 0x00, 0x00, 0xFE, 0xFF }) || b.StartsWith(new byte[] { 0xFF, 0xFE, 0x00, 0x00 }))
            {
                return new UTF32Encoding(bigEndian: b[0] == 0, byteOrderMark: true, throwOnInvalidCharacters: true).GetString(b[4..]);
            }

            if (b.StartsWith(new byte[] { 0xFE, 0xFF }) || b.StartsWith(new byte[] { 0xFF, 0xFE }))
            {
                return new UnicodeEncoding(bigEndian: b[0] == 0xFE, byteOrderMark: true, throwOnInvalidBytes: true).GetString(b[2..]);
            }

            if (b.StartsWith(new byte[] { 0xEF, 0xBB, 0xBF }))
            {
                return StrictUtf8.GetString(b[3..]);
            }

            if (b.Length >= 4)
            {
                if (b[0] == 0)
                {
                    return b[1] != 0
                        ? new UnicodeEncoding(bigEndian: true, byteOrderMark: false, throwOnInvalidBytes: true).GetString(b)
                        : new UTF32Encoding(bigEndian: true, byteOrderMark: false, throwOnInvalidCharacters: true).GetString(b);
                }

                if (b[1] == 0)
                {
                    return b[2] != 0 || b[3] != 0
                        ? new UnicodeEncoding(bigEndian: false, byteOrderMark: false, throwOnInvalidBytes: true).GetString(b)
                        : new UTF32Encoding(bigEndian: false, byteOrderMark: false, throwOnInvalidCharacters: true).GetString(b);
                }
            }
            else if (b.Length == 2)
            {
                if (b[0] == 0)
                {
                    return new UnicodeEncoding(bigEndian: true, byteOrderMark: false, throwOnInvalidBytes: true).GetString(b);
                }

                if (b[1] == 0)
                {
                    return new UnicodeEncoding(bigEndian: false, byteOrderMark: false, throwOnInvalidBytes: true).GetString(b);
                }
            }

            return StrictUtf8.GetString(b);
        }
        catch (DecoderFallbackException exception)
        {
            throw new PyJsonEncodingException("The body is not valid text.", exception);
        }
        catch (ArgumentException exception)
        {
            throw new PyJsonEncodingException("The body is not valid text.", exception);
        }
    }

    /// <summary><c>json.loads(str)</c>.</summary>
    public static PyJson Parse(string s)
    {
        ArgumentNullException.ThrowIfNull(s);
        if (s.StartsWith('﻿'))
        {
            throw new PyJsonDecodeException("Unexpected UTF-8 BOM (decode using utf-8-sig)", 0);
        }

        var idx = SkipWhitespace(s, 0);
        var value = ScanOnceOrExpectingValue(s, idx, out var end);
        end = SkipWhitespace(s, end);
        if (end != s.Length)
        {
            throw new PyJsonDecodeException("Extra data", end);
        }

        return value;
    }

    private static int SkipWhitespace(string s, int idx)
    {
        while (idx < s.Length && s[idx] is ' ' or '\t' or '\n' or '\r')
        {
            idx++;
        }

        return idx;
    }

    private static PyJson ScanOnceOrExpectingValue(string s, int idx, out int end)
    {
        var value = ScanOnce(s, idx, out end);
        return value ?? throw new PyJsonDecodeException("Expecting value", idx);
    }

    /// <summary>Returns <see langword="null"/> where the C scanner raises <c>StopIteration(idx)</c>.</summary>
    private static PyJson? ScanOnce(string s, int idx, out int end)
    {
        end = idx;
        if (idx >= s.Length)
        {
            return null;
        }

        var c = s[idx];
        switch (c)
        {
            case '"':
                return new PyStr(ScanString(s, idx + 1, out end));
            case '{':
                return ParseObject(s, idx + 1, out end);
            case '[':
                return ParseArray(s, idx + 1, out end);
            case 'n' when idx + 4 <= s.Length && string.CompareOrdinal(s, idx, "null", 0, 4) == 0:
                end = idx + 4;
                return PyNull.Instance;
            case 't' when idx + 4 <= s.Length && string.CompareOrdinal(s, idx, "true", 0, 4) == 0:
                end = idx + 4;
                return PyBool.True;
            case 'f' when idx + 5 <= s.Length && string.CompareOrdinal(s, idx, "false", 0, 5) == 0:
                end = idx + 5;
                return PyBool.False;
            case 'N' when idx + 3 <= s.Length && string.CompareOrdinal(s, idx, "NaN", 0, 3) == 0:
                end = idx + 3;
                return new PyFloat(double.NaN);
            case 'I' when idx + 8 <= s.Length && string.CompareOrdinal(s, idx, "Infinity", 0, 8) == 0:
                end = idx + 8;
                return new PyFloat(double.PositiveInfinity);
            case '-' when idx + 9 <= s.Length && string.CompareOrdinal(s, idx, "-Infinity", 0, 9) == 0:
                end = idx + 9;
                return new PyFloat(double.NegativeInfinity);
            default:
                return MatchNumber(s, idx, out end);
        }
    }

    private static PyJson? MatchNumber(string s, int start, out int end)
    {
        end = start;
        var idx = start;
        if (idx < s.Length && s[idx] == '-')
        {
            idx++;
        }

        if (idx >= s.Length || !char.IsAsciiDigit(s[idx]))
        {
            return null;
        }

        if (s[idx] == '0')
        {
            idx++;
        }
        else
        {
            while (idx < s.Length && char.IsAsciiDigit(s[idx]))
            {
                idx++;
            }
        }

        var isFloat = false;
        if (idx + 1 < s.Length && s[idx] == '.' && char.IsAsciiDigit(s[idx + 1]))
        {
            isFloat = true;
            idx += 2;
            while (idx < s.Length && char.IsAsciiDigit(s[idx]))
            {
                idx++;
            }
        }

        if (idx < s.Length && s[idx] is 'e' or 'E')
        {
            var e = idx + 1;
            if (e < s.Length && s[e] is '+' or '-')
            {
                e++;
            }

            if (e < s.Length && char.IsAsciiDigit(s[e]))
            {
                isFloat = true;
                idx = e;
                while (idx < s.Length && char.IsAsciiDigit(s[idx]))
                {
                    idx++;
                }
            }
        }

        end = idx;
        var text = s[start..idx];
        return isFloat
            ? new PyFloat(double.Parse(text, NumberStyles.Float, CultureInfo.InvariantCulture))
            : new PyInt(BigInteger.Parse(text, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture));
    }

    private static PyDict ParseObject(string s, int idx, out int end)
    {
        var result = new PyDict();
        idx = SkipWhitespace(s, idx);
        if (idx < s.Length && s[idx] == '}')
        {
            end = idx + 1;
            return result;
        }

        while (true)
        {
            if (idx >= s.Length || s[idx] != '"')
            {
                throw new PyJsonDecodeException("Expecting property name enclosed in double quotes", idx);
            }

            var key = ScanString(s, idx + 1, out idx);
            idx = SkipWhitespace(s, idx);
            if (idx >= s.Length || s[idx] != ':')
            {
                throw new PyJsonDecodeException("Expecting ':' delimiter", idx);
            }

            idx = SkipWhitespace(s, idx + 1);
            var value = ScanOnceOrExpectingValue(s, idx, out idx);
            result.Set(key, value);
            idx = SkipWhitespace(s, idx);
            if (idx < s.Length && s[idx] == '}')
            {
                end = idx + 1;
                return result;
            }

            if (idx >= s.Length || s[idx] != ',')
            {
                throw new PyJsonDecodeException("Expecting ',' delimiter", idx);
            }

            idx = SkipWhitespace(s, idx + 1);
        }
    }

    private static PyList ParseArray(string s, int idx, out int end)
    {
        var result = new PyList();
        idx = SkipWhitespace(s, idx);
        if (idx < s.Length && s[idx] == ']')
        {
            end = idx + 1;
            return result;
        }

        while (true)
        {
            var value = ScanOnceOrExpectingValue(s, idx, out idx);
            result.Items.Add(value);
            idx = SkipWhitespace(s, idx);
            if (idx < s.Length && s[idx] == ']')
            {
                end = idx + 1;
                return result;
            }

            if (idx >= s.Length || s[idx] != ',')
            {
                throw new PyJsonDecodeException("Expecting ',' delimiter", idx);
            }

            idx = SkipWhitespace(s, idx + 1);
        }
    }

    /// <summary><c>scanstring_unicode</c> with <c>strict=True</c>; <paramref name="start"/> is just after the opening quote.</summary>
    private static string ScanString(string s, int start, out int end)
    {
        var begin = start - 1;
        var builder = new StringBuilder();
        var next = start;
        var len = s.Length;
        while (true)
        {
            var chunkStart = next;
            while (next < len)
            {
                var c = s[next];
                if (c is '"' or '\\')
                {
                    break;
                }

                if (c <= 0x1F)
                {
                    throw new PyJsonDecodeException("Invalid control character at", next);
                }

                next++;
            }

            if (next >= len)
            {
                throw new PyJsonDecodeException("Unterminated string starting at", begin);
            }

            builder.Append(s, chunkStart, next - chunkStart);
            next++;
            if (s[next - 1] == '"')
            {
                end = next;
                return builder.ToString();
            }

            if (next == len)
            {
                throw new PyJsonDecodeException("Unterminated string starting at", begin);
            }

            var escape = s[next];
            if (escape != 'u')
            {
                end = next + 1;
                char? mapped = escape switch
                {
                    '"' => '"',
                    '\\' => '\\',
                    '/' => '/',
                    'b' => '\b',
                    'f' => '\f',
                    'n' => '\n',
                    'r' => '\r',
                    't' => '\t',
                    _ => null,
                };
                if (mapped is null)
                {
                    throw new PyJsonDecodeException("Invalid \\escape", end - 2);
                }

                builder.Append(mapped.Value);
                next = end;
                continue;
            }

            next++;
            var hexEnd = next + 4;
            if (hexEnd >= len)
            {
                throw new PyJsonDecodeException("Invalid \\uXXXX escape", next - 1);
            }

            var code = ReadHex4(s, next, hexEnd);
            next = hexEnd;
            if (char.IsHighSurrogate((char)code) && hexEnd + 6 < len && s[hexEnd] == '\\' && s[hexEnd + 1] == 'u')
            {
                var low = ReadHex4(s, hexEnd + 2, hexEnd + 6);
                if (char.IsLowSurrogate((char)low))
                {
                    builder.Append((char)code).Append((char)low);
                    next = hexEnd + 6;
                    continue;
                }
            }

            builder.Append((char)code);
        }
    }

    private static int ReadHex4(string s, int from, int to)
    {
        var value = 0;
        for (var i = from; i < to; i++)
        {
            var digit = s[i] switch
            {
                >= '0' and <= '9' => s[i] - '0',
                >= 'a' and <= 'f' => s[i] - 'a' + 10,
                >= 'A' and <= 'F' => s[i] - 'A' + 10,
                _ => -1,
            };
            if (digit < 0)
            {
                throw new PyJsonDecodeException("Invalid \\uXXXX escape", to - 5);
            }

            value = (value << 4) | digit;
        }

        return value;
    }
}
