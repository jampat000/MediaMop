using Microsoft.AspNetCore.Http;

namespace Weir.Api.Http;

/// <summary>
/// Routing answers a known path with the wrong method with an empty 405; FastAPI sends
/// <c>{"detail": "Method Not Allowed"}</c>. This fills in that body.
/// </summary>
public sealed class MethodNotAllowedBodyMiddleware
{
    private readonly RequestDelegate _next;

    public MethodNotAllowedBodyMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        await _next(context).ConfigureAwait(false);
        if (context.Response.StatusCode == StatusCodes.Status405MethodNotAllowed &&
            !context.Response.HasStarted &&
            context.Response.ContentLength is null or 0 &&
            string.IsNullOrEmpty(context.Response.ContentType))
        {
            await ApiJson.WriteDetailAsync(context, StatusCodes.Status405MethodNotAllowed, "Method Not Allowed").ConfigureAwait(false);
        }
    }
}
