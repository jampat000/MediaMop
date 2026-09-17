using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Weir.Api.Http;
using Weir.Api.OpenApi;
using Weir.Core;
using Weir.Core.Configuration;

namespace Weir.Api.Endpoints;

/// <summary><c>GET /openapi.json</c> (FastAPI's default <c>openapi_url</c>, unauthenticated, not itself listed in its own paths).</summary>
public static class OpenApiEndpoints
{
    public static IEndpointRouteBuilder MapOpenApiEndpoint(this IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var routes = endpoints.ServiceProvider.GetRequiredService<RouteTable>();
        routes.Add("/openapi.json", [HttpMethods.Get], "/openapi.json");

        endpoints.MapMethods("/openapi.json", [HttpMethods.Get], async (HttpContext context) =>
        {
            var document = context.RequestServices.GetRequiredService<WeirOpenApiDocumentCache>();
            var bytes = document.Bytes;
            context.Response.StatusCode = StatusCodes.Status200OK;
            context.Response.ContentType = "application/json";
            context.Response.ContentLength = bytes.Length;
            await context.Response.Body.WriteAsync(bytes, context.RequestAborted).ConfigureAwait(false);
        }).WithMetadata(new RouteLabel("/openapi.json"));
        return endpoints;
    }
}

/// <summary>
/// Builds <see cref="WeirOpenApiDocument"/> once the whole route table is populated (every
/// <c>Map*Endpoints</c> call has run) and caches the serialized bytes for the app's lifetime: the mapped
/// routes and the reported version do not change while running.
/// </summary>
public sealed class WeirOpenApiDocumentCache
{
    private readonly Lazy<byte[]> _bytes;

    public WeirOpenApiDocumentCache(RouteTable routes, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(routes);
        ArgumentNullException.ThrowIfNull(options);
        _bytes = new Lazy<byte[]>(() =>
        {
            var document = WeirOpenApiDocument.Build(routes.Snapshot(), WeirVersion.Resolve(options.VersionOverride));
            return System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(document);
        });
    }

    public byte[] Bytes => _bytes.Value;
}
