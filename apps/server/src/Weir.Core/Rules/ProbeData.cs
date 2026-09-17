using System.Text.Json;
using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>
/// ffprobe data the rules engine could not read, raised where the Python reference raises.
/// <see cref="PythonError"/> names the Python exception (<c>KeyError</c>, <c>ValueError</c>,
/// <c>TypeError</c>, <c>AttributeError</c>, <c>OverflowError</c>) so callers and the parity
/// tests can tell the cases apart the same way.
/// </summary>
public sealed class RulesInputException : Exception
{
    public RulesInputException()
    {
        PythonError = "ValueError";
    }

    public RulesInputException(string message)
        : base(message)
    {
        PythonError = "ValueError";
    }

    public RulesInputException(string message, Exception innerException)
        : base(message, innerException)
    {
        PythonError = "ValueError";
    }

    public RulesInputException(string pythonError, string message)
        : base(message)
    {
        PythonError = pythonError;
    }

    public string PythonError { get; }
}

/// <summary>
/// One stream from <c>ffprobe -show_streams -of json</c>.
/// </summary>
/// <remarks>
/// ffprobe's values are loosely typed (bit rates and frame counts arrive as strings, a
/// disposition flag can be a string), and the reference reads them with Python's own
/// conversions. The raw object stays available as <see cref="Json"/>; the typed properties
/// below are lenient readings for callers, and the rules use the exact conversions internally.
/// </remarks>
public sealed record ProbeStreamInfo
{
    public ProbeStreamInfo(JsonElement json)
    {
        if (json.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("An ffprobe stream is a JSON object.", nameof(json));
        }

        Json = json.Clone();
    }

    /// <summary>The stream exactly as ffprobe reported it.</summary>
    public JsonElement Json { get; }

    public static ProbeStreamInfo Parse(string json)
    {
        using var document = JsonDocument.Parse(json);
        return new ProbeStreamInfo(document.RootElement);
    }

    /// <summary><c>stream.get(name)</c>: null when absent; a JSON <c>null</c> is returned as an element.</summary>
    public JsonElement? Get(string name) => Py.Get(Json, name);

    /// <summary><c>index</c> when it reads as an integer.</summary>
    public long? Index => Py.TryInt(Get("index"), out var index) ? index : null;

    /// <summary><c>codec_type</c>, stripped and lower-cased; empty when absent or not a string.</summary>
    public string CodecType => Py.IsStr(Get("codec_type")) ? Py.Lower(PyStrings.Strip(Get("codec_type")!.Value.GetString()!)) : string.Empty;

    /// <summary><c>codec_name</c> as written; empty when absent.</summary>
    public string CodecName => Py.StrOr(Get("codec_name"), string.Empty);

    /// <summary>
    /// The tags as the rules read them, string-valued entries only. Issue #537 item 5: the port
    /// originally ran every value through <c>str()</c>, so a JSON <c>null</c> language became the
    /// text <c>"none"</c> (read as a real, if bogus, language code) and a list- or dict-valued
    /// title could still match a "commentary" substring test after being stringified. ffprobe never
    /// legitimately puts a non-string value in a tag, so a non-string value is now treated the same
    /// as an absent key; empty when tags are not an object.
    /// </summary>
    public IReadOnlyDictionary<string, string> Tags
    {
        get
        {
            var tags = Get("tags");
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            if (!Py.Truthy(tags) || !Py.IsDict(tags))
            {
                return result;
            }

            foreach (var (key, value) in Py.Items(tags!.Value))
            {
                if (Py.IsStr(value))
                {
                    result[key] = value.GetString()!;
                }
            }

            return result;
        }
    }

    /// <summary>
    /// The disposition flags as the reference reads them (<c>_stream_disposition</c>): each value
    /// through <c>int()</c>, skipping values that do not convert.
    /// </summary>
    public IReadOnlyDictionary<string, long> Disposition
    {
        get
        {
            var disposition = Get("disposition");
            var result = new Dictionary<string, long>(StringComparer.Ordinal);
            if (!Py.Truthy(disposition) || !Py.IsDict(disposition))
            {
                return result;
            }

            foreach (var (key, value) in Py.Items(disposition!.Value))
            {
                if (Py.TryInt(value, out var flag))
                {
                    result[key] = flag;
                }
            }

            return result;
        }
    }

    /// <summary><c>tags.get(name)</c> after <see cref="Tags"/>, or null.</summary>
    public string? Tag(string name) => Tags.TryGetValue(name, out var value) ? value : null;
}

/// <summary>The whole <c>ffprobe</c> JSON document for one file.</summary>
public sealed record ProbeResult
{
    public ProbeResult(JsonElement json)
    {
        Json = json.Clone();
    }

    public JsonElement Json { get; }

    public static ProbeResult Parse(string json)
    {
        using var document = JsonDocument.Parse(json);
        return new ProbeResult(document.RootElement);
    }

    /// <summary>
    /// The entries of <c>streams</c> that are objects, in file order; empty when the document has
    /// no stream list. Entries that are not objects are skipped, as the reference skips them.
    /// </summary>
    public IReadOnlyList<ProbeStreamInfo> Streams
    {
        get
        {
            if (Json.ValueKind != JsonValueKind.Object)
            {
                return [];
            }

            var streams = Py.Get(Json, "streams");
            if (!Py.IsList(streams))
            {
                return [];
            }

            return streams!.Value.EnumerateArray()
                .Where(s => s.ValueKind == JsonValueKind.Object)
                .Select(s => new ProbeStreamInfo(s))
                .ToList();
        }
    }

    /// <summary>
    /// The entries of <c>chapters</c> that are objects (#498: present when the probe ran with
    /// <c>-show_chapters</c>, see <see cref="Weir.Core.Media.FfmpegCommands.BuildFfprobeArgv"/>); empty when the
    /// document has no chapter list, including a probe made before that flag existed.
    /// </summary>
    public IReadOnlyList<JsonElement> Chapters
    {
        get
        {
            if (Json.ValueKind != JsonValueKind.Object)
            {
                return [];
            }

            var chapters = Py.Get(Json, "chapters");
            if (!Py.IsList(chapters))
            {
                return [];
            }

            return chapters!.Value.EnumerateArray().Where(c => c.ValueKind == JsonValueKind.Object).ToList();
        }
    }
}
