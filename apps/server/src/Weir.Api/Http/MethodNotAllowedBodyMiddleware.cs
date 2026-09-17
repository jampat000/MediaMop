using Microsoft.AspNetCore.Http;

namespace Weir.Api.Http;

/// <summary>
/// Routing answers a known path with the wrong method with an empty 405; FastAPI sends
/// <c>{"detail": "Method Not Allowed"}</c>. This fills in that body.
/// </summary>
public sealed class MethodNotAllowedBodyMiddleware
{
    private readonly RequestDelegate _next;
    private readonly RouteTable _routes;

    public MethodNotAllowedBodyMiddleware(RequestDelegate next, RouteTable routes)
    {
        _next = next;
        _routes = routes;
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
            // Starlette names the methods of the first route whose path matched.
            if (_routes.FirstPathMatch(context.Request.Path) is { } match)
            {
                context.Response.Headers.Allow = string.Join(", ", match.Methods);
            }

            await ApiJson.WriteDetailAsync(context, StatusCodes.Status405MethodNotAllowed, "Method Not Allowed").ConfigureAwait(false);
        }
    }
}
