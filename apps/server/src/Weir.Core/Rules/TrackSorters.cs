using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>The sorter list is not usable (<c>TrackSorterError</c>).</summary>
public sealed class TrackSorterException : Exception
{
    public TrackSorterException()
    {
    }

    public TrackSorterException(string message)
        : base(message)
    {
    }

    public TrackSorterException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// One entry in the ordered sorter list (<c>refiner_track_sorters.TrackSorter</c>). A null
/// <see cref="Value"/> sorts by the field naturally; anything else is a match test.
/// </summary>
public sealed record TrackSorter(string Field, string? Value = null, bool Reversed = false)
{
    /// <summary>A phrase for the selection notes, written the way the operator configured it.</summary>
    public string Describe()
    {
        if (Value is null)
        {
            // Issue #537 item 1: the reference's notes said the opposite of what the code did
            // (claiming "lowest first" for channels/bitrate, which actually rank highest first,
            // and "commentary first" when commentary is in fact ranked last). Fixed here so the
            // note matches the real ranking; see golden/overrides for the affected golden cases.
            if (Field is "default" or "forced")
            {
                return $"{Field} {(Reversed ? "last" : "first")}";
            }

            if (Field == "commentary")
            {
                // Commentary is a demotion: it naturally sorts last, not first.
                return $"{Field} {(Reversed ? "first" : "last")}";
            }

            if (Field is "codec" or "language" or "title")
            {
                return $"{Field} order";
            }

            // The only fields left (bitrate, channels) are both "larger is better".
            var direction = Reversed ? "lowest first" : "highest first";
            return $"{Field} {direction}";
        }

        var prefix = Reversed ? "not " : string.Empty;
        return $"{prefix}{Field} {Value}";
    }
}

/// <summary>
/// The facts a sorter can look at for one track. The planner fills <see cref="Title"/> with the
/// codec name, as the reference's <c>_candidate_as_track</c> does.
/// </summary>
public sealed record SortableTrack
{
    public int Index { get; init; }
    public string Language { get; init; } = string.Empty;
    public string Title { get; init; } = string.Empty;
    public bool Commentary { get; init; }
    public bool Default { get; init; }
    public bool Forced { get; init; }
    public long Channels { get; init; }
    public long Bitrate { get; init; }
    public string Codec { get; init; } = string.Empty;
    public long CodecRank { get; init; }

    /// <summary><c>track.get(field)</c>: a bool, a long, a string, or null for a key the track does not have.</summary>
    internal object? Get(string field) => field switch
    {
        "index" => (long)Index,
        "language" => Language,
        "title" => Title,
        "commentary" => Commentary,
        "default" => Default,
        "forced" => Forced,
        "channels" => Channels,
        "bitrate" => Bitrate,
        "codec" => Codec,
        "codec_rank" => CodecRank,
        _ => null,
    };
}

/// <summary>Lexicographic ordering of sort keys, like Python tuple comparison.</summary>
public sealed class SortKeyComparer : IComparer<IReadOnlyList<long>>
{
    public static SortKeyComparer Instance { get; } = new();

    public int Compare(IReadOnlyList<long>? x, IReadOnlyList<long>? y)
    {
        ArgumentNullException.ThrowIfNull(x);
        ArgumentNullException.ThrowIfNull(y);
        var length = Math.Min(x.Count, y.Count);
        for (var i = 0; i < length; i++)
        {
            var order = x[i].CompareTo(y[i]);
            if (order != 0)
            {
                return order;
            }
        }

        return x.Count.CompareTo(y.Count);
    }
}

/// <summary>
/// The ordered, editable sorter list (<c>refiner_track_sorters.py</c>): key building, storage
/// and the seeded default, which reproduces the ranking Refiner used to hardcode.
/// </summary>
public static partial class TrackSorters
{
    /// <summary>The vocabulary, in the reference's order.</summary>
    public static IReadOnlyList<string> Fields { get; } =
        ["bitrate", "channels", "codec", "language", "title", "default", "forced", "commentary"];

