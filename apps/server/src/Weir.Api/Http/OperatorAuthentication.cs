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
/// <c>UserPublicDep</c> for endpoints outside <see cref="ApiRoutes"/>: the request's session cookie, with
/// the <c>last_seen_at</c> touch committed when the request is signed in.
/// </summary>
public sealed class SessionOperatorAuthentication : IOperatorAuthentication
{
    public async ValueTask<OperatorAuthenticationResult> AuthenticateAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var request = new ApiRequest(context);
        await using (request.ConfigureAwait(false))
        {
            try
            {
                await request.RequireUserAsync().ConfigureAwait(false);
            }
            catch (ApiException exception) when (exception.StatusCode == StatusCodes.Status403Forbidden)
            {
                return OperatorAuthenticationResult.InvalidRole;
            }
            catch (ApiException)
            {
                return OperatorAuthenticationResult.NotAuthenticated;
            }

            await request.CommitAsync().ConfigureAwait(false);
            return OperatorAuthenticationResult.SignedIn;
        }
    }
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
