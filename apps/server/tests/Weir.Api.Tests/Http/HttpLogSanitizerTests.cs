using Weir.Api.Http;

namespace Weir.Api.Tests.Http;

/// <summary>
/// <see cref="HttpLogSanitizer.Sanitize"/> is the barrier between request-derived text (a decoded path,
/// an <c>X-Request-ID</c> header, <c>Request.Method</c>) and a text log line. These tests prove the CWE-117
/// shape directly: a value carrying CR, LF and other control characters comes out with none of them, while
/// staying readable.
/// </summary>
public sealed class HttpLogSanitizerTests
{
    // Built from numeric char values, not literal escape sequences, so the test source itself never has to
    // carry a raw control character or a source-breaking line/paragraph separator.
    private const char Nul = (char)0x00;
    private const char Bel = (char)0x07;
    private const char Esc = (char)0x1b;
    private const char Del = (char)0x7f;
    private const char LineSeparator = (char)0x2028;
    private const char ParagraphSeparator = (char)0x2029;
    private const char NextLine = (char)0x0085;

    [Fact]
    public void Sanitize_removes_cr_and_lf_but_keeps_the_value_readable()
    {
        var forged = "GET /health HTTP/1.1\r\nX-Injected: evil";

        var sanitized = HttpLogSanitizer.Sanitize(forged);

        Assert.DoesNotContain('\r', sanitized);
        Assert.DoesNotContain('\n', sanitized);
        Assert.Equal("GET /health HTTP/1.1" + "\\r" + "\\n" + "X-Injected: evil", sanitized);
    }

    [Fact]
    public void Sanitize_escapes_every_control_character_and_leaves_ordinary_text_alone()
    {
        // C0 controls (NUL, BEL, ESC, ...), a tab, CR, LF, the Unicode separators some terminals treat as
        // line breaks, and DEL, mixed in with plain readable text either side.
        var value = "before" + Nul + Bel + Esc + '\t' + "after" + '\r' + '\n' + LineSeparator + ParagraphSeparator + NextLine + "tail" + Del + "end";

        var sanitized = HttpLogSanitizer.Sanitize(value);

        foreach (var c in sanitized)
        {
            Assert.False(char.IsControl(c) || c == LineSeparator || c == ParagraphSeparator, $"sanitized text still contains U+{(int)c:X4}");
        }

        var expected = "before" + "\\x00" + "\\x07" + "\\x1b" + "\\t" + "after" + "\\r" + "\\n" + "\\u2028" + "\\u2029" + "\\u0085" + "tail" + "\\x7f" + "end";
        Assert.Equal(expected, sanitized);
        Assert.Contains("before", sanitized, StringComparison.Ordinal);
        Assert.Contains("after", sanitized, StringComparison.Ordinal);
        Assert.Contains("tail", sanitized, StringComparison.Ordinal);
        Assert.Contains("end", sanitized, StringComparison.Ordinal);
    }

    [Fact]
    public void Sanitize_leaves_text_without_control_characters_unchanged()
    {
        const string clean = "GET /api/v1/processing/jobs?limit=20 (unicode: café, plain text)";

        Assert.Equal(clean, HttpLogSanitizer.Sanitize(clean));
        Assert.Same(clean, HttpLogSanitizer.Sanitize(clean));
    }

    [Fact]
    public void Sanitize_leaves_empty_string_empty()
    {
        Assert.Equal(string.Empty, HttpLogSanitizer.Sanitize(string.Empty));
    }

    [Fact]
    public void Sanitize_rejects_null()
    {
        Assert.Throws<ArgumentNullException>(() => HttpLogSanitizer.Sanitize(null!));
    }
}
