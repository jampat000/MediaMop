using System.Text;

namespace Weir.Core.Media;

/// <summary>
/// Splits a byte stream into lines the way iterating a Python text-mode pipe does
/// (<c>encoding="utf-8", errors="replace"</c>, universal newlines): <c>\n</c>, <c>\r\n</c> and a lone <c>\r</c>
/// each end a line. Lines are reported without their ending. Bytes may arrive in any chunking.
/// </summary>
public sealed class UniversalNewlineSplitter
{
    private readonly Decoder _decoder = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: false).GetDecoder();
    private readonly StringBuilder _line = new();
    private readonly Action<string> _onLine;
    private bool _pendingCarriageReturn;

    public UniversalNewlineSplitter(Action<string> onLine)
    {
        ArgumentNullException.ThrowIfNull(onLine);
        _onLine = onLine;
    }

    public void Feed(ReadOnlySpan<byte> bytes)
    {
        var chars = new char[_decoder.GetCharCount(bytes, flush: false)];
        var count = _decoder.GetChars(bytes, chars, flush: false);
        Consume(chars.AsSpan(0, count));
    }

    /// <summary>End of stream: flushes a partial character and reports a final unterminated line.</summary>
    public void Finish()
    {
        var chars = new char[_decoder.GetCharCount([], flush: true)];
        var count = _decoder.GetChars([], chars, flush: true);
        Consume(chars.AsSpan(0, count));
        if (_pendingCarriageReturn)
        {
            _pendingCarriageReturn = false;
            Emit();
        }
        else if (_line.Length > 0)
        {
            Emit();
        }
    }

    private void Consume(ReadOnlySpan<char> chars)
    {
        foreach (var c in chars)
        {
            if (_pendingCarriageReturn)
            {
                _pendingCarriageReturn = false;
                Emit();
                if (c == '\n')
                {
                    continue;
                }
            }

            if (c == '\r')
            {
                _pendingCarriageReturn = true;
            }
            else if (c == '\n')
            {
                Emit();
            }
            else
            {
                _line.Append(c);
            }
        }
    }

    private void Emit()
    {
        var text = _line.ToString();
        _line.Clear();
        _onLine(text);
    }
}
