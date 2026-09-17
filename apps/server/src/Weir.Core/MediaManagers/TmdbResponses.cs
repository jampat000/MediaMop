using System.Globalization;
using System.Text;
using Weir.Core.Json;
using Weir.Core.Rules;

namespace Weir.Core.MediaManagers;

/// <summary>Reading a TMDb <c>/search/movie</c> answer (the pure half of <c>integrations.metadata.tmdb_provider</c>).</summary>
public static class TmdbResponses
{
    public const string DefaultBaseUrl = "https://api.themoviedb.org/3";

    /// <summary><c>KNOWN_PROVIDERS</c>.</summary>
    public static readonly IReadOnlyList<string> KnownProviders = ["tmdb"];

    public static readonly TimeSpan Timeout = TimeSpan.FromSeconds(15);

    public const int CacheMaxEntries = 2000;

    public static readonly TimeSpan MinimumBetweenCalls = TimeSpan.FromSeconds(0.25);

    /// <summary>The cache key: base URL, lower-cased title, year.</summary>
    public static string CacheKey(string baseUrl, string cleanedTitle, int? year) =>
        $"{baseUrl}|{cleanedTitle.ToLowerInvariant()}|{(year is { } y && y != 0 ? y.ToString(CultureInfo.InvariantCulture) : string.Empty)}";

    /// <summary>The subject named in details: <c>"Film (2001)"</c>, or the title alone.</summary>
    public static string Subject(string cleanedTitle, int? year) =>
        year is { } y && y != 0 ? $"{cleanedTitle} ({y.ToString(CultureInfo.InvariantCulture)})" : cleanedTitle;

    /// <summary><c>urllib.parse.urlencode</c> of string pairs (<c>quote_plus</c>, UTF-8).</summary>
    public static string UrlEncode(IEnumerable<KeyValuePair<string, string>> pairs)
    {
        ArgumentNullException.ThrowIfNull(pairs);
        return string.Join('&', pairs.Select(pair => QuotePlus(pair.Key) + "=" + QuotePlus(pair.Value)));
    }

    /// <summary><c>urllib.parse.quote_plus</c> with <c>safe=""</c>.</summary>
    public static string QuotePlus(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        var builder = new StringBuilder();
        foreach (var b in Encoding.UTF8.GetBytes(value))
        {
            var c = (char)b;
            if (char.IsAsciiLetterOrDigit(c) || c is '_' or '.' or '-' or '~')
            {
                builder.Append(c);
            }
            else if (c == ' ')
            {
                builder.Append('+');
            }
            else
            {
                builder.Append('%').Append(b.ToString("X2", CultureInfo.InvariantCulture));
            }
        }

        return builder.ToString();
    }

    /// <summary>Everything after the HTTP call succeeded: the body read into a lookup result.</summary>
    public static LookupResult Parse(byte[] body, string subject)
    {
        ArgumentNullException.ThrowIfNull(body);
        PyJson payload;
        try
        {
            payload = PyJsonParser.ParseBytes(body);
        }
        catch (Exception exception) when (exception is PyJsonDecodeException or PyJsonEncodingException)
        {
            return new LookupResult { Status = LookupResult.StatusUnreachable, Detail = "The metadata provider returned something unreadable." };
        }

        if (payload is not PyDict dict || dict.Get("results") is not PyList { Items.Count: > 0 } results)
        {
            return new LookupResult { Status = LookupResult.StatusNoMatch, Detail = $"The metadata provider had no match for {subject}." };
        }

        if (results.Items[0] is not PyDict first)
        {
            return new LookupResult { Status = LookupResult.StatusNoMatch, Detail = $"The metadata provider had no usable match for {subject}." };
        }

        var release = StrOrEmpty(first.Get("release_date"));
        int? parsedYear = release.Length >= 4 && release[..4].All(char.IsAsciiDigit)
            ? int.Parse(release[..4], CultureInfo.InvariantCulture)
            : null;
        var title = PyValues.Or(first.Get("title"), first.Get("original_title"));
        return new LookupResult
        {
            Status = LookupResult.StatusMatched,
            Metadata = new TitleMetadata
            {
                OriginalLanguage = PyStrings.Strip(StrOrEmpty(first.Get("original_language"))).ToLowerInvariant(),
                Title = PyStrings.Strip(StrOrEmpty(title)),
                Year = parsedYear,
                ProviderId = StrOrEmpty(first.Get("id")),
            },
            Detail = $"The metadata provider matched {subject}.",
        };
    }

    /// <summary><c>str(value or "")</c>.</summary>
    private static string StrOrEmpty(PyJson? value) => value is { IsTruthy: true } present ? PyConvert.Str(present) : string.Empty;
}
