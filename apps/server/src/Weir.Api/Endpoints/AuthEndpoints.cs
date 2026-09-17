using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Weir.Api.Http;
using Weir.Core.Activity;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Security;
using Weir.Core.Validation;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Settings;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Endpoints;

/// <summary>Cookie-session auth under <c>/api/v1/auth</c> (port of <c>weir.platform.auth.router</c>).</summary>
public static class AuthEndpoints
{
    private const string InvalidCsrf = "Invalid or expired CSRF token.";
    private const string ConfirmationExpired = "Your confirmation token expired. Refresh the page and try again.";

    public static IEndpointRouteBuilder MapAuthEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/auth/csrf", GetCsrfAsync);
        endpoints.MapV1("POST", "/auth/login", PostLoginAsync);
        endpoints.MapV1("GET", "/auth/bootstrap/status", GetBootstrapStatusAsync);
        endpoints.MapV1("POST", "/auth/bootstrap", PostBootstrapAsync);
        endpoints.MapV1("POST", "/auth/logout", PostLogoutAsync);
        endpoints.MapV1("GET", "/auth/me", GetMeAsync);
        endpoints.MapV1("GET", "/auth/session", GetSessionAsync);
        endpoints.MapV1("GET", "/auth/sessions", GetSessionsAsync);
        endpoints.MapV1("POST", "/auth/sessions/revoke-others", PostRevokeOthersAsync);
        endpoints.MapV1("POST", "/auth/sessions/{session_id}/revoke", PostRevokeSessionAsync);
        endpoints.MapV1("GET", "/auth/admin/ping", GetAdminPingAsync);
        endpoints.MapV1("POST", "/auth/change-username", PostChangeUsernameAsync);
        endpoints.MapV1("POST", "/auth/change-password", PostChangePasswordAsync);
        return endpoints;
    }

    private static ILogger Logger(ApiRequest request) => request.LoggerFactory.CreateLogger("weir.platform.auth.router");

    private static async Task<ApiResult> GetCsrfAsync(ApiRequest request)
    {
        var secret = request.RequireSessionSecret();
        var raw = request.RawSessionToken;
        if (raw is not null)
        {
            var uow = await request.DbAsync().ConfigureAwait(false);
            if (await request.Auth.LoadValidSessionAsync(uow, raw).ConfigureAwait(false) is null)
            {
                raw = null;
            }
        }

        return ApiRoutes.Ok(new PyDict().Set("csrf_token", CsrfTokens.Issue(secret, raw, request.Time)));
    }

    private static async Task<ApiResult> PostLoginAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var username = model.Str("username", minLength: 1, maxLength: 64);
        var password = model.Str("password", minLength: 1);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var trustedDevice = model.Bool("trusted_device", defaultValue: false);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        var limiters = request.Service<AuthRateLimiters>();
        if (!limiters.Login.Allow(request.RateLimitKey()))
        {
            throw new ApiException(
                StatusCodes.Status429TooManyRequests,
                "Too many login attempts from this address. Try again later.",
                new Dictionary<string, string> { ["Retry-After"] = Math.Max(1, request.Options.AuthLoginRateWindowSeconds).ToString(System.Globalization.CultureInfo.InvariantCulture) });
        }

        var secret = request.RequireSessionSecret();
        request.ValidateBrowserPostOrigin();
        if (!request.VerifyCsrf(secret, csrfToken, allowAnonymous: true))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, InvalidCsrf);
        }

        var uname = username.Trim();
        var uow = await request.DbAsync().ConfigureAwait(false);
        var result = await request.Auth.LoginAsync(
            uow, uname, password, trustedDevice, SessionRules.ClientLabelFromUserAgent(request.FirstHeader("User-Agent"))).ConfigureAwait(false);
        if (result is null)
        {
            Logger(request).LogWarning("auth event: login failed");
            await ActivityStore.MaybeRecordLoginFailedAsync(uow, uname, request.Auth.Now()).ConfigureAwait(false);
            await request.CommitAsync().ConfigureAwait(false);
            throw new ApiException(StatusCodes.Status401Unauthorized, "Invalid username or password.");
        }

        var (user, session, rawToken) = result.Value;
        Logger(request).LogInformation("auth event: login succeeded (user_id={UserId})", user.Id);
        await ActivityStore.RecordAsync(uow, ActivityEventTypes.AuthLoginSucceeded, "auth", "Signed in", user.Username).ConfigureAwait(false);
        var cookie = PyCookies.SetCookieHeader(
            request.Options.SessionCookieName,
            rawToken,
            maxAge: SessionRules.AbsoluteTimeoutDays(session.IsTrustedDevice, request.Options) * 86400,
            expires: null,
            httpOnly: true,
            secure: SessionRules.ResolveCookieSecure(request.Context.Request.Scheme, request.Options.SessionCookieSecureMode),
            sameSite: SessionRules.SameSiteText(request.Options.SessionCookieSameSite));
        return new JsonApiResult(StatusCodes.Status200OK, new PyDict().Set("user", AuthService.UserPublic(user)))
        {
            Headers = [new("Set-Cookie", cookie), new("Cache-Control", "no-store, private")],
        };
    }

    private static async Task<ApiResult> GetBootstrapStatusAsync(ApiRequest request)
    {
        const string schemaNotReady = "Local SQLite schema is not ready (Weir migrates its database at startup; check the server log and restart it).";
        const string databaseUnavailable = "SQLite database unavailable or cannot be opened (check WEIR_HOME and WEIR_DB_PATH).";
        const string queryFailed =
            "Database query failed while checking bootstrap status. " +
            "See the server log, restart Weir so it can migrate the database, and verify WEIR_HOME / WEIR_DB_PATH.";
        bool allowed;
        try
        {
            var uow = await UnitOfWork.OpenAsync(request.Database, request.Context.RequestAborted).ConfigureAwait(false);
            await using (uow.ConfigureAwait(false))
            {
                allowed = await AuthService.BootstrapAllowedAsync(uow).ConfigureAwait(false);
            }
        }
        catch (SqliteException exception)
        {
            var message = exception.Message.ToLowerInvariant();
            var operational = exception.SqliteErrorCode is 1 or 3 or 4 or 5 or 6 or 8 or 9 or 10 or 13 or 14 or 15 or 16 or 17;
            if (operational)
            {
                throw new ApiException(
                    StatusCodes.Status503ServiceUnavailable,
                    message.Contains("no such table", StringComparison.Ordinal) || message.Contains("no such column", StringComparison.Ordinal)
                        ? schemaNotReady
                        : databaseUnavailable);
            }

            throw new ApiException(StatusCodes.Status503ServiceUnavailable, queryFailed);
        }
        catch (Exception exception) when (exception is not ApiException and not OperationCanceledException)
        {
            request.LoggerFactory.CreateLogger("weir.platform.auth.router").LogError(exception, "bootstrap status: unexpected failure");
            throw new ApiException(
                StatusCodes.Status503ServiceUnavailable,
                "Could not read bootstrap status. Check the server log, restart Weir so it can migrate " +
                "the database, and verify WEIR_HOME / WEIR_DB_PATH.");
        }

        return ApiRoutes.Ok(new PyDict()
            .Set("bootstrap_allowed", allowed)
            .Set("reason", allowed ? "no_admin_user" : "admin_already_exists"));
    }

    private static async Task<ApiResult> PostBootstrapAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var username = model.Str("username", minLength: 1, maxLength: 64);
        var password = model.Str("password", minLength: PasswordPolicy.MinPasswordLength, maxLength: 512);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        var limiters = request.Service<AuthRateLimiters>();
        if (!limiters.Bootstrap.Allow(request.RateLimitKey()))
        {
            throw new ApiException(
                StatusCodes.Status429TooManyRequests,
                "Too many bootstrap attempts from this address. Try again later.",
                new Dictionary<string, string> { ["Retry-After"] = Math.Max(1, request.Options.BootstrapRateWindowSeconds).ToString(System.Globalization.CultureInfo.InvariantCulture) });
        }

        var secret = request.RequireSessionSecret();
        request.ValidateBrowserPostOrigin();
        if (!CsrfTokens.Verify(secret, csrfToken, null, allowAnonymous: true, request.Time))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, InvalidCsrf);
        }

        var logger = Logger(request);
        logger.LogInformation("auth event: bootstrap attempted");
        var uow = await request.DbAsync().ConfigureAwait(false);
        uow.BeginImmediate();
        if (!await AuthService.BootstrapAllowedAsync(uow).ConfigureAwait(false))
        {
            logger.LogWarning("auth event: bootstrap denied (admin already exists)");
            await ActivityStore.MaybeRecordBootstrapDeniedAsync(uow, request.Auth.Now()).ConfigureAwait(false);
            await request.CommitAsync().ConfigureAwait(false);
            throw new ApiException(StatusCodes.Status403Forbidden, "Bootstrap is not available: an admin user already exists.");
        }

        UserRecord user;
        try
        {
            user = await AuthService.CreateInitialAdminAsync(uow, username.Trim(), password).ConfigureAwait(false);
        }
        catch (PyValueErrorException exception)
        {
            logger.LogWarning("auth event: bootstrap failed (weak password)");
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }
        catch (SqliteException exception) when (SqliteValues.IsIntegrityError(exception))
        {
            logger.LogWarning("auth event: bootstrap failed (username conflict)");
            throw new ApiException(StatusCodes.Status409Conflict, "Username already exists.");
        }

        logger.LogInformation("auth event: bootstrap succeeded (user_id={UserId})", user.Id);
        await ActivityStore.RecordAsync(uow, ActivityEventTypes.AuthBootstrapSucceeded, "auth", "Initial admin created", user.Username).ConfigureAwait(false);
        var suite = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        await SuiteSettingsStore.UpdateAsync(uow, suite, suite with { SetupWizardState = "pending" }).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("message", "Bootstrap complete. Sign in with POST /api/v1/auth/login.")
            .Set("username", user.Username));
    }

    private static async Task<ApiResult> PostLogoutAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        var headerToken = request.FirstHeader("X-CSRF-Token");
        string? bodyToken = null;
        if (body is not null and not PyNull)
        {
            var issues = new ValidationIssues();
            var model = new BodyModel(body, issues);
            bodyToken = model.OptionalStr("csrf_token");
            model.Finish(ExtraFields.Forbid);
            issues.ThrowIfAny();
        }

        var secret = request.RequireSessionSecret();
        request.ValidateBrowserPostOrigin();
        var token = (string.IsNullOrEmpty(headerToken) ? string.IsNullOrEmpty(bodyToken) ? string.Empty : bodyToken : headerToken).Trim();
        if (token.Length == 0)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "Missing CSRF token (X-CSRF-Token header or body csrf_token).");
        }

        var rawSession = request.RawSessionToken;
        if (!request.VerifyCsrf(secret, token, allowAnonymous: rawSession is null))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, InvalidCsrf);
        }

        var logger = Logger(request);
        if (rawSession is not null)
        {
            var uow = await request.DbAsync().ConfigureAwait(false);
            var pair = await request.Auth.LoadValidSessionAsync(uow, rawSession).ConfigureAwait(false);
            if (pair is not null)
            {
                await ActivityStore.RecordAsync(uow, ActivityEventTypes.AuthLogout, "auth", "Signed out", pair.User.Username).ConfigureAwait(false);
            }

            if (await request.Auth.LogoutByCookieAsync(uow, rawSession).ConfigureAwait(false))
            {
                logger.LogInformation("auth event: logout (session revoked)");
            }
            else
            {
                logger.LogInformation("auth event: logout (no active session matched cookie)");
            }
        }
        else
        {
            logger.LogInformation("auth event: logout (no session cookie)");
        }

        var cookie = PyCookies.SetCookieHeader(
            request.Options.SessionCookieName,
            string.Empty,
            maxAge: 0,
            expires: request.Time.GetUtcNow(),
            httpOnly: true,
            secure: SessionRules.ResolveCookieSecure(request.Context.Request.Scheme, request.Options.SessionCookieSecureMode),
            sameSite: SessionRules.SameSiteText(request.Options.SessionCookieSameSite));
        return new CustomApiResult(context =>
        {
            context.Response.Headers.Append("Set-Cookie", cookie);
            context.Response.Headers.CacheControl = "no-store, private";
            context.Response.StatusCode = StatusCodes.Status204NoContent;
            return Task.CompletedTask;
        });
    }

    private static async Task<ApiResult> GetMeAsync(ApiRequest request)
    {
        var current = await request.RequireUserAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("user", AuthService.UserPublic(current.User)));
    }

    private static async Task<ApiResult> GetSessionAsync(ApiRequest request)
    {
        var uow = await request.DbAsync().ConfigureAwait(false);
        var pair = await request.Auth.LoadValidSessionAsync(uow, request.RawSessionToken).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status401Unauthorized, "Not authenticated.");
        return ApiRoutes.Ok(request.Auth.SessionPublic(pair.Session, current: true));
    }

    private static async Task<ApiResult> GetSessionsAsync(ApiRequest request)
    {
        var user = await request.RequireUserAsync().ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var pair = await request.Auth.LoadValidSessionAsync(uow, request.RawSessionToken).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status401Unauthorized, "Not authenticated.");
        // Python's session hands back the row the dependency already loaded (and may have touched).
        var current = user.Session.Id == pair.Session.Id ? user.Session : pair.Session;
        var items = await request.Auth.ListActiveSessionsAsync(uow, user.User.Id, current).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("items", new PyList(items)));
    }

    private static async Task<ApiResult> PostRevokeOthersAsync(ApiRequest request)
    {
        var user = await request.RequireUserAsync().ConfigureAwait(false);
        var headerToken = request.FirstHeader("X-CSRF-Token");
        request.ValidateBrowserPostOrigin();
        var secret = request.RequireSessionSecret();
        if (headerToken is null || !request.VerifyCsrf(secret, headerToken, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, ConfirmationExpired);
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var pair = await request.Auth.LoadValidSessionAsync(uow, request.RawSessionToken).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status401Unauthorized, "Not authenticated.");
        var count = await request.Auth.RevokeOtherUserSessionsAsync(uow, user.User.Id, pair.Session.Id).ConfigureAwait(false);
        await ActivityStore.RecordAsync(
            uow, ActivityEventTypes.AuthSessionsRevoked, "auth", "Other sessions signed out",
            count.ToString(System.Globalization.CultureInfo.InvariantCulture)).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("message", $"Signed out {count} other session(s).").Set("revoked_count", count));
    }

    private static async Task<ApiResult> PostRevokeSessionAsync(ApiRequest request)
    {
        var user = await request.RequireUserAsync().ConfigureAwait(false);
        var headerToken = request.FirstHeader("X-CSRF-Token");
        var issues = new ValidationIssues();
        PydanticRules.TryUuid(request.RouteValue("session_id") ?? string.Empty, ["path", "session_id"], issues, out var sessionId);
        issues.ThrowIfAny();

        request.ValidateBrowserPostOrigin();
        var secret = request.RequireSessionSecret();
        if (headerToken is null || !request.VerifyCsrf(secret, headerToken, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, ConfirmationExpired);
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var pair = await request.Auth.LoadValidSessionAsync(uow, request.RawSessionToken).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status401Unauthorized, "Not authenticated.");
        if (sessionId.ToString("N") == pair.Session.Id)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "The current session cannot be revoked here.");
        }

        if (!await request.Auth.RevokeUserSessionAsync(uow, user.User.Id, sessionId).ConfigureAwait(false))
        {
            throw new ApiException(StatusCodes.Status404NotFound, "Session is no longer active.");
        }

        await ActivityStore.RecordAsync(uow, ActivityEventTypes.AuthSessionsRevoked, "auth", "Session signed out", "One other session was revoked.").ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("message", "Session signed out.").Set("revoked_count", 1));
    }

    private static async Task<ApiResult> GetAdminPingAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.AdminOnly).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("ok", true));
    }

    private static async Task<ApiResult> PostChangeUsernameAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        var user = await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var currentPassword = model.Str("current_password", minLength: 1);
        var newUsername = model.Str("new_username", minLength: 1, maxLength: 64);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        var secret = request.RequireSessionSecret();
        request.ValidateBrowserPostOrigin();
        if (!request.VerifyCsrf(secret, csrfToken, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, InvalidCsrf);
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        string changed;
        try
        {
            changed = await request.Auth.ChangeUsernameAsync(uow, user.User.Id, currentPassword, newUsername).ConfigureAwait(false);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        Logger(request).LogInformation("auth event: username changed (user_id={UserId})", user.User.Id);
        await ActivityStore.RecordAsync(uow, ActivityEventTypes.AuthUsernameChanged, "auth", "Username changed", $"Signed in as {changed}.").ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("message", "Username changed. Use it the next time you sign in.")
            .Set("username", changed));
    }

    private static async Task<ApiResult> PostChangePasswordAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        var user = await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var currentPassword = model.Str("current_password", minLength: 1);
        var newPassword = model.Str("new_password", minLength: PasswordPolicy.MinPasswordLength, maxLength: 512);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        var secret = request.RequireSessionSecret();
        request.ValidateBrowserPostOrigin();
        if (!request.VerifyCsrf(secret, csrfToken, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, InvalidCsrf);
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        try
        {
            await request.Auth.ChangePasswordAsync(uow, user.User.Id, currentPassword, newPassword).ConfigureAwait(false);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        Logger(request).LogInformation("auth event: password changed (user_id={UserId})", user.User.Id);
        await ActivityStore.RecordAsync(uow, ActivityEventTypes.AuthPasswordChanged, "auth", "Password changed", user.User.Username).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("message", "Password changed. Sign in again with your new password."));
    }
}
