using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Weir.Core.Validation;

namespace Weir.Api.Http;

/// <summary>Maps API routes with FastAPI's request lifecycle.</summary>
public static class ApiRoutes
{
    public const string V1Prefix = "/api/v1";

    /// <summary>
    /// A route under <c>/api/v1</c>. <paramref name="path"/> is the path in the Python router (also the metrics
    /// label). The handler runs with a unit of work that is committed when it returns a result; an
    /// <see cref="ApiException"/> or validation error discards uncommitted work and is answered as FastAPI does.
    /// </summary>
    public static IEndpointConventionBuilder MapV1(this IEndpointRouteBuilder endpoints, string method, string path, Func<ApiRequest, Task<ApiResult>> handler) =>
        endpoints.MapApi(method, V1Prefix + path, path, handler);

    public static IEndpointConventionBuilder MapApi(this IEndpointRouteBuilder endpoints, string method, string template, string label, Func<ApiRequest, Task<ApiResult>> handler)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(handler);
        endpoints.ServiceProvider.GetRequiredService<RouteTable>().Add(template, [method], label);
        return endpoints
            .MapMethods(template, [method], context => RunAsync(context, handler))
            .WithMetadata(new RouteLabel(label));
    }

    internal static async Task RunAsync(HttpContext context, Func<ApiRequest, Task<ApiResult>> handler)
    {
        var request = new ApiRequest(context);
        await using (request.ConfigureAwait(false))
        {
            ApiResult result;
            try
            {
                result = await handler(request).ConfigureAwait(false);
                await request.CommitAsync().ConfigureAwait(false);
            }
            catch (ApiException exception)
            {
                await PyResponses.WriteDetailAsync(context, exception).ConfigureAwait(false);
                return;
            }
            catch (RequestValidationException exception)
            {
                await PyResponses.WriteValidationErrorAsync(context, exception).ConfigureAwait(false);
                return;
            }

            switch (result)
            {
                case JsonApiResult json:
                    foreach (var (name, value) in json.Headers)
                    {
                        context.Response.Headers.Append(name, value);
                    }

                    await PyResponses.WriteJsonAsync(context, json.StatusCode, json.Body).ConfigureAwait(false);
                    break;
                case CustomApiResult custom:
                    await custom.Write(context).ConfigureAwait(false);
                    break;
                default:
                    throw new InvalidOperationException("Unknown API result.");
            }
        }
    }

    public static JsonApiResult Ok(Core.Json.PyJson body) => new(StatusCodes.Status200OK, body);
}
