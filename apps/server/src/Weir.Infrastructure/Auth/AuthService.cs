using Microsoft.Extensions.Logging;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Security;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Auth;

/// <summary>A signed-in request: its session row (as held in memory) and its user.</summary>
public sealed record SignedInSession(UserSessionRecord Session, UserRecord User);

/// <summary>Port of <c>weir.platform.auth.service</c> and <c>bootstrap</c>: credentials, server-side sessions and logout.</summary>
public sealed class AuthService
{
    public const string BootstrapNotAllowedMessage = "bootstrap not allowed: an admin user already exists";

    private readonly WeirOptions _options;
    private readonly TimeProvider _time;
    private readonly SqliteDatabase _database;
    private readonly ILogger _logger;

    public AuthService(WeirOptions options, TimeProvider time, SqliteDatabase database, ILoggerFactory loggerFactory)
    {
        ArgumentNullException.ThrowIfNull(loggerFactory);
        _options = options;
        _time = time;
        _database = database;
        _logger = loggerFactory.CreateLogger("weir.platform.auth.service");
    }

    public PyDateTime Now() => PyDateTime.UtcNow(_time);

    /// <summary><c>load_valid_session_for_request</c>: look up by token hash, enforce revocation and timeouts, and touch <c>last_seen_at</c> at most once a minute.</summary>
    public async Task<SignedInSession?> LoadValidSessionAsync(UnitOfWork uow, string? rawCookieToken)
    {
        ArgumentNullException.ThrowIfNull(uow);
        if (string.IsNullOrEmpty(rawCookieToken))
        {
            return null;
        }

        var row = await AuthStore.FindSessionByTokenHashAsync(uow, SessionTokens.Hash(rawCookieToken)).ConfigureAwait(false);
        if (row is null)
        {
            return null;
        }

        var idle = SessionRules.EffectiveIdleTimeout(row.IsTrustedDevice, _options);
        var now = Now();
        var reason = SessionRules.InvalidReason(row, idle, now.AsUtc);
        if (reason is not null)
        {
            if (row.RevokedAt is null && reason is SessionInvalidReason.AbsoluteExpired or SessionInvalidReason.IdleExpired)
            {
                await RevokeExpiredAsync(uow, row.Id, now).ConfigureAwait(false);
            }

            _logger.LogInformation("auth event: session rejected (reason={Reason}, user_id={UserId})", ReasonText(reason.Value), row.UserId);
            return null;
        }

        var user = await AuthStore.GetUserAsync(uow, row.UserId).ConfigureAwait(false);
        if (user is null || !user.IsActive)
        {
            return null;
        }

        if (now.AsUtc - row.LastSeenAt.AsUtc >= SessionRules.LastSeenTouchGap(idle))
        {
            await AuthStore.TouchSessionAsync(uow, row.Id, now).ConfigureAwait(false);
            row = row with { LastSeenAt = now };
        }

        return new SignedInSession(row, user);
    }

    /// <summary>
    /// Deliberate fix (#529): Python marks the expired session revoked inside the request's own session, which
    /// the 401 then rolls back. Here the revoke is committed on its own, whatever the request's outcome.
    /// </summary>
    private async Task RevokeExpiredAsync(UnitOfWork uow, string sessionId, PyDateTime now)
    {
        if (uow.InTransaction)
        {
            // The request already holds the write lock; a second connection would wait on it.
            await AuthStore.RevokeSessionAsync(uow, sessionId, now).ConfigureAwait(false);
            return;
        }

        var own = await UnitOfWork.OpenAsync(_database).ConfigureAwait(false);
        await using (own.ConfigureAwait(false))
        {
            await AuthStore.RevokeSessionAsync(own, sessionId, now).ConfigureAwait(false);
            await own.CommitAsync().ConfigureAwait(false);
        }
    }

