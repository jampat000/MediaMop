using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.Logging;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Net;

namespace Weir.Api.Http;

/// <summary>Response markers shared by the middleware.</summary>
internal static class ResponseMarkers
{
    /// <summary>
    /// Set when the outermost error handler answers 500: Starlette's <c>ServerErrorMiddleware</c> sits outside
    /// every other middleware, so its response carries none of their headers.
    /// </summary>
    public const string ServerError = "weir.server_error";

    /// <summary>The address the connection really came from, before forwarded headers are applied.</summary>
    public const string ConnectionPeer = "weir.connection_peer";

    public static bool IsServerError(HttpContext context) => context.Items.ContainsKey(ServerError);
}

/// <summary>
/// Starlette's <c>ServerErrorMiddleware</c>: an unhandled exception is answered with a plain
/// <c>Internal Server Error</c> (the exception was already logged by the request context).
/// </summary>
public sealed class ServerErrorMiddleware
{
    private readonly RequestDelegate _next;

    public ServerErrorMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        try
        {
            await _next(context).ConfigureAwait(false);
        }
        catch (Exception) when (!context.Response.HasStarted && !context.RequestAborted.IsCancellationRequested)
        {
            context.Items[ResponseMarkers.ServerError] = true;
            context.Response.Clear();
            await PyResponses.WritePlainTextAsync(context, StatusCodes.Status500InternalServerError, "Internal Server Error").ConfigureAwait(false);
        }
    }
}

/// <summary>
/// Forwarded headers, honoured only from a peer inside <c>WEIR_TRUSTED_PROXY_IPS</c> (none by default).
/// </summary>
/// <remarks>
/// Deliberate fix (#528): the Python server runs under uvicorn, whose default <c>forwarded_allow_ips</c>
/// trusts 127.0.0.1 even when no proxy is configured, so any local process could rotate
/// <c>X-Forwarded-For</c> past the login rate limit or claim HTTPS.
/// </remarks>
public static class TrustedForwardedHeaders
{
    public static IApplicationBuilder UseTrustedForwardedHeaders(this IApplicationBuilder app, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(app);
        ArgumentNullException.ThrowIfNull(options);
        app.Use((context, next) =>
        {
            context.Items[ResponseMarkers.ConnectionPeer] = ApiRequest.DefaultClientHost(context);
            return next(context);
        });

        var forwarded = new ForwardedHeadersOptions
        {
            ForwardedHeaders = ForwardedHeaders.XForwardedFor,
            ForwardLimit = null,
        };
        forwarded.KnownProxies.Clear();
        forwarded.KnownIPNetworks.Clear();
#pragma warning disable ASPDEPR005 // The legacy list still defaults to loopback and is still consulted.
        forwarded.KnownNetworks.Clear();
#pragma warning restore ASPDEPR005
        foreach (var raw in options.TrustedProxyIps)
        {
            if (PyIpNetwork.TryParse(raw.Trim(), strict: false, out var network))
            {
                forwarded.KnownIPNetworks.Add(new System.Net.IPNetwork(new IPAddress(network.AddressBytes()), network.PrefixLength));
            }
        }

        // With both lists empty ASP.NET trusts every peer, so the middleware only runs when a proxy is configured.
        return forwarded.KnownIPNetworks.Count == 0 ? app : app.UseForwardedHeaders(forwarded);
    }
}

/// <summary>Starlette's <c>CORSMiddleware</c> as the Python app configures it when <c>WEIR_CORS_ORIGINS</c> is set.</summary>
public sealed class CorsMiddleware
{
    private static readonly string[] AllowMethods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"];
    private static readonly string[] AllowHeaders =
        [.. new[] { "Accept", "Accept-Language", "Content-Language", "Content-Type", "X-CSRF-Token", "X-Requested-With" }.Order(StringComparer.Ordinal)];

    private readonly RequestDelegate _next;
    private readonly HashSet<string> _origins;
    private readonly HashSet<string> _allowHeadersLower;