    /// <summary>Exactly the ranking the fixed tuple applied.</summary>
    public static IReadOnlyList<TrackSorter> DefaultAudioSorters { get; } =
    [
        new("commentary"),
        new("channels"),
        new("codec"),
        new("bitrate"),
        new("default"),
    ];

    public static IReadOnlyList<TrackSorter> DefaultSubtitleSorters { get; } =
    [
        new("forced"),
        new("default"),
        new("language"),
    ];

    /// <summary>The three policies as starting points an operator can edit.</summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<TrackSorter>> Presets { get; } =
        new Dictionary<string, IReadOnlyList<TrackSorter>>(StringComparer.Ordinal)
        {
            ["preferred_langs_quality"] = DefaultAudioSorters,
            ["preferred_langs_strict"] = DefaultAudioSorters,
            ["quality_all_languages"] = [new("commentary"), new("channels"), new("codec"), new("bitrate")],
        };

    internal static bool LargerIsBetter(string field) => field is "bitrate" or "channels";

    // Python's \s is str.isspace(), which also covers U+001C..U+001F; .NET's \s does not.
    private const string PyWhitespace = "[\\t\\n\\x0b\\x0c\\r\x001c-\x001f \x0085\x00a0\x1680\x2000-\x200a\x2028\x2029\x202f\x205f\x3000]";

    [GeneratedRegex("^" + PyWhitespace + "*(>=|<=|!=|>|<|=)?" + PyWhitespace + "*(.+?)" + PyWhitespace + "*$", RegexOptions.CultureInvariant)]
    private static partial Regex ComparisonRegex();

    /// <summary>
    /// <c>5.1</c> means six channels, and operators write it that way. Null where the reference
    /// returns <c>None</c>.
    /// </summary>
    internal static double? ParseChannels(string text)
    {
        var raw = Py.Lower(PyStrings.Strip(text));
        if (raw is "mono" or "1.0")
        {
            return 1.0;
        }

        if (raw is "stereo" or "2.0")
        {
            return 2.0;
        }

        if (raw.Contains('.', StringComparison.Ordinal))
        {
            var dot = raw.IndexOf('.', StringComparison.Ordinal);
            var main = Py.TryIntFromText(raw[..dot]);
            var lfe = Py.TryIntFromText(raw[(dot + 1)..]);
            return main is null || lfe is null ? null : main.Value + lfe.Value;
        }

        return Py.TryIntFromText(raw);
    }

    private static bool Compare(object? actual, string op, string expected, string field)
    {
        if (field == "channels")
        {
            var wanted = ParseChannels(expected);
            var have = NumberOrZero(actual);
            return wanted is not null && NumericCompare(have, op, wanted.Value);
        }

        if (field == "bitrate")
        {
            var normalized = Py.Lower(PyStrings.Strip(expected)).TrimEnd('k').Replace("_", string.Empty, StringComparison.Ordinal);
            if (Py.TryFloatFromText(normalized) is not { } wantedNumber)
            {
                return false;
            }

            if (Py.Lower(PyStrings.Strip(expected)).EndsWith('k'))
            {
                wantedNumber *= 1000;
            }

            return NumericCompare(NumberOrZero(actual), op, wantedNumber);
        }

        if (field is "default" or "forced" or "commentary")
        {
            var wantedBool = Py.Lower(PyStrings.Strip(expected)) is "1" or "true" or "yes" or "on";
            var haveBool = Truthy(actual);
            return op == "!=" ? haveBool != wantedBool : haveBool == wantedBool;
        }

        // Text compares case-insensitively; title is a containment test.
        var haveText = Py.Lower(PyStrings.Strip(Truthy(actual) ? Str(actual) : string.Empty));
        var wantText = Py.Lower(PyStrings.Strip(expected));
        var matched = field == "title" ? haveText.Contains(wantText, StringComparison.Ordinal) : haveText == wantText;
        return op == "!=" ? !matched : matched;
    }