    /// <summary><c>authenticate_user</c>, padding a missing or inactive account with a dummy verify.</summary>
    public async Task<UserRecord?> AuthenticateAsync(UnitOfWork uow, string username, string password)
    {
        var user = await AuthStore.FindUserByLowerUsernameAsync(uow, (username ?? string.Empty).Trim().ToLowerInvariant()).ConfigureAwait(false);
        if (user is null || !user.IsActive)
        {
            VerifyPassword(password, PasswordHasher.DummyPasswordHash);
            return null;
        }

        return VerifyPassword(password, user.PasswordHash) ? user : null;
    }

    /// <summary><c>verify_password</c>.</summary>
    public bool VerifyPassword(string plain, string passwordHash)
    {
        var result = PasswordHasher.Verify(plain, passwordHash);
        if (result == PasswordVerification.InvalidHash)
        {
            _logger.LogWarning("password verify: stored hash is invalid or unsupported (user record may be corrupt)");
        }

        return result == PasswordVerification.Match;
    }

    /// <summary><c>login_user</c>.</summary>
    public async Task<(UserRecord User, UserSessionRecord Session, string RawToken)?> LoginAsync(
        UnitOfWork uow, string username, string password, bool trustedDevice, string clientLabel)
    {
        var user = await AuthenticateAsync(uow, username, password).ConfigureAwait(false);
        if (user is null)
        {
            return null;
        }

        var (row, raw) = await CreateSessionAsync(uow, user, trustedDevice, clientLabel).ConfigureAwait(false);
        return (user, row, raw);
    }

    /// <summary><c>create_user_session</c>.</summary>
    public async Task<(UserSessionRecord Row, string RawToken)> CreateSessionAsync(UnitOfWork uow, UserRecord user, bool trustedDevice, string clientLabel)
    {
        ArgumentNullException.ThrowIfNull(user);
        var raw = SessionTokens.Generate();
        var now = Now();
        var ttl = SessionRules.Days(SessionRules.AbsoluteTimeoutDays(trustedDevice, _options));
        var label = (clientLabel ?? string.Empty).Trim();
        var row = new UserSessionRecord(
            Guid.NewGuid().ToString("N"),
            user.Id,
            SessionTokens.Hash(raw),
            now,
            PyDateTime.FromUtc(SessionRules.SafeAdd(now.AsUtc, ttl)),
            trustedDevice,
            now,
            null,
            PyStrings.Slice(label.Length == 0 ? SessionRules.DefaultClientLabel : label, 80));
        await AuthStore.InsertSessionAsync(uow, row).ConfigureAwait(false);
        var revoked = await EnforceSessionLimitAsync(uow, user.Id).ConfigureAwait(false);
        if (revoked > 0)
        {
            _logger.LogInformation("auth event: oldest sessions revoked after session cap (user_id={UserId}, count={Count})", user.Id, revoked);
        }

        _logger.LogInformation("auth event: session created");
        return (row, raw);
    }

    /// <summary><c>enforce_session_limit_for_user</c>: keep the newest five active sessions.</summary>
    public async Task<int> EnforceSessionLimitAsync(UnitOfWork uow, long userId, int maxActiveSessions = SessionRules.MaxActiveSessionsPerUser)
    {
        var cap = Math.Max(1, maxActiveSessions);
        var now = Now();
        var active = await AuthStore.CountActiveSessionsAsync(uow, userId, now).ConfigureAwait(false);
        var overflow = active - cap;
        if (overflow <= 0)
        {
            return 0;
        }

        var rows = await AuthStore.OldestActiveSessionsAsync(uow, userId, now, overflow).ConfigureAwait(false);
        foreach (var row in rows)
        {
            await AuthStore.RevokeSessionAsync(uow, row.Id, now).ConfigureAwait(false);
        }

        return rows.Count;
    }

    /// <summary><c>logout_by_cookie</c>.</summary>
    public async Task<bool> LogoutByCookieAsync(UnitOfWork uow, string? rawCookieToken)
    {
        var pair = await LoadValidSessionAsync(uow, rawCookieToken).ConfigureAwait(false);
        if (pair is null)
        {
            return false;
        }

        await AuthStore.RevokeSessionAsync(uow, pair.Session.Id, Now()).ConfigureAwait(false);
        return true;
    }

