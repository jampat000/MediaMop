using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Routing.Template;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Notifications;
using Weir.Core.Security;
using Weir.Core.Validation;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Http;

/// <summary>What a handler answers with.</summary>
public abstract record ApiResult;

/// <summary>A JSON body, with extra headers (for example <c>Set-Cookie</c>) in the order given.</summary>
public sealed record JsonApiResult(int StatusCode, PyJson Body) : ApiResult
{
    public IReadOnlyList<KeyValuePair<string, string>> Headers { get; init; } = [];
}

/// <summary>A response the handler writes itself (files, plain text, empty bodies).</summary>
public sealed record CustomApiResult(Func<HttpContext, Task> Write) : ApiResult;

/// <summary>The metrics label of a route: its path in the Python router that declared it.</summary>
public sealed record RouteLabel(string Label);

/// <summary>Every API route in registration order, for Starlette's partial matches (405 and its <c>Allow</c> header).</summary>
public sealed class RouteTable
{
    private readonly List<(TemplateMatcher Matcher, string[] Methods, string Label)> _routes = [];
    private readonly Lock _lock = new();

    public void Add(string template, IReadOnlyList<string> methods, string label)
    {
        ArgumentNullException.ThrowIfNull(methods);
        var matcher = new TemplateMatcher(TemplateParser.Parse(template), new RouteValueDictionary());
        lock (_lock)
        {
            _routes.Add((matcher, [.. methods], label));
        }
    }

    /// <summary>The first route whose path matches, whatever its methods.</summary>
    public (string Label, IReadOnlyList<string> Methods)? FirstPathMatch(PathString path)
    {
        lock (_lock)
        {
            foreach (var (matcher, methods, label) in _routes)
            {
                if (matcher.TryMatch(path, new RouteValueDictionary()))
                {
                    return (label, methods);
                }
            }
        }

        return null;
    }
}

/// <summary>Per-process abuse controls (<c>app.state.auth_login_rate_limiter</c> and <c>bootstrap_rate_limiter</c>).</summary>
public sealed class AuthRateLimiters
{
    private int _forwardedWarned;

    public AuthRateLimiters(WeirOptions options, TimeProvider time)
    {
        ArgumentNullException.ThrowIfNull(options);
        Login = new SlidingWindowLimiter(options.AuthLoginRateMaxAttempts, options.AuthLoginRateWindowSeconds, time);
        Bootstrap = new SlidingWindowLimiter(options.BootstrapRateMaxAttempts, options.BootstrapRateWindowSeconds, time);
    }

    public SlidingWindowLimiter Login { get; }

    public SlidingWindowLimiter Bootstrap { get; }

    /// <summary><c>_warn_forwarded_headers_ignored</c>: once per process.</summary>
    public bool ShouldWarnForwardedIgnored() => Interlocked.Exchange(ref _forwardedWarned, 1) == 0;
}

/// <summary>
/// One API request: its database work (committed when the handler succeeds), the signed-in user once
/// resolved, and the checks Python's routes share (session secret, CSRF, browser origin, rate limits).
/// </summary>
public sealed class ApiRequest : IAsyncDisposable
{
    private UnitOfWork? _uow;
    private SignedInSession? _user;

    public ApiRequest(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        Context = context;
        Options = context.RequestServices.GetRequiredService<WeirOptions>();
        Time = context.RequestServices.GetRequiredService<TimeProvider>();
        Auth = context.RequestServices.GetRequiredService<AuthService>();
        Database = context.RequestServices.GetRequiredService<SqliteDatabase>();
        LoggerFactory = context.RequestServices.GetRequiredService<ILoggerFactory>();
    }

    public HttpContext Context { get; }

    public WeirOptions Options { get; }

    public TimeProvider Time { get; }

    public AuthService Auth { get; }

    public SqliteDatabase Database { get; }

    public ILoggerFactory LoggerFactory { get; }

    public T Service<T>()
        where T : notnull => Context.RequestServices.GetRequiredService<T>();

    public async Task<UnitOfWork> DbAsync()
    {
        _uow ??= await UnitOfWork.OpenAsync(Database, Context.RequestAborted).ConfigureAwait(false);
        return _uow;
    }

