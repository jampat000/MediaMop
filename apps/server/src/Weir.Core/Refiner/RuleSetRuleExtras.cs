using System.Text;
using System.Text.Json;
using Weir.Core.Rules;

namespace Weir.Core.Refiner;

/// <summary>
/// Storage for issues #495, #497 and #498's new rule-set fields (<see cref="RefinerRuleSetRecord.RemoveHearingImpairedSubs"/>
/// through <see cref="RefinerRuleSetRecord.RemoveChapters"/>). ADR-0017 freezes the <c>refiner_rule_sets</c> schema until the
/// backend switch-over (#523), and none of these fields exist in the Python schema, so they get no columns of their own.
/// </summary>
/// <remarks>
/// <para>
/// <b>Storage decision.</b> They are packed into the existing <c>subtitle_sorters_json</c> TEXT column, which today stores a
/// plain JSON array of subtitle sorter criteria (see <see cref="TrackSorters"/>) but — unlike <c>audio_sorters_json</c> — is
/// never read by the planner; only the API and the web "Subtitle order" editor round-trip it. That makes it the column an
/// upgrade can extend safely: the plain array shape it has always had (or an empty string) still means exactly what it
/// always meant.
/// </para>
/// <para>
/// <b>Encoded shape.</b> <c>{"sorters": &lt;the plain sorter array, or null&gt;, "rule_extras_v1": {"remove_hearing_impaired_subs":
/// bool, "audio_keep_mode": str, "subtitle_max_per_language": int, "subtitle_quality_strategy": str, "standardize_track_names":
/// bool, "track_name_template": str, "track_name_overrides": {"forced": str, "hearing_impaired": str, "commentary": str,
/// "audio_description": str}, "clear_video_track_names": bool, "remove_chapters": bool}}</c>.
/// </para>
/// <para>
/// <b>Backward and forward compatible.</b> <see cref="Decode"/> treats empty text, or a bare JSON array (exactly what this
/// column held before this change), as that sorter list with every new field at its shipped default — an upgrade changes
/// nothing. An object with no <c>rule_extras_v1</c> key, or one missing individual fields (a value written by an older or a
/// future server), decodes with those fields at their default too. This is the only code that knows the column's format;
/// everywhere else (the API request/response shape, <see cref="RefinerRuleSetRecord"/>, <see cref="RuleSetConversion"/>) sees
/// plain, discrete fields.
/// </para>
/// </remarks>
public static class RuleSetRuleExtras
{
    /// <summary>One decoded column: the plain sorter list JSON (or empty), plus every new field.</summary>
    public sealed record Decoded
    {
        public string SubtitleSortersJson { get; init; } = string.Empty;
        public bool RemoveHearingImpairedSubs { get; init; }
        public string AudioKeepMode { get; init; } = RemuxRuleValues.AudioKeepModeSingle;
        public int SubtitleMaxPerLanguage { get; init; }
        public string SubtitleQualityStrategy { get; init; } = RemuxRuleValues.SubtitleStrategyTextFirst;
        public bool StandardizeTrackNames { get; init; }
        public string TrackNameTemplate { get; init; } = TrackNaming.DefaultTemplate;
        public TrackNameOverrides TrackNameOverrides { get; init; } = new();
        public bool ClearVideoTrackNames { get; init; }
        public bool RemoveChapters { get; init; }
    }