    /// <summary><c>cleanup_inactive_sessions</c>.</summary>
    public Task<int> CleanupInactiveSessionsAsync(UnitOfWork uow, PyDateTime? now = null)
    {
        var moment = now ?? Now();
        var idleCutoff = PyDateTime.FromUtc(SessionRules.SafeSubtract(moment.AsUtc, SessionRules.Minutes(_options.SessionIdleMinutes)));
        var trustedCutoff = PyDateTime.FromUtc(SessionRules.SafeSubtract(moment.AsUtc, SessionRules.Minutes(_options.SessionTrustedIdleMinutes)));
        return AuthStore.DeleteInactiveSessionsAsync(uow, moment, idleCutoff, trustedCutoff);
    }

    /// <summary><c>session_public</c>.</summary>
    public PyDict SessionPublic(UserSessionRecord session, bool current)
    {
        ArgumentNullException.ThrowIfNull(session);
        var label = string.IsNullOrEmpty(session.ClientLabel) ? SessionRules.DefaultClientLabel : session.ClientLabel;
        return new PyDict()
            .Set("session_id", session.PublicId)
            .Set("client_label", PyStrings.Slice(label, 80))
            .Set("current", current)
            .Set("trusted_device", session.IsTrustedDevice)
            .Set("created_at", session.CreatedAt.PydanticJson())
            .Set("last_seen_at", session.LastSeenAt.PydanticJson())
            .Set("absolute_expires_at", session.AbsoluteExpiresAt.PydanticJson())
            .Set("idle_timeout_minutes", SessionRules.IdleTimeoutMinutes(session.IsTrustedDevice, _options))
            .Set("absolute_timeout_days", SessionRules.AbsoluteTimeoutDays(session.IsTrustedDevice, _options));
    }

    public static PyDict UserPublic(UserRecord user)
    {
        ArgumentNullException.ThrowIfNull(user);
        return new PyDict().Set("id", user.Id).Set("username", user.Username).Set("role", user.Role);
    }

    /// <summary><c>list_active_sessions</c>, with the request's own session as it is held in memory.</summary>
    public async Task<List<PyJson>> ListActiveSessionsAsync(UnitOfWork uow, long userId, UserSessionRecord? current)
    {
        var moment = Now();
        var rows = await AuthStore.ActiveSessionsNewestFirstAsync(uow, userId, moment).ConfigureAwait(false);
        var output = new List<PyJson>();
        foreach (var stored in rows)
        {
            var row = current is not null && stored.Id == current.Id ? current : stored;
            var idle = SessionRules.EffectiveIdleTimeout(row.IsTrustedDevice, _options);
            if (SessionRules.InvalidReason(row, idle, moment.AsUtc) is not null)
            {
                continue;
            }

            output.Add(SessionPublic(row, current is not null && row.Id == current.Id));
        }

        return output;
    }

    /// <summary><c>revoke_user_session</c>.</summary>
    public async Task<bool> RevokeUserSessionAsync(UnitOfWork uow, long userId, Guid sessionId)
    {
        var row = await AuthStore.FindUserSessionAsync(uow, userId, sessionId.ToString("N")).ConfigureAwait(false);
        if (row is null || row.RevokedAt is not null)
        {
            return false;
        }

        await AuthStore.RevokeSessionAsync(uow, row.Id, Now()).ConfigureAwait(false);
        return true;
    }

    /// <summary><c>revoke_other_user_sessions</c>.</summary>
    public async Task<int> RevokeOtherUserSessionsAsync(UnitOfWork uow, long userId, string? currentSessionId)
    {
        var moment = Now();
        var count = 0;
        foreach (var row in await AuthStore.ActiveSessionsAsync(uow, userId, moment).ConfigureAwait(false))
        {
            if (currentSessionId is not null && row.Id == currentSessionId)
            {
                continue;
            }

            await AuthStore.RevokeSessionAsync(uow, row.Id, moment).ConfigureAwait(false);
            count++;
        }

        return count;
    }