    public async Task CommitAsync()
    {
        if (_uow is not null)
        {
            await _uow.CommitAsync().ConfigureAwait(false);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_uow is not null)
        {
            await _uow.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Commit and close this request's database work now, for a response that outlives it (the Activity
    /// stream must not hold a connection for its lifetime).
    /// </summary>
    public async Task ReleaseDbAsync()
    {
        if (_uow is not null)
        {
            await _uow.CommitAsync().ConfigureAwait(false);
            await _uow.DisposeAsync().ConfigureAwait(false);
            _uow = null;
        }
    }

    /// <summary><c>current_raw_session_token</c>.</summary>
    public string? RawSessionToken
    {
        get
        {
            var raw = (PyCookies.Get(Context, Options.SessionCookieName) ?? string.Empty).Trim();
            return raw.Length == 0 ? null : raw;
        }
    }

    public string? Header(string name)
    {
        var values = Context.Request.Headers[name];
        return values.Count == 0 ? null : string.Join(", ", values.ToArray());
    }

    /// <summary>Starlette's <c>request.headers.get(name)</c>: the first occurrence.</summary>
    public string? FirstHeader(string name)
    {
        var values = Context.Request.Headers[name];
        return values.Count == 0 ? null : values[0];
    }

    /// <summary>Starlette's <c>request.query_params.get(name)</c>: the last value, <see langword="null"/> when absent.</summary>
    public string? Query(string name)
    {
        var values = Context.Request.Query[name];
        return values.Count == 0 ? null : values[^1];
    }

    public string? RouteValue(string name) => Context.Request.RouteValues.TryGetValue(name, out var value) ? value as string : null;

    /// <summary>The client address after trusted forwarded headers were applied (<c>request.client.host</c>).</summary>
    public string? ClientHost => DefaultClientHost(Context);

    public static string? DefaultClientHost(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var address = context.Connection.RemoteIpAddress;
        if (address is null)
        {
            return null;
        }

        return (address.IsIPv4MappedToIPv6 ? address.MapToIPv4() : address).ToString();
    }

    /// <summary><c>get_current_user_public</c>, then <c>require_roles</c> when <paramref name="allowedRoles"/> is given.</summary>
    public async Task<SignedInSession> RequireUserAsync(IReadOnlySet<string>? allowedRoles = null)
    {
        if (_user is null)
        {
            var uow = await DbAsync().ConfigureAwait(false);
            _user = await Auth.LoadValidSessionAsync(uow, RawSessionToken).ConfigureAwait(false)
                ?? throw new ApiException(StatusCodes.Status401Unauthorized, "Not authenticated.");
            if (!UserRoles.Valid.Contains(_user.User.Role))
            {
                _user = null;
                throw new ApiException(StatusCodes.Status403Forbidden, "Invalid account role.");
            }
        }

        if (allowedRoles is not null && !allowedRoles.Contains(_user.User.Role))
        {
            throw new ApiException(StatusCodes.Status403Forbidden, "Forbidden.");
        }

        return _user;
    }

    /// <summary><c>require_session_secret</c>.</summary>
    public string RequireSessionSecret()
    {
        var secret = (Options.SessionSecret ?? string.Empty).Trim();
        return secret.Length > 0
            ? secret
            : throw new ApiException(StatusCodes.Status503ServiceUnavailable, "WEIR_SESSION_SECRET must be set for auth endpoints.");
    }

    /// <summary><c>validate_browser_post_origin</c>.</summary>
    public void ValidateBrowserPostOrigin()
    {
        var trusted = Options.TrustedBrowserOrigins;
        if (trusted.Count == 0)
        {
            return;
        }

        var normalized = trusted.Select(o => o.TrimEnd('/')).ToHashSet(StringComparer.Ordinal);
        var origin = (Context.Request.Headers.Origin.FirstOrDefault() ?? string.Empty).Trim();
        if (origin.Length > 0)
        {
            if (!normalized.Contains(origin.TrimEnd('/')))
            {
                throw new ApiException(StatusCodes.Status403Forbidden, "Origin not allowed.");
            }

            return;
        }

        var referer = (Context.Request.Headers.Referer.FirstOrDefault() ?? string.Empty).Trim();
        if (referer.Length > 0)
        {
            var parsed = SplitUrl.Parse(referer);
            var baseUrl = $"{parsed.Scheme}://{parsed.Netloc}".TrimEnd('/');
            if (!normalized.Contains(baseUrl))
            {
                throw new ApiException(StatusCodes.Status403Forbidden, "Referer not allowed.");
            }

            return;
        }

        throw new ApiException(StatusCodes.Status403Forbidden, "Missing Origin or Referer for browser POST.");
    }

    /// <summary><c>verify_csrf_token</c> against this request's session cookie.</summary>
    public bool VerifyCsrf(string secret, string? token, bool allowAnonymous) =>
        CsrfTokens.Verify(secret, token, RawSessionToken, allowAnonymous, Time);

    /// <summary>The standard settings-route check: origin, secret, then a session-bound token.</summary>
    public void RequireConfirmationToken(string? token, string detail = "Your confirmation token expired. Refresh the page and try again.")
    {
        ValidateBrowserPostOrigin();
        var secret = RequireSessionSecret();
        if (!VerifyCsrf(secret, token, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, detail);
        }
    }

    /// <summary><c>client_rate_limit_key</c>.</summary>
    public string RateLimitKey()
    {
        var limiters = Service<AuthRateLimiters>();
        return ClientRateLimitKey.Resolve(
            ClientHost,
            Header("X-Forwarded-For"),
            Options.TrustedProxyIps,
            () =>
            {
                if (limiters.ShouldWarnForwardedIgnored())
                {
                    LoggerFactory.CreateLogger("weir.platform.auth.rate_limit").LogWarning(
                        "X-Forwarded-For was present but WEIR_TRUSTED_PROXY_IPS is not configured; " +
                        "rate limiting will use the immediate peer address.");
                }
            });
    }

    /// <summary>Read the body now (FastAPI reads and decodes it before running dependencies).</summary>
    public Task<PyJson?> ReadBodyAsync() => PyRequestBody.ReadAsync(Context);

    /// <summary>An <c>int</c> path parameter.</summary>
    public long PathInt(string name, ValidationIssues issues)
    {
        ArgumentNullException.ThrowIfNull(issues);
        var raw = RouteValue(name) ?? string.Empty;
        return PydanticRules.TryInt(new PyStr(raw), ["path", name], null, null, issues, out var value)
            ? value > long.MaxValue ? long.MaxValue : value < long.MinValue ? long.MinValue : (long)value
            : 0;
    }
}