    public CorsMiddleware(RequestDelegate next, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        _next = next;
        _origins = new HashSet<string>(options.CorsOrigins, StringComparer.Ordinal);
        _allowHeadersLower = new HashSet<string>(AllowHeaders.Select(h => h.ToLowerInvariant()), StringComparer.Ordinal);
    }

    public async Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var originValues = context.Request.Headers.Origin;
        if (originValues.Count == 0)
        {
            await _next(context).ConfigureAwait(false);
            return;
        }

        var origin = originValues[0] ?? string.Empty;
        if (context.Request.Method == HttpMethods.Options && context.Request.Headers.ContainsKey("Access-Control-Request-Method"))
        {
            await PreflightAsync(context, origin).ConfigureAwait(false);
            return;
        }

        context.Response.OnStarting(() =>
        {
            if (!ResponseMarkers.IsServerError(context))
            {
                var headers = context.Response.Headers;
                headers["Access-Control-Allow-Credentials"] = "true";
                if (_origins.Contains(origin))
                {
                    headers["Access-Control-Allow-Origin"] = origin;
                    var vary = headers.Vary.ToString();
                    headers.Vary = vary.Length > 0 ? vary + ", Origin" : "Origin";
                }
            }

            return Task.CompletedTask;
        });
        await _next(context).ConfigureAwait(false);
    }

    private Task PreflightAsync(HttpContext context, string origin)
    {
        var headers = context.Response.Headers;
        headers.Vary = "Origin";
        headers["Access-Control-Allow-Methods"] = string.Join(", ", AllowMethods);
        headers["Access-Control-Max-Age"] = "600";
        headers["Access-Control-Allow-Headers"] = string.Join(", ", AllowHeaders);
        headers["Access-Control-Allow-Credentials"] = "true";
        var failures = new List<string>();
        if (_origins.Contains(origin))
        {
            headers["Access-Control-Allow-Origin"] = origin;
        }
        else
        {
            failures.Add("origin");
        }

        var requestedMethod = context.Request.Headers["Access-Control-Request-Method"][0] ?? string.Empty;
        if (!AllowMethods.Contains(requestedMethod, StringComparer.Ordinal))
        {
            failures.Add("method");
        }

        var requestedHeaders = context.Request.Headers["Access-Control-Request-Headers"];
        if (requestedHeaders.Count > 0)
        {
            foreach (var header in (requestedHeaders[0] ?? string.Empty).ToLowerInvariant().Split(','))
            {
                if (!_allowHeadersLower.Contains(header.Trim()))
                {
                    failures.Add("headers");
                    break;
                }
            }
        }

        if (context.Request.Headers.ContainsKey("Access-Control-Request-Private-Network"))
        {
            failures.Add("private-network");
        }

        return failures.Count > 0
            ? PyResponses.WritePlainTextAsync(context, StatusCodes.Status400BadRequest, "Disallowed CORS " + string.Join(", ", failures))
            : PyResponses.WritePlainTextAsync(context, StatusCodes.Status200OK, "OK");
    }
}

/// <summary>
/// <c>TrustedProxySchemeMiddleware</c>: only a connection from inside <c>WEIR_TRUSTED_PROXY_IPS</c> may set the
/// scheme, and only with a single <c>http</c> or <c>https</c>.
/// </summary>
public sealed class TrustedProxySchemeMiddleware
{
    private readonly RequestDelegate _next;
    private readonly List<PyIpNetwork> _networks;

    public TrustedProxySchemeMiddleware(RequestDelegate next, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        _next = next;
        _networks = [.. options.TrustedProxyIps
            .Select(value => PyIpNetwork.TryParse(value.Trim(), strict: false, out var network) ? network : null)
            .OfType<PyIpNetwork>()];
    }