    private static bool NumericCompare(double have, string op, double wanted) => op switch
    {
        ">=" => have >= wanted,
        "<=" => have <= wanted,
        ">" => have > wanted,
        "<" => have < wanted,
        "!=" => have != wanted,
        _ => have == wanted,
    };

    private static (string Operator, string Expected) SplitExpression(string value)
    {
        var match = ComparisonRegex().Match(value);
        if (!match.Success)
        {
            return ("=", PyStrings.Strip(value));
        }

        return (match.Groups[1].Success ? match.Groups[1].Value : "=", match.Groups[2].Value);
    }

    private static bool Truthy(object? value) => value switch
    {
        null => false,
        bool b => b,
        long n => n != 0,
        string s => s.Length > 0,
        _ => true,
    };

    private static string Str(object? value) => value switch
    {
        null => "None",
        bool b => b ? "True" : "False",
        long n => n.ToString(CultureInfo.InvariantCulture),
        string s => s,
        _ => value.ToString() ?? string.Empty,
    };

    /// <summary><c>float(actual or 0)</c> / <c>int(actual or 0)</c> over a track fact.</summary>
    private static double NumberOrZero(object? actual) => (double)LongOrZero(actual);

    private static long LongOrZero(object? actual) => actual switch
    {
        long n => n,
        bool b => b ? 1 : 0,
        string s when s.Length > 0 => Py.IntFromText(s),
        _ => 0,
    };

    /// <summary>One sorter's contribution to the sort key. Lower sorts first.</summary>
    public static IReadOnlyList<long> SorterKeyComponent(TrackSorter sorter, SortableTrack track)
    {
        ArgumentNullException.ThrowIfNull(sorter);
        ArgumentNullException.ThrowIfNull(track);
        var actual = track.Get(sorter.Field);

        if (sorter.Value is not null)
        {
            var (op, expected) = SplitExpression(sorter.Value);
            var matched = Compare(actual, op, expected, sorter.Field);
            if (sorter.Reversed)
            {
                matched = !matched;
            }

            return [matched ? 0 : 1];
        }

        if (sorter.Field is "default" or "forced" or "commentary")
        {
            long flag = Truthy(actual) ? 1 : 0;
            // commentary naturally sorts commentary last: it is a demotion.
            if (sorter.Field == "commentary")
            {
                return [sorter.Reversed ? 1 - flag : flag];
            }

            return [sorter.Reversed ? flag : 1 - flag];
        }

        if (LargerIsBetter(sorter.Field))
        {
            var number = LongOrZero(actual);
            // Unknown sorts after known, in both directions.
            long unknown = number <= 0 ? 1 : 0;
            var score = number > 0 ? -Math.Min(number, 2_000_000_000) : 0;
            if (sorter.Reversed)
            {
                score = -score;
            }

            return [unknown, score];
        }

        if (sorter.Field == "codec")
        {
            var rank = track.CodecRank;
            return [sorter.Reversed ? -rank : rank];
        }

        var text = Py.Lower(PyStrings.Strip(Truthy(actual) ? Str(actual) : string.Empty));
        var parts = new List<long> { text.Length == 0 ? 1 : 0 };
        foreach (var rune in PyStrings.Slice(text, 32).EnumerateRunes())
        {
            parts.Add(sorter.Reversed ? -rune.Value : rune.Value);
        }

        return parts;
    }

    /// <summary>The whole key, in the operator's order, ending in the track index.</summary>
    public static IReadOnlyList<long> SortKeyForTrack(IEnumerable<TrackSorter> sorters, SortableTrack track)
    {
        ArgumentNullException.ThrowIfNull(sorters);
        ArgumentNullException.ThrowIfNull(track);
        var parts = new List<long>();
        foreach (var sorter in sorters)
        {
            parts.AddRange(SorterKeyComponent(sorter, track));
        }

        parts.Add(track.Index);
        return parts;
    }

    // --- serialisation ------------------------------------------------------------------

