using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using Microsoft.AspNetCore.Http;

namespace Weir.Api.Http;

/// <summary>FastAPI's error body: <c>{"detail": "..."}</c>.</summary>
public sealed record ErrorDetail([property: JsonPropertyName("detail")] string Detail);

public sealed record HealthResponse(
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("dependencies")] IReadOnlyDictionary<string, string> Dependencies);

public sealed record ReadinessStepResponse(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("detail")] string Detail);

public sealed record ReadinessWorkerResponse(
    [property: JsonPropertyName("module")] string Module,
    [property: JsonPropertyName("expected_workers")] int ExpectedWorkers,
    [property: JsonPropertyName("active_workers")] int ActiveWorkers,
    [property: JsonPropertyName("stale_workers")] int StaleWorkers,
    [property: JsonPropertyName("stopped_workers")] int StoppedWorkers,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("detail")] string Detail);

public sealed record ReadinessResponse(
    [property: JsonPropertyName("ready")] bool Ready,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("startup_seconds")] double StartupSeconds,
    [property: JsonPropertyName("steps")] IReadOnlyList<ReadinessStepResponse> Steps,
    [property: JsonPropertyName("worker_health")] IReadOnlyList<ReadinessWorkerResponse> WorkerHealth);

public sealed record PublicReadinessResponse(
    [property: JsonPropertyName("ready")] bool Ready,
    [property: JsonPropertyName("status")] string Status);

[JsonSourceGenerationOptions(WriteIndented = false)]
[JsonSerializable(typeof(ErrorDetail))]
[JsonSerializable(typeof(HealthResponse))]
[JsonSerializable(typeof(ReadinessResponse))]
[JsonSerializable(typeof(PublicReadinessResponse))]
internal sealed partial class ApiJsonContext : JsonSerializerContext;

internal static class ApiJson
{
    /// <summary>Write a JSON body the way FastAPI does: compact, <c>Content-Type: application/json</c>.</summary>
    public static async Task WriteAsync<T>(HttpContext context, int statusCode, T value, JsonTypeInfo<T> typeInfo)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        var bytes = System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(value, typeInfo);
        context.Response.ContentLength = bytes.Length;
        await context.Response.Body.WriteAsync(bytes, context.RequestAborted).ConfigureAwait(false);
    }

    public static Task WriteDetailAsync(HttpContext context, int statusCode, string detail) =>
        WriteAsync(context, statusCode, new ErrorDetail(detail), ApiJsonContext.Default.ErrorDetail);
}
