using System.Net;
using System.Text;
using Weir.Core.Json;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Tests.MediaManagers;

/// <summary>A request the fake manager received.</summary>
internal sealed record RecordedRequest(HttpMethod Method, Uri Uri, IReadOnlyDictionary<string, string> Headers, string Body, bool FollowRedirects)
{
    public string PathAndQuery => Uri.PathAndQuery;

    public PyJson? Json => Body.Length == 0 ? null : PyJsonParser.Parse(Body);
}

/// <summary>
/// A scripted media manager behind <see cref="IManagerHttpHandlerFactory"/>: answers by method and path, records every
/// request, and can throw the transport failures a real network produces.
/// </summary>
internal sealed class FakeManagerHttp : IManagerHttpHandlerFactory
{
    private readonly List<(HttpMethod Method, string Path, Func<RecordedRequest, HttpResponseMessage> Respond)> _routes = [];
    private readonly Lock _lock = new();

    public List<RecordedRequest> Requests { get; } = [];

    public FakeManagerHttp Route(HttpMethod method, string path, Func<RecordedRequest, HttpResponseMessage> respond)
    {
        lock (_lock)
        {
            _routes.Insert(0, (method, path, respond));
        }

        return this;
    }

    public FakeManagerHttp Json(HttpMethod method, string path, string json, HttpStatusCode status = HttpStatusCode.OK) =>
        Route(method, path, _ => Response(status, json));

    public FakeManagerHttp Throw(HttpMethod method, string path, Exception exception) =>
        Route(method, path, _ => throw exception);

    public static HttpResponseMessage Response(HttpStatusCode status, string? json = null, params (string Name, string Value)[] headers)
    {
        var response = new HttpResponseMessage(status)
        {
            Content = new ByteArrayContent(Encoding.UTF8.GetBytes(json ?? string.Empty)),
        };
        foreach (var (name, value) in headers)
        {
            response.Headers.TryAddWithoutValidation(name, value);
        }

        return response;
    }

    public List<RecordedRequest> RequestsTo(HttpMethod method, string pathPrefix)
    {
        lock (_lock)
        {
            return [.. Requests.Where(r => r.Method == method && r.Uri.AbsolutePath.StartsWith(pathPrefix, StringComparison.Ordinal))];
        }
    }

    public HttpMessageHandler Handler(bool followRedirects) => new RecordingHandler(this, followRedirects);

    private sealed class RecordingHandler(FakeManagerHttp fake, bool followRedirects) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            var headers = request.Headers.Concat(request.Content?.Headers ?? Enumerable.Empty<KeyValuePair<string, IEnumerable<string>>>())
                .ToDictionary(pair => pair.Key, pair => string.Join(", ", pair.Value), StringComparer.OrdinalIgnoreCase);
            var recorded = new RecordedRequest(request.Method, request.RequestUri!, headers, body, followRedirects);
            List<(HttpMethod Method, string Path, Func<RecordedRequest, HttpResponseMessage> Respond)> routes;
            lock (fake._lock)
            {
                fake.Requests.Add(recorded);
                routes = [.. fake._routes];
            }

            foreach (var (method, path, respond) in routes)
            {
                if (method == request.Method && path == request.RequestUri!.AbsolutePath)
                {
                    return respond(recorded);
                }
            }

            throw new HttpRequestException("No connection could be made because the target machine actively refused it.");
        }
    }
}