    /// <summary>Read a stored list. Anything unusable yields the seeded default rather than none.</summary>
    public static IReadOnlyList<TrackSorter> Parse(string? raw)
    {
        var text = PyStrings.Strip(raw ?? string.Empty);
        if (text.Length == 0)
        {
            return [.. DefaultAudioSorters];
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(text);
        }
        catch (JsonException)
        {
            return [.. DefaultAudioSorters];
        }

        using (document)
        {
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                return [.. DefaultAudioSorters];
            }

            var result = new List<TrackSorter>();
            foreach (var item in document.RootElement.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                var sorter = ReadEntry(item);
                if (!Fields.Contains(sorter.Field))
                {
                    continue;
                }

                result.Add(sorter);
            }

            return result.Count > 0 ? result : [.. DefaultAudioSorters];
        }
    }

    private static TrackSorter ReadEntry(JsonElement item)
    {
        var field = Py.Lower(PyStrings.Strip(Py.StrOr(Py.Get(item, "field"), string.Empty)));
        var value = Py.Get(item, "value");
        var keptValue = Py.IsStr(value) && PyStrings.Strip(value!.Value.GetString()!).Length > 0 ? value.Value.GetString() : null;
        return new TrackSorter(field, keptValue, Py.Truthy(Py.Get(item, "reversed")));
    }

    /// <summary><c>dump_sorters</c>: compact JSON exactly as <c>json.dumps(..., separators=(",", ":"))</c> writes it.</summary>
    public static string Dump(IEnumerable<TrackSorter> sorters)
    {
        ArgumentNullException.ThrowIfNull(sorters);
        var builder = new StringBuilder("[");
        var first = true;
        foreach (var sorter in sorters)
        {
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            builder.Append("{\"field\":");
            PyJsonWriter.WriteString(builder, sorter.Field, ensureAscii: true);
            builder.Append(",\"value\":");
            if (sorter.Value is null)
            {
                builder.Append("null");
            }
            else
            {
                PyJsonWriter.WriteString(builder, sorter.Value, ensureAscii: true);
            }

            builder.Append(",\"reversed\":").Append(sorter.Reversed ? "true" : "false").Append('}');
        }

        return builder.Append(']').ToString();
    }

    /// <summary>Validate a submitted list, refusing rather than silently dropping entries.</summary>
    public static string Validate(string? raw)
    {
        var text = PyStrings.Strip(raw ?? string.Empty);
        if (text.Length == 0)
        {
            return Dump(DefaultAudioSorters);
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(text);
        }
        catch (JsonException exception)
        {
            throw new TrackSorterException("The track sorter list is not valid JSON.", exception);
        }

        using (document)
        {
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                throw new TrackSorterException("The track sorter list must be a list.");
            }

            var result = new List<TrackSorter>();
            var position = 0;
            foreach (var item in document.RootElement.EnumerateArray())
            {
                position++;
                if (item.ValueKind != JsonValueKind.Object)
                {
                    throw new TrackSorterException($"Sorter {position} is not an object.");
                }

                var sorter = ReadEntry(item);
                if (!Fields.Contains(sorter.Field))
                {
                    throw new TrackSorterException(
                        $"Sorter {position} uses an unknown field {Py.Repr(sorter.Field)}. Known fields: {string.Join(", ", Fields)}.");
                }

                result.Add(sorter);
            }

            return Dump(result);
        }
    }

    /// <summary>The preset for a policy name, or the seeded default.</summary>
    public static IReadOnlyList<TrackSorter> Preset(string? name) =>
        Presets.TryGetValue(Py.Lower(PyStrings.Strip(name ?? string.Empty)), out var preset) ? [.. preset] : [.. DefaultAudioSorters];

    /// <summary>A sentence for the selection notes.</summary>
    public static string Describe(IReadOnlyCollection<TrackSorter> sorters)
    {
        ArgumentNullException.ThrowIfNull(sorters);
        if (sorters.Count == 0)
        {
            return "no ordering configured, so tracks were taken in file order";
        }

        return string.Join(", then ", sorters.Select(s => s.Describe()));
    }
}
