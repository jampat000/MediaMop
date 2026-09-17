using Microsoft.AspNetCore.Http;

namespace Weir.Api.Http;

/// <summary>Result of checking the request's session for a signed-in operator.</summary>
public enum OperatorAuthenticationResult
{
    SignedIn,

    /// <summary>401 <c>Not authenticated.</c></summary>
    NotAuthenticated,

    /// <summary>403 <c>Invalid account role.</c></summary>
    InvalidRole,
}

/// <summary>
/// Resolves the signed-in operator for endpoints that Python guards with <c>UserPublicDep</c>.
/// </summary>
public interface IOperatorAuthentication
{
    ValueTask<OperatorAuthenticationResult> AuthenticateAsync(HttpContext context);
}

/// <summary>
/// Until sessions are ported (#517) no request is signed in, so guarded endpoints answer exactly
/// as Python answers a request without a valid session cookie.
/// </summary>
public sealed class SessionsNotPortedAuthentication : IOperatorAuthentication
{
    public ValueTask<OperatorAuthenticationResult> AuthenticateAsync(HttpContext context) =>
        ValueTask.FromResult(OperatorAuthenticationResult.NotAuthenticated);
}

internal static class OperatorAuthenticationExtensions
{
    /// <summary>Writes the Python error response and returns <see langword="false"/> unless signed in.</summary>
    public static async Task<bool> RequireOperatorAsync(this IOperatorAuthentication authentication, HttpContext context)
    {
        switch (await authentication.AuthenticateAsync(context).ConfigureAwait(false))
        {
            case OperatorAuthenticationResult.SignedIn:
                return true;
            case OperatorAuthenticationResult.InvalidRole:
                await ApiJson.WriteDetailAsync(context, StatusCodes.Status403Forbidden, "Invalid account role.").ConfigureAwait(false);
                return false;
            default:
                await ApiJson.WriteDetailAsync(context, StatusCodes.Status401Unauthorized, "Not authenticated.").ConfigureAwait(false);
                return false;
        }
    }
}
