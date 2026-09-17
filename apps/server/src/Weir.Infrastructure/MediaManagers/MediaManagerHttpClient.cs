using System.Globalization;
using System.Net.Http.Headers;
using System.Text;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Notifications;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>
/// The HTTP transport for media managers and the metadata provider. A seam so tests answer with a fake handler.
/// </summary>
public interface IManagerHttpHandlerFactory
{
    /// <summary>
    /// A handler the caller does not dispose. <paramref name="followRedirects"/> mirrors the Python client in use:
    /// <c>urllib</c> follows redirects, <c>httpx.post</c> does not.
    /// </summary>
    HttpMessageHandler Handler(bool followRedirects);
}

/// <summary>Two shared <see cref="SocketsHttpHandler"/>s, one following redirects (as urllib does, up to ten) and one not.</summary>
public sealed class SocketsManagerHttpHandlerFactory : IManagerHttpHandlerFactory, IDisposable
{
    private readonly SocketsHttpHandler _following = new() { AllowAutoRedirect = true, MaxAutomaticRedirections = 10, PooledConnectionLifetime = TimeSpan.FromMinutes(2) };
    private readonly SocketsHttpHandler _notFollowing = new() { AllowAutoRedirect = false, PooledConnectionLifetime = TimeSpan.FromMinutes(2) };

    public HttpMessageHandler Handler(bool followRedirects) => followRedirects ? _following : _notFollowing;

    public void Dispose()
    {
        _following.Dispose();
        _notFollowing.Dispose();
    }
}

/// <summary>
/// A narrow JSON client for one media manager (port of <c>manager_http.MediaManagerHttpClient</c>). The base URL must
/// be a plain http(s) address with no credentials, query or fragment, and request paths must be relative, so a saved
/// connection cannot be turned into a request against an arbitrary host (ADR-0015).
/// </summary>
public sealed class MediaManagerHttpClient
{
    private readonly string _base;
    private readonly string _apiKey;
    private readonly TimeSpan _timeout;
    private readonly IManagerHttpHandlerFactory _handlers;

    /// <exception cref="MediaManagerHttpException">The base URL is not a plain http(s) address.</exception>
    public MediaManagerHttpClient(string baseUrl, string apiKey, IManagerHttpHandlerFactory handlers, TimeSpan? timeout = null)
    {
        ArgumentNullException.ThrowIfNull(baseUrl);
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
        try
        {
            _base = ExternalUrlPolicy.NormalizeLocalServiceBaseUrl(baseUrl);
        }
        catch (PyValueErrorException exception)
        {
            throw new MediaManagerHttpException(exception.Message, exception);
        }

        _apiKey = apiKey ?? string.Empty;
        _timeout = timeout ?? TimeSpan.FromSeconds(30);
    }

    /// <summary><c>_url</c>: refuses an absolute path, prefixes a slash, appends urlencoded parameters.</summary>
    public string Url(string path, IReadOnlyList<KeyValuePair<string, string>>? parameters = null)
    {
        ArgumentNullException.ThrowIfNull(path);
        if (SplitUrl.Parse(path).Scheme.Length > 0)
        {
            throw new MediaManagerHttpException("A media manager API path must be relative.");
        }

        var url = _base + (path.StartsWith('/') ? path : "/" + path);
        return parameters is { Count: > 0 } ? url + "?" + TmdbResponses.UrlEncode(parameters) : url;
    }