    /// <summary><c>change_username_for_user</c>. Throws <see cref="PyValueErrorException"/> with the operator message.</summary>
    public async Task<string> ChangeUsernameAsync(UnitOfWork uow, long userId, string currentPassword, string newUsername)
    {
        var user = await AuthStore.GetUserAsync(uow, userId).ConfigureAwait(false);
        if (user is null || !user.IsActive)
        {
            throw new PyValueErrorException("Account is not available.");
        }

        if (!VerifyPassword(currentPassword, user.PasswordHash))
        {
            throw new PyValueErrorException("Current password is incorrect.");
        }

        var candidate = (newUsername ?? string.Empty).Trim();
        if (candidate.Length == 0)
        {
            throw new PyValueErrorException("Username is required.");
        }

        if (candidate == user.Username)
        {
            throw new PyValueErrorException("New username must be different from the current username.");
        }

        var clash = await AuthStore.FindUserByLowerUsernameAsync(uow, candidate.ToLowerInvariant()).ConfigureAwait(false);
        if (clash is not null && clash.Id != user.Id)
        {
            throw new PyValueErrorException("That username is already taken.");
        }

        await AuthStore.UpdateUsernameAsync(uow, user.Id, candidate).ConfigureAwait(false);
        return candidate;
    }

    /// <summary><c>change_password_for_user</c>: rotate the hash and revoke every active session.</summary>
    public async Task ChangePasswordAsync(UnitOfWork uow, long userId, string currentPassword, string newPassword)
    {
        var user = await AuthStore.GetUserAsync(uow, userId).ConfigureAwait(false);
        if (user is null || !user.IsActive)
        {
            throw new PyValueErrorException("Account is not available.");
        }

        if (!VerifyPassword(currentPassword, user.PasswordHash))
        {
            throw new PyValueErrorException("Current password is incorrect.");
        }

        if (currentPassword == newPassword)
        {
            throw new PyValueErrorException("New password must be different from the current password.");
        }

        if (PasswordPolicy.Validate(newPassword, user.Username) is { } problem)
        {
            throw new PyValueErrorException(problem);
        }

        await AuthStore.UpdatePasswordHashAsync(uow, user.Id, PasswordHasher.Hash(newPassword)).ConfigureAwait(false);
        await AuthStore.RevokeActiveSessionsForUserAsync(uow, user.Id, Now()).ConfigureAwait(false);
    }

    /// <summary><c>bootstrap_allowed</c>: no usable (active) admin exists.</summary>
    public static async Task<bool> BootstrapAllowedAsync(UnitOfWork uow) =>
        await AuthStore.CountActiveAdminsAsync(uow).ConfigureAwait(false) == 0;

    /// <summary>
    /// <c>create_initial_admin</c>: validate the password, clear any inactive admin rows and insert the
    /// admin. A username clash surfaces as a <see cref="Microsoft.Data.Sqlite.SqliteException"/> constraint error.
    /// </summary>
    public static async Task<UserRecord> CreateInitialAdminAsync(UnitOfWork uow, string username, string password)
    {
        if (!await BootstrapAllowedAsync(uow).ConfigureAwait(false))
        {
            throw new InvalidOperationException(BootstrapNotAllowedMessage);
        }

        if (PasswordPolicy.Validate(password, username) is { } problem)
        {
            throw new PyValueErrorException(problem);
        }

        await AuthStore.DeleteAdminsAsync(uow).ConfigureAwait(false);
        var trimmed = username.Trim();
        var hash = PasswordHasher.Hash(password);
        var id = await AuthStore.InsertUserAsync(uow, trimmed, hash, UserRoles.Admin, isActive: true).ConfigureAwait(false);
        return new UserRecord(id, trimmed, hash, UserRoles.Admin, true);
    }

    private static string ReasonText(SessionInvalidReason reason) => reason switch
    {
        SessionInvalidReason.Revoked => "revoked",
        SessionInvalidReason.AbsoluteExpired => "absolute_expired",
        _ => "idle_expired",
    };
}
