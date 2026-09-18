using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Weir.Api.Http;
using Weir.Core.Metrics;

namespace Weir.Api.Tests.Http;

/// <summary>
/// <see cref="RequestContextMiddleware"/>'s unhandled-failure log is the sink CodeQL's <c>cs/log-forging</c> flagged
/// (alerts #342 and #343): a request-derived value reaching <c>ILogger.LogError</c>. These drive the
/// middleware directly — a real <c>DefaultHttpContext</c>, a <c>next</c> that throws, and a logger that
/// captures the exact text a console/file sink would receive — rather than through <c>TestServer</c>/Kestrel,
/// because Kestrel itself would reject a request line or method carrying these characters before the
/// middleware ever saw them (verified separately); driving the middleware directly is what proves the
/// application-level barrier holds regardless of which host is in front of it.
/// </summary>
public sealed class RequestContextMiddlewareLogForgingTests
{
    [Fact]
    public async Task Unhandled_failure_log_does_not_forge_a_line_from_a_decoded_path_newline()
    {
        var logger = new CapturingLoggerFactory();
        var middleware = NewMiddleware(logger);

        var context = new DefaultHttpContext();
        // What ASP.NET Core hands application code after decoding a request to /foo%0Afake-log-line: a
        // Path.Value containing a real line feed. No route is registered, so RouteLabelFor falls back to it.
        context.Request.Path = new PathString("/foo\nfake-log-line: forged");
        context.Request.Method = "GET";

        await Assert.ThrowsAsync<InvalidOperationException>(() => middleware.InvokeAsync(context));

        var message = SingleUnhandledFailureMessage(logger);
        Assert.DoesNotContain('\n', message);
        Assert.DoesNotContain('\r', message);
        Assert.Contains("route=/foo\\nfake-log-line: forged", message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Unhandled_failure_log_does_not_forge_a_line_from_the_request_id_header()
    {
        var logger = new CapturingLoggerFactory();
        var middleware = NewMiddleware(logger);

        var context = new DefaultHttpContext();
        context.Request.Path = new PathString("/health");
        context.Request.Method = "GET";
        context.Request.Headers[RequestContextMiddleware.HeaderName] = "abc123\r\nfake-log-line: forged";

        await Assert.ThrowsAsync<InvalidOperationException>(() => middleware.InvokeAsync(context));

        var message = SingleUnhandledFailureMessage(logger);
        Assert.DoesNotContain('\n', message);
        Assert.DoesNotContain('\r', message);
        Assert.Contains("request_id=abc123\\r\\nfake-log-line: forged", message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Unhandled_failure_log_sanitizes_a_forged_method_even_though_kestrel_would_reject_it()
    {
        // DefaultHttpContext performs none of Kestrel's request-line validation, so this stands in for any
        // non-Kestrel host (a bespoke TestServer request, a future reverse proxy) that might not reject a
        // method token containing control characters the way Kestrel does.
        var logger = new CapturingLoggerFactory();
        var middleware = NewMiddleware(logger);

        var context = new DefaultHttpContext();
        context.Request.Path = new PathString("/health");
        context.Request.Method = "GET\r\nfake-log-line: forged";

        await Assert.ThrowsAsync<InvalidOperationException>(() => middleware.InvokeAsync(context));

        var message = SingleUnhandledFailureMessage(logger);
        Assert.DoesNotContain('\n', message);
        Assert.DoesNotContain('\r', message);
        Assert.Contains("method=GET\\r\\nfake-log-line: forged", message, StringComparison.Ordinal);
    }

    private static RequestContextMiddleware NewMiddleware(ILoggerFactory loggerFactory) =>
        new(
            _ => throw new InvalidOperationException("boom"),
            loggerFactory,
            new RuntimeMetricsStore(TimeProvider.System),
            new RouteTable(),
            TimeProvider.System);

    private static string SingleUnhandledFailureMessage(CapturingLoggerFactory logger) =>
        Assert.Single(logger.Entries, e => e.Message.Contains("Unhandled request failure", StringComparison.Ordinal)).Message;

    private sealed class CapturingLoggerFactory : ILoggerFactory
    {
        public List<(LogLevel Level, string Message)> Entries { get; } = [];

        public ILogger CreateLogger(string categoryName) => new CapturingLogger(this);

        public void AddProvider(ILoggerProvider provider)
        {
        }

        public void Dispose()
        {
        }

        private sealed class CapturingLogger(CapturingLoggerFactory owner) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state)
                where TState : notnull => null;

            public bool IsEnabled(LogLevel logLevel) => true;

            public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) =>
                owner.Entries.Add((logLevel, formatter(state, exception)));
        }
    }
}
