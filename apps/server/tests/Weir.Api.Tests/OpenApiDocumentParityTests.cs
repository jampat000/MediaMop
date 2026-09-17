using System.Net;
using System.Text.Json.Nodes;

namespace Weir.Api.Tests;

/// <summary>
/// <c>GET /openapi.json</c> is Python's own committed document (<c>apps/web/openapi/weir-openapi.json</c>,
/// embedded into Weir.Api at build time — see <c>OpenApi/WeirOpenApiDocument.cs</c>), pruned to the routes
/// the .NET server actually maps. These tests read a normalized structural view — paths+methods, and each
/// component schema's property names, required list and enum values — and compare it against the committed
/// Python document, so:
///
/// - every path+method the .NET server implements matches Python's document exactly (same schemas, because
///   they are literally the same JSON), and
/// - the only paths+methods missing are the ones in <see cref="KnownGaps"/>, each with a reason, so a route
///   that quietly stops being served (or a newly-ported route nobody removed from the allowlist) fails here
///   instead of surfacing later as a broken web build against <c>openapi-typescript</c> output.
/// </summary>
public sealed class OpenApiDocumentParityTests
{
    /// <summary>
    /// Python operations the .NET server does not answer yet, each with why. Every entry must be a real gap:
    /// <see cref="Not_implemented_yet_matches_exactly_the_allowlisted_gaps"/> fails if the .NET server starts
    /// answering one (remove it here) or stops answering one that is not listed (add it here with a reason).
    /// </summary>
    private static readonly (string Method, string Path, string Reason)[] KnownGaps =
    [
        ("GET", "/api/v1/refiner/libraries/discover/{connection_id}",
            "Media-manager library discovery browsing is not ported yet (depends on the manager browsing APIs)."),
        ("GET", "/api/v1/refiner/libraries/discover/{connection_id}/drift",
            "Same discovery feature as the row above; the drift report depends on the same unported browsing code."),
        ("POST", "/api/v1/refiner/libraries/discover/{connection_id}/import",
            "Same discovery feature; importing a discovered library depends on the same unported browsing code."),
        ("POST", "/api/v1/refiner/libraries/{library_id}/unlink",
            "Library unlink (detach without deleting rows) is not ported yet."),
        ("GET", "/api/v1/refiner/reject-support",
            "The reject-support bundle download is not ported yet."),
        ("POST", "/api/v1/refiner/jobs/file-remux-pass/enqueue",
            "Manual remux-pass enqueue; the remux pass itself is being ported on a parallel branch (port/remux-pass)."),
        ("POST", "/api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue",
            "Manual watched-folder scan dispatch enqueue; same remux-pass dependency as the row above."),
    ];

    [Fact]
    public async Task Serves_openapi_json_unauthenticated_with_the_running_version()
    {
        await using var server = await WeirTestServer.StartAsync();

        using var response = await server.Client.GetAsync("/openapi.json");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/json", response.Content.Headers.ContentType?.ToString());
        var document = JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsObject();
        Assert.Equal("Weir API", document["info"]!["title"]!.GetValue<string>());
        Assert.Equal(Core.WeirVersion.BuildVersion, document["info"]!["version"]!.GetValue<string>());
        Assert.Equal("3.1.0", document["openapi"]!.GetValue<string>());
    }

    [Fact]
    public async Task Every_served_path_and_method_matches_a_real_python_operation()
    {
        await using var server = await WeirTestServer.StartAsync();
        using var response = await server.Client.GetAsync("/openapi.json");
        var dotnet = PathMethods(JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsObject());
        var python = PathMethods(PythonDocument());

        var unexpected = dotnet.Except(python).ToList();
        Assert.True(unexpected.Count == 0, "The .NET document serves operations Python's does not: " + string.Join(", ", unexpected));
    }