    /// <summary><c>get_json</c>. Booleans in <paramref name="parameters"/> are sent as <c>1</c>/<c>0</c>, as Python does here.</summary>
    public Task<PyJson?> GetJsonAsync(string path, IReadOnlyList<KeyValuePair<string, object>>? parameters = null, CancellationToken cancellationToken = default)
    {
        var flat = parameters?.Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value switch
        {
            bool flag => flag ? "1" : "0",
            IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
            _ => Convert.ToString(pair.Value, CultureInfo.InvariantCulture) ?? string.Empty,
        })).ToList();
        var request = new HttpRequestMessage(HttpMethod.Get, Url(path, flat));
        request.Headers.TryAddWithoutValidation("X-Api-Key", _apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        return SendAsync(request, allowEmpty: false, cancellationToken);
    }

    /// <summary>
    /// <c>post_json</c>: the body as <c>json.dumps(body)</c>. <paramref name="acceptedStatuses"/> widens the
    /// success set beyond 200/201/204 for an endpoint verified to answer differently (Deluno's file-changed
    /// answers 202 Accepted, #507); every other caller keeps Python's exact three.
    /// </summary>
    public Task<PyJson?> PostJsonAsync(string path, PyDict body, IReadOnlyCollection<int>? acceptedStatuses = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(body);
        var request = new HttpRequestMessage(HttpMethod.Post, Url(path))
        {
            Content = JsonContent(body),
        };
        request.Headers.TryAddWithoutValidation("X-Api-Key", _apiKey);
        return SendAsync(request, allowEmpty: false, cancellationToken, acceptedStatuses);
    }

    /// <summary><c>put_json</c>.</summary>
    public async Task PutJsonAsync(string path, PyDict body, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(body);
        var request = new HttpRequestMessage(HttpMethod.Put, Url(path))
        {
            Content = JsonContent(body),
        };
        request.Headers.TryAddWithoutValidation("X-Api-Key", _apiKey);
        await SendAsync(request, allowEmpty: true, cancellationToken).ConfigureAwait(false);
    }

    /// <summary><c>delete</c>: success is the status code alone. Booleans are sent as <c>true</c>/<c>false</c>, which is how ASP.NET binds them.</summary>
    public async Task DeleteAsync(string path, IReadOnlyList<KeyValuePair<string, object>>? parameters = null, CancellationToken cancellationToken = default)
    {
        var flat = parameters?.Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value switch
        {
            bool flag => flag ? "true" : "false",
            IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
            _ => Convert.ToString(pair.Value, CultureInfo.InvariantCulture) ?? string.Empty,
        })).ToList();
        var request = new HttpRequestMessage(HttpMethod.Delete, Url(path, flat));
        request.Headers.TryAddWithoutValidation("X-Api-Key", _apiKey);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        await SendAsync(request, allowEmpty: true, cancellationToken).ConfigureAwait(false);
    }

    /// <summary><c>health_ok</c>.</summary>
    public Task HealthOkAsync(string path, CancellationToken cancellationToken = default) => GetJsonAsync(path, cancellationToken: cancellationToken);

    private static ByteArrayContent JsonContent(PyDict body)
    {
        var content = new ByteArrayContent(PyJsonWriter.DumpsUtf8(body, PyJsonFormat.Default));
        content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
        return content;
    }

    private static readonly int[] DefaultAcceptedStatuses = [200, 201, 204];

    /// <summary><c>_read_json</c>.</summary>
    private async Task<PyJson?> SendAsync(HttpRequestMessage request, bool allowEmpty, CancellationToken cancellationToken, IReadOnlyCollection<int>? acceptedStatuses = null)
    {
        using (request)
        {
            using var client = new HttpClient(_handlers.Handler(followRedirects: true), disposeHandler: false) { Timeout = _timeout };
            HttpResponseMessage response;
            try
            {
                response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (IsTransportFailure(exception, cancellationToken))
            {
                throw Unreachable(exception);
            }

            using (response)
            {
                byte[] raw;
                try
                {
                    raw = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
                }
                catch (Exception exception) when (IsTransportFailure(exception, cancellationToken))
                {
                    throw Unreachable(exception);
                }

                var status = (int)response.StatusCode;
                if (status is < 200 or >= 300)
                {
                    var text = PyStrings.Slice(new UTF8Encoding(false, false).GetString(raw), 500);
                    if (status == 429)
                    {
                        throw new MediaManagerRateLimitedException(
                            $"HTTP 429: {text}",
                            RetryAfterSeconds(response.Headers.TryGetValues("Retry-After", out var values) ? values.First() : null));
                    }

                    throw new MediaManagerHttpException($"HTTP {status.ToString(CultureInfo.InvariantCulture)}: {text}");
                }

                if (raw.Length == 0 && allowEmpty)
                {
                    return null;
                }

                if (!(acceptedStatuses ?? DefaultAcceptedStatuses).Contains(status))
                {
                    throw new MediaManagerHttpException($"unexpected HTTP {status.ToString(CultureInfo.InvariantCulture)}");
                }

                if (raw.Length == 0)
                {
                    return null;
                }

                // #544 item 1: Python's json.loads raises ValueError here, uncaught, so a 2xx answer that is not
                // JSON (an HTML login page from a reverse proxy, most often) surfaced as a 500. Classified instead,
                // so a connection test and the capabilities list report a plain "this is not that API" message.
                try
                {
                    return PyJsonParser.Parse(new UTF8Encoding(false, true).GetString(raw));
                }
                catch (Exception exception) when (exception is PyJsonDecodeException or DecoderFallbackException)
                {
                    throw new MediaManagerHttpException(
                        $"HTTP {status.ToString(CultureInfo.InvariantCulture)}: the response was not valid JSON. " +
                        "This does not look like a Sonarr, Radarr or Deluno API at this address.",
                        exception);
                }
            }
        }
    }

    /// <summary><c>_retry_after_seconds</c>: a non-negative delay in seconds, or null (an HTTP-date is not acted on).</summary>
    public static double? RetryAfterSeconds(string? raw)
    {
        if (raw is null)
        {
            return null;
        }

        var text = PyStrings.Strip(raw);
        if (text.Length == 0 || !double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var seconds) || double.IsNaN(seconds))
        {
            return null;
        }

        return seconds >= 0 ? seconds : null;
    }

    internal static bool IsTransportFailure(Exception exception, CancellationToken cancellationToken) =>
        exception is HttpRequestException or IOException ||
        (exception is TaskCanceledException && !cancellationToken.IsCancellationRequested);

    internal static MediaManagerUnreachableException Unreachable(Exception exception)
    {
        var message = exception is TaskCanceledException ? "timed out" : Innermost(exception).Message;
        return new MediaManagerUnreachableException($"<urlopen error {message}>", exception);
    }

    private static Exception Innermost(Exception exception)
    {
        while (exception.InnerException is not null)
        {
            exception = exception.InnerException;
        }

        return exception;
    }
}
