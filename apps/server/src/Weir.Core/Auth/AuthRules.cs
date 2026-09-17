using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Time;

namespace Weir.Core.Auth;

/// <summary>Values persisted in <c>users.role</c>.</summary>
public static class UserRoles
{
    public const string Admin = "admin";
    public const string Operator = "operator";
    public const string Viewer = "viewer";

    public static readonly IReadOnlySet<string> Valid = new HashSet<string>(StringComparer.Ordinal) { Admin, Operator, Viewer };

    public static readonly IReadOnlySet<string> AdminOnly = new HashSet<string>(StringComparer.Ordinal) { Admin };

    public static readonly IReadOnlySet<string> OperatorOrAdmin = new HashSet<string>(StringComparer.Ordinal) { Admin, Operator };
}

/// <summary>A <c>users</c> row.</summary>
public sealed record UserRecord(long Id, string Username, string PasswordHash, string Role, bool IsActive);

/// <summary>A <c>user_sessions</c> row. <see cref="Id"/> is the stored 32-character hex UUID.</summary>
public sealed record UserSessionRecord(
    string Id,
    long UserId,
    string TokenHash,
    PyDateTime CreatedAt,
    PyDateTime AbsoluteExpiresAt,
    bool IsTrustedDevice,
    PyDateTime LastSeenAt,
    PyDateTime? RevokedAt,
    string ClientLabel)
{
    /// <summary><c>str(uuid)</c>: the hyphenated form the API shows.</summary>
    public string PublicId => Guid.TryParseExact(Id, "N", out var guid) ? guid.ToString("D") : Id;
}

/// <summary>Why a session no longer authenticates.</summary>
public enum SessionInvalidReason
{
    Revoked,
    AbsoluteExpired,
    IdleExpired,
}

/// <summary>Port of the pure rules in <c>weir.platform.auth.sessions</c> and <c>service</c>.</summary>
public static class SessionRules
{
    public const int MaxActiveSessionsPerUser = 5;
    public const string DefaultClientLabel = "Browser session";

    public static TimeSpan EffectiveIdleTimeout(bool isTrustedDevice, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        return Minutes(isTrustedDevice ? options.SessionTrustedIdleMinutes : options.SessionIdleMinutes);
    }

    public static long AbsoluteTimeoutDays(bool isTrustedDevice, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        return isTrustedDevice ? options.SessionTrustedAbsoluteDays : options.SessionAbsoluteDays;
    }

    public static long IdleTimeoutMinutes(bool isTrustedDevice, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        return isTrustedDevice ? options.SessionTrustedIdleMinutes : options.SessionIdleMinutes;
    }

    public static SessionInvalidReason? InvalidReason(UserSessionRecord row, TimeSpan idle, DateTime nowUtc)
    {
        ArgumentNullException.ThrowIfNull(row);
        if (row.RevokedAt is not null)
        {
            return SessionInvalidReason.Revoked;
        }

        if (nowUtc >= row.AbsoluteExpiresAt.AsUtc)
        {
            return SessionInvalidReason.AbsoluteExpired;
        }

        return nowUtc > SafeAdd(row.LastSeenAt.AsUtc, idle) ? SessionInvalidReason.IdleExpired : null;
    }

    /// <summary><c>_session_last_seen_touch_gap</c>: at most 60 s, at most half the idle window.</summary>
    public static TimeSpan LastSeenTouchGap(TimeSpan idle)
    {
        var half = TimeSpan.FromTicks(idle.Ticks / 2);
        var cap = TimeSpan.FromSeconds(60);
        return half < cap ? half : cap;
    }

    public static TimeSpan Minutes(long minutes) =>
        minutes > TimeSpan.MaxValue.TotalMinutes ? TimeSpan.MaxValue : TimeSpan.FromMinutes(minutes);

    public static TimeSpan Days(long days) =>
        days > TimeSpan.MaxValue.TotalDays ? TimeSpan.MaxValue : TimeSpan.FromDays(days);

    public static DateTime SafeAdd(DateTime value, TimeSpan span) =>
        span.Ticks > DateTime.MaxValue.Ticks - value.Ticks ? DateTime.MaxValue : value + span;

    public static DateTime SafeSubtract(DateTime value, TimeSpan span) =>
        span.Ticks > value.Ticks ? DateTime.MinValue : value - span;

    /// <summary><c>client_label_from_user_agent</c>: a coarse, non-identifying label.</summary>
    public static string ClientLabelFromUserAgent(string? userAgent)
    {
        var value = (userAgent ?? string.Empty).ToLowerInvariant();
        var browser = "Browser";
        if (value.Contains("edg/", StringComparison.Ordinal) || value.Contains("edge/", StringComparison.Ordinal))
        {
            browser = "Edge";
        }
        else if (value.Contains("chrome/", StringComparison.Ordinal) || value.Contains("crios/", StringComparison.Ordinal))
        {
            browser = "Chrome";
        }
        else if (value.Contains("firefox/", StringComparison.Ordinal) || value.Contains("fxios/", StringComparison.Ordinal))
        {
            browser = "Firefox";
        }
        else if (value.Contains("safari/", StringComparison.Ordinal) && !value.Contains("chrome/", StringComparison.Ordinal))
        {
            browser = "Safari";
        }
        else if (value.Contains("electron/", StringComparison.Ordinal))
        {
            browser = "Weir app";
        }

        var platform = "device";
        if (value.Contains("windows", StringComparison.Ordinal))
        {
            platform = "Windows";
        }
        else if (value.Contains("mac os", StringComparison.Ordinal) || value.Contains("macintosh", StringComparison.Ordinal))
        {
            platform = "macOS";
        }
        else if (value.Contains("android", StringComparison.Ordinal))
        {
            platform = "Android";
        }
        else if (value.Contains("iphone", StringComparison.Ordinal) || value.Contains("ipad", StringComparison.Ordinal) || value.Contains("ios", StringComparison.Ordinal))
        {
            platform = "iOS";
        }
        else if (value.Contains("linux", StringComparison.Ordinal))
        {
            platform = "Linux";
        }

        return PyStrings.Slice($"{browser} on {platform}", 80);
    }

    /// <summary><c>resolve_cookie_secure</c>.</summary>
    public static bool ResolveCookieSecure(string? requestScheme, CookieSecureMode mode) => mode switch
    {
        CookieSecureMode.Always => true,
        CookieSecureMode.Never => false,
        _ => string.Equals((requestScheme ?? string.Empty).Trim(), "https", StringComparison.OrdinalIgnoreCase),
    };

    public static string SameSiteText(CookieSameSite sameSite) => sameSite switch
    {
        CookieSameSite.Strict => "strict",
        CookieSameSite.None => "none",
        _ => "lax",
    };

    public static string SecureModeText(CookieSecureMode mode) => mode switch
    {
        CookieSecureMode.Always => "always",
        CookieSecureMode.Never => "never",
        _ => "auto",
    };
}