    public Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var peer = context.Items.TryGetValue(ResponseMarkers.ConnectionPeer, out var item) ? item as string : ApiRequest.DefaultClientHost(context);
        if (!string.IsNullOrEmpty(peer) && ClientRateLimitKey.InNetworks(peer, _networks))
        {
            var values = context.Request.Headers["X-Forwarded-Proto"];
            if (values.Count > 0)
            {
                var scheme = (values[^1] ?? string.Empty).Trim().ToLowerInvariant();
                if (scheme is "http" or "https")
                {
                    context.Request.Scheme = scheme;
                }
            }
        }

        return _next(context);
    }
}

/// <summary><c>HeadMirrorsGetMiddleware</c>: HEAD runs as GET and the body is discarded.</summary>
public sealed class HeadMirrorsGetMiddleware
{
    private readonly RequestDelegate _next;

    public HeadMirrorsGetMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        if (!HttpMethods.IsHead(context.Request.Method))
        {
            await _next(context).ConfigureAwait(false);
            return;
        }

        context.Request.Method = HttpMethods.Get;
        var original = context.Features.Get<IHttpResponseBodyFeature>()!;
        context.Features.Set<IHttpResponseBodyFeature>(new DiscardingBodyFeature(original));
        try
        {
            await _next(context).ConfigureAwait(false);
        }
        finally
        {
            context.Features.Set(original);
            context.Request.Method = HttpMethods.Head;
        }
    }

    private sealed class DiscardingBodyFeature(IHttpResponseBodyFeature inner) : IHttpResponseBodyFeature
    {
        public Stream Stream { get; } = Stream.Null;

        public System.IO.Pipelines.PipeWriter Writer { get; } = System.IO.Pipelines.PipeWriter.Create(Stream.Null);

        public void DisableBuffering() => inner.DisableBuffering();

        public Task StartAsync(CancellationToken cancellationToken = default) => inner.StartAsync(cancellationToken);

        public Task SendFileAsync(string path, long offset, long? count, CancellationToken cancellationToken = default) =>
            inner.StartAsync(cancellationToken);

        public Task CompleteAsync() => inner.CompleteAsync();
    }
}

/// <summary><c>XRequestedWithCsrfMiddleware</c>: a browser's mutating API call must send <c>X-Requested-With: XMLHttpRequest</c>.</summary>
public sealed class XRequestedWithMiddleware
{
    private static readonly HashSet<string> Mutating = new(StringComparer.Ordinal) { "POST", "PUT", "PATCH", "DELETE" };
    private readonly RequestDelegate _next;

    public XRequestedWithMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var request = context.Request;
        if (Mutating.Contains(request.Method) &&
            (request.Path.Value ?? string.Empty).StartsWith("/api/", StringComparison.Ordinal) &&
            request.Headers.ContainsKey("Origin"))
        {
            var xrw = (request.Headers["X-Requested-With"].FirstOrDefault() ?? string.Empty).Trim();
            if (!string.Equals(xrw, "xmlhttprequest", StringComparison.OrdinalIgnoreCase))
            {
                return PyResponses.WriteJsonAsync(
                    context,
                    StatusCodes.Status403Forbidden,
                    new Core.Json.PyDict().Set("detail", "Missing X-Requested-With header. This endpoint requires an authenticated browser session."));
            }
        }

        return _next(context);
    }
}

/// <summary>Counts log records by level for the metrics endpoints (the Python log filter's <c>record_log_record</c>).</summary>
public sealed class MetricsLoggerProvider : ILoggerProvider
{
    private readonly Core.Metrics.RuntimeMetricsStore _metrics;
    private readonly LogLevel _minimum;

    public MetricsLoggerProvider(Core.Metrics.RuntimeMetricsStore metrics, LogLevel minimum)
    {
        _metrics = metrics;
        _minimum = minimum;
    }

    public ILogger CreateLogger(string categoryName) => new CountingLogger(this);

    public void Dispose()
    {
    }

    private sealed class CountingLogger(MetricsLoggerProvider provider) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => logLevel != LogLevel.None && logLevel >= provider._minimum;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (IsEnabled(logLevel))
            {
                provider._metrics.RecordLog(Infrastructure.Logging.PythonLogFormat.LevelName(logLevel));
            }
        }
    }
}
