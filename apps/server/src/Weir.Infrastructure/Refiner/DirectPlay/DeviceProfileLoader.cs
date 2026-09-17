using System.Text.Json;
using Microsoft.Extensions.Logging;
using Weir.Core.Refiner;

namespace Weir.Infrastructure.Refiner.DirectPlay;

/// <summary>
/// Loads the Direct Play device list: the operator's <c>WEIR_HOME/direct-play-devices.json</c> override
/// when present and readable, otherwise the shipped <c>devices.json</c> embedded resource (port of
/// <c>refiner/direct_play/__init__.py</c>'s <c>load_device_profiles</c>).
/// </summary>
public static class DeviceProfileLoader
{
    private const string EmbeddedResourceName = "Weir.Infrastructure.Refiner.DirectPlay.devices.json";

    public static IReadOnlyList<DeviceProfile> Load(string? weirHome, ILogger? logger = null)
    {
        if (!string.IsNullOrEmpty(weirHome))
        {
            var overridePath = Path.Combine(weirHome, DirectPlayEvaluation.OverrideFileName);
            if (File.Exists(overridePath))
            {
                try
                {
                    return ParseDocument(File.ReadAllText(overridePath));
                }
                catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
                {
                    logger?.LogWarning(exception, "Ignoring {Path}: it is not a readable device list.", overridePath);
                }
            }
        }

        using var stream = typeof(DeviceProfileLoader).Assembly.GetManifestResourceStream(EmbeddedResourceName)
            ?? throw new InvalidOperationException($"Embedded resource {EmbeddedResourceName} was not found.");
        using var reader = new StreamReader(stream);
        return ParseDocument(reader.ReadToEnd());
    }

    private static List<DeviceProfile> ParseDocument(string text)
    {
        using var document = JsonDocument.Parse(text);
        var devices = document.RootElement.GetProperty("devices");
        var result = new List<DeviceProfile>();
        foreach (var item in devices.EnumerateArray())
        {
            result.Add(ParseProfile(item));
        }

        return result;
    }

    private static DeviceProfile ParseProfile(JsonElement item)
    {
        var containers = item.TryGetProperty("containers", out var c) ? c : default;
        var audio = item.TryGetProperty("audio", out var a) ? a : default;
        return new DeviceProfile(
            item.GetProperty("id").GetString() ?? string.Empty,
            item.GetProperty("name").GetString() ?? string.Empty,
            item.TryGetProperty("source", out var source) ? source.GetString() ?? string.Empty : string.Empty,
            item.TryGetProperty("note", out var note) ? note.GetString() ?? string.Empty : string.Empty,
            StringSet(containers, "yes"),
            StringSet(containers, "maybe"),
            VideoLimits(item, "video"),
            VideoLimits(item, "video_maybe"),
            StringSet(audio, "yes"),
            StringSet(audio, "maybe"));
    }

    private static HashSet<string> StringSet(JsonElement parent, string property)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(property, out var array) || array.ValueKind != JsonValueKind.Array)
        {
            return new HashSet<string>(StringComparer.Ordinal);
        }

        return new HashSet<string>(array.EnumerateArray().Select(e => e.GetString() ?? string.Empty), StringComparer.Ordinal);
    }

    private static Dictionary<string, DeviceVideoLimits> VideoLimits(JsonElement item, string property)
    {
        var result = new Dictionary<string, DeviceVideoLimits>(StringComparer.Ordinal);
        if (!item.TryGetProperty(property, out var video) || video.ValueKind != JsonValueKind.Object)
        {
            return result;
        }

        foreach (var codec in video.EnumerateObject())
        {
            int? maxHeight = codec.Value.TryGetProperty("max_height", out var h) && h.ValueKind == JsonValueKind.Number ? h.GetInt32() : null;
            int? maxDepth = codec.Value.TryGetProperty("max_bit_depth", out var d) && d.ValueKind == JsonValueKind.Number ? d.GetInt32() : null;
            HashSet<string>? containers = codec.Value.TryGetProperty("containers", out var containersElement) && containersElement.ValueKind == JsonValueKind.Array
                ? [.. containersElement.EnumerateArray().Select(e => e.GetString() ?? string.Empty)]
                : null;
            result[codec.Name] = new DeviceVideoLimits(maxHeight, maxDepth, containers);
        }

        return result;
    }
}
