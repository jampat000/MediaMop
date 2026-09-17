using System.Text.Json.Nodes;

namespace Weir.Api.OpenApi;

/// <summary>
/// Builds <c>/openapi.json</c>: Python's own committed document (embedded at build time from
/// <c>apps/web/openapi/weir-openapi.json</c> — see the <c>EmbeddedResource</c> in Weir.Api.csproj), pruned to
/// only the operations <see cref="Http.RouteTable"/> says the .NET server actually maps.
/// </summary>
/// <remarks>
/// Every schema, parameter and response the resulting document still describes is Python's own, byte for
/// byte — the .NET server is a port that keeps the same HTTP API (README, "Schema parity"; ADR-0017), so its
/// OpenAPI document is a true subset of Python's rather than a hand-rebuilt approximation that could drift
/// from it. An endpoint the .NET server does not map yet is simply absent from the pruned document, the same
/// way FastAPI's own document never lists a route nobody registered. <c>OpenApiDocumentParityTests</c> checks
/// the resulting gap against an explicit, reasoned allowlist so a silent regression (a mapped route dropping
/// out, or an unallowlisted gap appearing) fails the build.
/// </remarks>
public static class WeirOpenApiDocument
{
    private const string ResourceName = "Weir.Api.OpenApi.python-openapi.json";

    /// <summary>The lowercase JSON keys FastAPI/OpenAPI use for HTTP operations under a path item.</summary>
    private static readonly HashSet<string> OperationKeys = new(StringComparer.Ordinal)
    {
        "get", "put", "post", "delete", "options", "head", "patch", "trace",
    };

    private static readonly Lazy<JsonObject> PythonDocument = new(LoadEmbeddedDocument);

    /// <summary>A fresh, independent copy of the embedded Python document, unmodified. For tests only.</summary>
    public static JsonObject LoadPythonDocumentForTests() => Clone(PythonDocument.Value);

    /// <summary>
    /// Python's document, pruned to the <paramref name="implementedRoutes"/> (a <see cref="Http.RouteTable"/>
    /// snapshot: each route's mounted path, which matches Python's path exactly, and the HTTP methods mapped
    /// to it), with <c>info.version</c> set to the running server's own version.
    /// </summary>
    public static JsonObject Build(IReadOnlyList<(string Path, IReadOnlyList<string> Methods)> implementedRoutes, string version)
    {
        ArgumentNullException.ThrowIfNull(implementedRoutes);
        ArgumentNullException.ThrowIfNull(version);
        var implemented = new HashSet<(string Method, string Path)>();
        foreach (var (path, methods) in implementedRoutes)
        {
            foreach (var method in methods)
            {
                implemented.Add((method.ToUpperInvariant(), path));
            }
        }

        var document = Clone(PythonDocument.Value);
        if (document["paths"] is JsonObject paths)
        {
            foreach (var path in paths.Select(entry => entry.Key).ToList())
            {
                if (paths[path] is not JsonObject operations)
                {
                    continue;
                }

                foreach (var method in operations.Select(entry => entry.Key).ToList())
                {
                    if (OperationKeys.Contains(method) && !implemented.Contains((method.ToUpperInvariant(), path)))
                    {
                        operations.Remove(method);
                    }
                }

                if (!operations.Select(entry => entry.Key).Any(OperationKeys.Contains))
                {
                    paths.Remove(path);
                }
            }
        }

        document["info"] ??= new JsonObject();
        document["info"]!["version"] = version;
        return document;
    }

    private static JsonObject Clone(JsonObject document) => document.DeepClone().AsObject();

    private static JsonObject LoadEmbeddedDocument()
    {
        var assembly = typeof(WeirOpenApiDocument).Assembly;
        using var stream = assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException($"Embedded OpenAPI resource '{ResourceName}' was not found.");
        var node = JsonNode.Parse(stream) ?? throw new InvalidOperationException("The embedded OpenAPI document is empty.");
        return node.AsObject();
    }
}