    /// <summary>Decodes a stored <c>subtitle_sorters_json</c> column value. Never throws: anything unusable is read as a bare, empty legacy value.</summary>
    public static Decoded Decode(string? stored)
    {
        var text = (stored ?? string.Empty).Trim();
        if (text.Length == 0)
        {
            return new Decoded();
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(text);
        }
        catch (JsonException)
        {
            return new Decoded { SubtitleSortersJson = text };
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                // A bare array (the legacy/only shape this column used to have) or anything else unexpected:
                // keep it as the sorter list text verbatim, same as before this change existed.
                return new Decoded { SubtitleSortersJson = text };
            }

            var sortersJson = root.TryGetProperty("sorters", out var sortersElement) && sortersElement.ValueKind == JsonValueKind.Array
                ? sortersElement.GetRawText()
                : string.Empty;

            if (!root.TryGetProperty("rule_extras_v1", out var extras) || extras.ValueKind != JsonValueKind.Object)
            {
                return new Decoded { SubtitleSortersJson = sortersJson };
            }

            var defaultOverrides = new TrackNameOverrides();
            return new Decoded
            {
                SubtitleSortersJson = sortersJson,
                RemoveHearingImpairedSubs = ReadBool(extras, "remove_hearing_impaired_subs"),
                AudioKeepMode = ReadString(extras, "audio_keep_mode", RemuxRuleValues.AudioKeepModeSingle),
                SubtitleMaxPerLanguage = ReadInt(extras, "subtitle_max_per_language", 0),
                SubtitleQualityStrategy = ReadString(extras, "subtitle_quality_strategy", RemuxRuleValues.SubtitleStrategyTextFirst),
                StandardizeTrackNames = ReadBool(extras, "standardize_track_names"),
                TrackNameTemplate = ReadString(extras, "track_name_template", TrackNaming.DefaultTemplate),
                TrackNameOverrides = ReadOverrides(extras, defaultOverrides),
                ClearVideoTrackNames = ReadBool(extras, "clear_video_track_names"),
                RemoveChapters = ReadBool(extras, "remove_chapters"),
            };
        }
    }

    /// <summary>Encodes a value for storage in the <c>subtitle_sorters_json</c> column.</summary>
    public static string Encode(Decoded value)
    {
        ArgumentNullException.ThrowIfNull(value);
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            writer.WritePropertyName("sorters");
            WriteSorters(writer, value.SubtitleSortersJson);

            writer.WriteStartObject("rule_extras_v1");
            writer.WriteBoolean("remove_hearing_impaired_subs", value.RemoveHearingImpairedSubs);
            writer.WriteString("audio_keep_mode", value.AudioKeepMode);
            writer.WriteNumber("subtitle_max_per_language", value.SubtitleMaxPerLanguage);
            writer.WriteString("subtitle_quality_strategy", value.SubtitleQualityStrategy);
            writer.WriteBoolean("standardize_track_names", value.StandardizeTrackNames);
            writer.WriteString("track_name_template", value.TrackNameTemplate);
            writer.WriteStartObject("track_name_overrides");
            writer.WriteString("forced", value.TrackNameOverrides.Forced);
            writer.WriteString("hearing_impaired", value.TrackNameOverrides.HearingImpaired);
            writer.WriteString("commentary", value.TrackNameOverrides.Commentary);
            writer.WriteString("audio_description", value.TrackNameOverrides.AudioDescription);
            writer.WriteEndObject();
            writer.WriteBoolean("clear_video_track_names", value.ClearVideoTrackNames);
            writer.WriteBoolean("remove_chapters", value.RemoveChapters);
            writer.WriteEndObject();
            writer.WriteEndObject();
        }

        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static void WriteSorters(Utf8JsonWriter writer, string sortersJson)
    {
        if (string.IsNullOrWhiteSpace(sortersJson))
        {
            writer.WriteNullValue();
            return;
        }

        try
        {
            using var document = JsonDocument.Parse(sortersJson);
            document.RootElement.WriteTo(writer);
        }
        catch (JsonException)
        {
            writer.WriteNullValue();
        }
    }

    private static bool ReadBool(JsonElement obj, string name) =>
        obj.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

    private static string ReadString(JsonElement obj, string name, string fallback) =>
        obj.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? fallback : fallback;

    private static int ReadInt(JsonElement obj, string name, int fallback) =>
        obj.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number) ? number : fallback;

    private static TrackNameOverrides ReadOverrides(JsonElement extras, TrackNameOverrides defaults)
    {
        if (!extras.TryGetProperty("track_name_overrides", out var overrides) || overrides.ValueKind != JsonValueKind.Object)
        {
            return defaults;
        }

        return new TrackNameOverrides
        {
            Forced = ReadString(overrides, "forced", defaults.Forced),
            HearingImpaired = ReadString(overrides, "hearing_impaired", defaults.HearingImpaired),
            Commentary = ReadString(overrides, "commentary", defaults.Commentary),
            AudioDescription = ReadString(overrides, "audio_description", defaults.AudioDescription),
        };
    }
}
