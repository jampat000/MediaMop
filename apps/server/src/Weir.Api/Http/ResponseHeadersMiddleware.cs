using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Weir.Core.Configuration;
using Weir.Infrastructure.Logging;

namespace Weir.Api.Http;

/// <summary>
/// <c>X-Request-ID</c> on every response and the request id in every log line
/// (port of <c>RequestContextMiddleware</c>).
/// </summary>
public sealed class RequestContextMiddleware
{
    public const string HeaderName = "X-Request-ID";

    private readonly RequestDelegate _next;
    private readonly ILogger<RequestContextMiddleware> _logger;

    public RequestContextMiddleware(RequestDelegate next, ILogger<RequestContextMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var incoming = context.Request.Headers[HeaderName].ToString().Trim();
        var requestId = incoming.Length > 0 ? incoming : Guid.NewGuid().ToString("N");
        using var scope = LogContext.BeginRequest(requestId);
        context.Response.OnStarting(() =>
        {
            context.Response.Headers[HeaderName] = requestId;
            return Task.CompletedTask;
        });
        try
        {
            await _next(context).ConfigureAwait(false);
        }
        catch (Exception exception) when (LogUnhandled(exception, requestId, context))
        {
            throw;
        }
    }

    private bool LogUnhandled(Exception exception, string requestId, HttpContext context)
    {
        _logger.LogError(
            exception,
            "Unhandled request failure request_id={RequestId} method={Method} route={Route}",
            requestId,
            context.Request.Method,
            context.Request.Path.Value);
        return false;
    }
}

/// <summary>
/// Security headers on every response that passes through it (port of <c>SecurityHeadersMiddleware</c>).
/// Existing values win, as with Python's <c>setdefault</c>.
/// </summary>
public sealed class SecurityHeadersMiddleware
{
    /// <summary>API baseline: no scripts, no frames, no base-tag surprises, no forms to third parties.</summary>
    public const string ApiContentSecurityPolicy = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";

    /// <summary>The bundled web app: first-party only; the app self-hosts its fonts.</summary>
    public const string HtmlContentSecurityPolicy =
        "default-src 'self'; " +
        "script-src 'self'; " +
        "style-src 'self'; " +
        "font-src 'self' data:; " +
        "img-src 'self' data: blob:; " +
        "connect-src 'self'; " +
        "base-uri 'none'; " +
        "frame-ancestors 'none'; " +
        "form-action 'self'";

    private static readonly HashSet<string> NoStoreExactPaths = new(StringComparer.Ordinal) { "/health", "/ready", "/readiness", "/metrics" };

    private readonly RequestDelegate _next;
    private readonly WeirOptions _options;

    public SecurityHeadersMiddleware(RequestDelegate next, WeirOptions options)
    {
        _next = next;
        _options = options;
    }

    public Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        context.Response.OnStarting(() =>
        {
            Apply(context, _options.SecurityEnableHsts);
            return Task.CompletedTask;
        });
        return _next(context);
    }

    internal static void Apply(HttpContext context, bool enableHsts)
    {
        var headers = context.Response.Headers;
        var contentType = (context.Response.ContentType ?? string.Empty).ToLowerInvariant();
        SetDefault(headers, "X-Content-Type-Options", "nosniff");
        SetDefault(headers, "Referrer-Policy", "strict-origin-when-cross-origin");
        SetDefault(
            headers,
            "Content-Security-Policy",
            contentType.StartsWith("text/html", StringComparison.Ordinal) ? HtmlContentSecurityPolicy : ApiContentSecurityPolicy);
        SetDefault(headers, "X-Frame-Options", "DENY");
        headers.Remove("Server");

        // API responses can include filesystem paths, credentials metadata and operator settings.
        var path = context.Request.Path.Value ?? string.Empty;
        if (path.StartsWith("/api/v1", StringComparison.Ordinal) || NoStoreExactPaths.Contains(path))
        {
            SetDefault(headers, "Cache-Control", "no-store, private");
        }

        if (enableHsts)
        {
            SetDefault(headers, "Strict-Transport-Security", "max-age=31536000; includeSubDomains");
        }
    }

    private static void SetDefault(IHeaderDictionary headers, string name, string value)
    {
        if (!headers.ContainsKey(name))
        {
            headers[name] = value;
        }
    }
}