    [Fact]
    public async Task Not_implemented_yet_matches_exactly_the_allowlisted_gaps()
    {
        await using var server = await WeirTestServer.StartAsync();
        using var response = await server.Client.GetAsync("/openapi.json");
        var dotnet = PathMethods(JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsObject());
        var python = PathMethods(PythonDocument());
        var allowlisted = KnownGaps.Select(gap => (gap.Method, gap.Path)).ToHashSet();

        var missing = python.Except(dotnet).ToList();
        var unaccountedFor = missing.Except(allowlisted).ToList();
        Assert.True(
            unaccountedFor.Count == 0,
            "Python has operations the .NET document is missing without an allowlist reason: " +
            string.Join(", ", unaccountedFor.Select(pair => $"{pair.Method} {pair.Path}")));

        var stale = allowlisted.Except(missing).ToList();
        Assert.True(
            stale.Count == 0,
            "Allowlisted gaps that the .NET server now answers (remove from KnownGaps): " +
            string.Join(", ", stale.Select(pair => $"{pair.Method} {pair.Path}")));
    }

    [Fact]
    public async Task Component_schemas_for_served_operations_match_python_property_names_required_and_enums()
    {
        await using var server = await WeirTestServer.StartAsync();
        using var response = await server.Client.GetAsync("/openapi.json");
        var dotnet = JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsObject();
        var python = PythonDocument();

        var dotnetSchemas = ((JsonObject?)dotnet["components"]?["schemas"]) ?? [];
        var pythonSchemas = ((JsonObject?)python["components"]?["schemas"]) ?? [];
        Assert.NotEmpty(pythonSchemas);

        // Every schema the .NET document still references must be Python's own, unedited shape. (The .NET
        // document never prunes components, only paths, so this also proves that has not changed by accident.)
        foreach (var (name, schemaNode) in dotnetSchemas)
        {
            Assert.True(pythonSchemas.ContainsKey(name), $"Schema '{name}' in the .NET document does not exist in Python's.");
            var expected = ShapeOf(pythonSchemas[name]!.AsObject());
            var actual = ShapeOf(schemaNode!.AsObject());
            Assert.Equal(expected.Properties, actual.Properties);
            Assert.Equal(expected.Required, actual.Required);
            Assert.Equal(expected.Enum, actual.Enum);
        }
    }

    private static JsonObject PythonDocument()
    {
        var root = RepositoryRoot() ?? throw new InvalidOperationException("Could not find the repository root from the test assembly.");
        var path = Path.Join(root, "apps", "web", "openapi", "weir-openapi.json");
        using var stream = File.OpenRead(path);
        return JsonNode.Parse(stream)!.AsObject();
    }

    private static string? RepositoryRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            if (Directory.Exists(Path.Join(directory.FullName, "apps", "server")) &&
                File.Exists(Path.Join(directory.FullName, "apps", "web", "openapi", "weir-openapi.json")))
            {
                return directory.FullName;
            }
        }

        return null;
    }

    private static readonly string[] OperationKeys = ["get", "put", "post", "delete", "options", "head", "patch", "trace"];

    private static HashSet<(string Method, string Path)> PathMethods(JsonObject document)
    {
        var result = new HashSet<(string Method, string Path)>();
        if (document["paths"] is not JsonObject paths)
        {
            return result;
        }

        foreach (var (path, operationsNode) in paths)
        {
            if (operationsNode is not JsonObject operations)
            {
                continue;
            }

            foreach (var (method, _) in operations)
            {
                if (OperationKeys.Contains(method))
                {
                    result.Add((method.ToUpperInvariant(), path));
                }
            }
        }

        return result;
    }

    private sealed record SchemaShape(
        IReadOnlyList<string> Properties,
        IReadOnlyList<string> Required,
        IReadOnlyList<string> Enum);

    private static SchemaShape ShapeOf(JsonObject schema)
    {
        var properties = schema["properties"] is JsonObject props
            ? props.Select(entry => entry.Key).OrderBy(name => name, StringComparer.Ordinal).ToList()
            : [];
        var required = schema["required"] is JsonArray requiredArray
            ? requiredArray.Select(node => node!.GetValue<string>()).OrderBy(name => name, StringComparer.Ordinal).ToList()
            : [];
        var enumValues = schema["enum"] is JsonArray enumArray
            ? enumArray.Select(node => node!.ToJsonString()).OrderBy(value => value, StringComparer.Ordinal).ToList()
            : [];
        return new SchemaShape(properties, required, enumValues);
    }
}
