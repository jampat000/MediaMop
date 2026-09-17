using System.Globalization;
using System.Text;
using System.Text.Json;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// The .NET rules engine against answers recorded from the Python reference by
/// <c>scripts/generate-rules-golden.py</c>. Every golden file holds an input and Python's result;
/// these tests run the same input through <c>Weir.Core.Rules</c> and require the same result,
/// down to the bytes of every note.
/// </summary>
public sealed class GoldenParityTests
{
    private static readonly string GoldenDirectory = Path.Combine(AppContext.BaseDirectory, "Rules", "golden");

    public static TheoryData<string> PlanCases()
    {
        var data = new TheoryData<string>();
        foreach (var path in Directory.GetFiles(GoldenDirectory, "plan-*.json").Order(StringComparer.Ordinal))
        {
            data.Add(Path.GetFileName(path));
        }

        return data;
    }

    [Fact]
    public void The_corpus_is_present_and_large_enough()
    {
        Assert.True(PlanCases().Count >= 60, $"Expected at least 60 plan cases in {GoldenDirectory}.");
    }

    [Theory]
    [MemberData(nameof(PlanCases))]
    public void Plans_match_the_python_engine(string fileName)
    {
        using var document = Load(fileName);
        var input = document.RootElement.GetProperty("input");
        var probe = new ProbeResult(input.GetProperty("probe"));
        var config = ReadConfig(input.GetProperty("config"));

        var actual = Write(writer => WritePlanOutcome(writer, probe, config));

        AssertJsonEqual(document.RootElement.GetProperty("expected"), actual, fileName);
    }

    [Fact]
    public void Sorters_match_the_python_engine()
    {
        using var document = Load("sorters.json");
        var tracks = document.RootElement.GetProperty("tracks").EnumerateArray().Select(ReadSortableTrack).ToList();
        var cases = document.RootElement.GetProperty("cases").EnumerateArray().ToList();
        Assert.NotEmpty(cases);

        foreach (var item in cases)
        {
            var raw = item.GetProperty("input").ValueKind == JsonValueKind.Null ? null : item.GetProperty("input").GetString();
            var actual = Write(writer =>
            {
                var parsed = TrackSorters.Parse(raw);
                writer.WriteStartObject();
                writer.WriteString("parsed", TrackSorters.Dump(parsed));
                writer.WriteString("described", TrackSorters.Describe([.. parsed]));
                writer.WritePropertyName("validated");
                writer.WriteStartObject();
                try
                {
                    writer.WriteString("ok", TrackSorters.Validate(raw));
                }
                catch (TrackSorterException error)
                {
                    writer.WriteString("error", error.Message);
                }

                writer.WriteEndObject();
                writer.WritePropertyName("keys");
                writer.WriteStartArray();
                foreach (var track in tracks)
                {
                    WriteLongs(writer, TrackSorters.SortKeyForTrack(parsed, track));
                }

                writer.WriteEndArray();
                writer.WritePropertyName("ranking");
                writer.WriteStartArray();
                foreach (var track in tracks.OrderBy(t => TrackSorters.SortKeyForTrack(parsed, t), SortKeyComparer.Instance))
                {
                    writer.WriteNumberValue(track.Index);
                }

                writer.WriteEndArray();
                writer.WriteEndObject();
            });

            AssertJsonEqual(item.GetProperty("expected"), actual, $"sorters.json input {raw ?? "None"}");
        }
    }

    [Fact]
    public void Original_language_selection_matches_the_python_engine()
    {
        using var document = Load("original-language.json");
        var cases = document.RootElement.EnumerateArray().ToList();
        Assert.NotEmpty(cases);

        foreach (var item in cases)
        {
            var input = item.GetProperty("input");
            var rulesJson = input.GetProperty("rules");
            var rules = new OriginalLanguageRules
            {
                Enabled = rulesJson.GetProperty("enabled").GetBoolean(),
                AdditionalLanguages = rulesJson.GetProperty("additional_languages").EnumerateArray().Select(e => e.GetString()!).ToList(),
                KeepOnlyFirst = rulesJson.GetProperty("keep_only_first").GetBoolean(),
                FirstIfNone = rulesJson.GetProperty("first_if_none").GetBoolean(),
                TreatEmptyAsOriginal = rulesJson.GetProperty("treat_empty_as_original").GetBoolean(),
            };
            var lookupJson = input.GetProperty("lookup");
            var metadataJson = lookupJson.GetProperty("metadata");
            var lookup = new LookupResult
            {
                Status = lookupJson.GetProperty("status").GetString()!,
                Detail = lookupJson.GetProperty("detail").GetString()!,
                Metadata = metadataJson.ValueKind == JsonValueKind.Null
                    ? null
                    : new TitleMetadata
                    {
                        OriginalLanguage = metadataJson.GetProperty("original_language").GetString()!,
                        Title = metadataJson.GetProperty("title").GetString()!,
                        Year = metadataJson.GetProperty("year").ValueKind == JsonValueKind.Null ? null : metadataJson.GetProperty("year").GetInt32(),
                        ProviderId = metadataJson.GetProperty("provider_id").GetString()!,
                    },
            };
            var tracks = input.GetProperty("tracks").EnumerateArray()
                .Select(t => new OriginalLanguageTrack(t.GetProperty("index").GetInt32(), t.GetProperty("language").GetString()!))
                .ToList();

            var outcome = OriginalLanguage.SelectTracks(rules, lookup, tracks);

            var actual = Write(writer =>
            {
                writer.WriteStartObject();
                writer.WritePropertyName("preferred_indices");
                WriteInts(writer, outcome.PreferredIndices);
                writer.WriteString("note", outcome.Note);
                writer.WriteBoolean("chose", outcome.Chose);
                writer.WriteEndObject();
            });
            AssertJsonEqual(item.GetProperty("expected"), actual, "original-language.json " + item.GetProperty("name").GetString());
        }
    }

    [Fact]
    public void Helpers_match_the_python_engine()
    {
        using var document = Load("helpers.json");
        var root = document.RootElement;

        foreach (var item in root.GetProperty("languages").EnumerateArray())
        {
            var raw = NullableString(item.GetProperty("input"));
            var context = $"language input {raw ?? "None"}";
            Assert.True(item.GetProperty("normalize_lang").GetString() == RemuxRules.NormalizeLang(raw), context + " normalize_lang");
            Assert.True(item.GetProperty("canonical_language").GetString() == OriginalLanguage.CanonicalLanguage(raw), context + " canonical_language");
            Assert.True(item.GetProperty("display").GetString() == RemuxDisplay.LangDisplay(raw), context + " display");
            Assert.True(item.GetProperty("display_or_blank").GetString() == RemuxDisplay.LangDisplayOrBlank(raw), context + " display_or_blank");
        }

        foreach (var item in root.GetProperty("codec_ranks").EnumerateArray())
        {
            Assert.Equal(item.GetProperty("rank").GetInt32(), RemuxRules.AudioCodecQualityRank(NullableString(item.GetProperty("input"))));
        }

        foreach (var item in root.GetProperty("subtitle_langs_csv").EnumerateArray())
        {
            Assert.Equal(Strings(item.GetProperty("output")), RemuxRules.ParseSubtitleLangsCsv(item.GetProperty("input").GetString()));
        }

        foreach (var item in root.GetProperty("additional_languages_csv").EnumerateArray())
        {
            Assert.Equal(Strings(item.GetProperty("output")), OriginalLanguage.ParseAdditionalLanguages(item.GetProperty("input").GetString()));
        }

        foreach (var item in root.GetProperty("audio_preference_modes").EnumerateArray())
        {
            Assert.Equal(item.GetProperty("output").GetString(), RemuxRules.NormalizeAudioPreferenceMode(NullableString(item.GetProperty("input"))));
        }

        foreach (var item in root.GetProperty("path_lines").EnumerateArray())
        {
            Assert.Equal(Strings(item.GetProperty("output")), RemuxRules.ParsePathLines(item.GetProperty("input").GetString()));
        }

        foreach (var item in root.GetProperty("presets").EnumerateArray())
        {
            Assert.Equal(item.GetProperty("output").GetString(), TrackSorters.Dump(TrackSorters.Preset(NullableString(item.GetProperty("input")))));
        }

        Assert.Equal(Strings(root.GetProperty("media_extensions")), RemuxRules.MediaExtensionsSorted());

        var defaults = Write(writer => WriteConfig(writer, RemuxRules.DefaultConfig()));
        AssertJsonEqual(root.GetProperty("default_config"), defaults, "default_config");
    }

    // --- running a case ----------------------------------------------------------------

    /// <summary>The sequence <c>file_remux_pass/run.py</c> runs, as the generator records it.</summary>
    private static void WritePlanOutcome(Utf8JsonWriter writer, ProbeResult probe, RefinerRulesConfig config)
    {
        string json;
        try
        {
            json = Write(w => WritePlanResult(w, probe, config));
        }
        catch (RulesInputException error)
        {
            writer.WriteStartObject();
            writer.WriteString("error", error.PythonError);
            writer.WriteEndObject();
            return;
        }

        using var result = JsonDocument.Parse(json);
        result.RootElement.WriteTo(writer);
    }

    private static void WritePlanResult(Utf8JsonWriter writer, ProbeResult probe, RefinerRulesConfig config)
    {
        var split = RemuxRules.SplitStreams(probe);
        var attachments = RemuxRules.AttachmentStreams(probe);

        writer.WriteStartObject();
        writer.WritePropertyName("split");
        writer.WriteStartObject();
        WriteRawIndices(writer, "video", split.Video);
        WriteRawIndices(writer, "audio", split.Audio);
        WriteRawIndices(writer, "subtitles", split.Subtitles);
        WriteRawIndices(writer, "attachments", attachments);
        writer.WriteEndObject();

        var plan = RemuxRules.PlanRemux(split.Video, split.Audio, split.Subtitles, config, attachments);
        if (plan is null)
        {
            writer.WriteNull("plan");
            writer.WriteEndObject();
            return;
        }

        writer.WritePropertyName("plan");
        WritePlan(writer, plan);
        writer.WriteBoolean("remux_required", RemuxRules.IsRemuxRequired(plan, split.Audio, split.Subtitles));
        writer.WritePropertyName("lines");
        writer.WriteStartObject();
        writer.WriteString("audio_before", RemuxDisplay.AudioBeforeLineFromProbe(split.Audio));
        writer.WriteString("audio_after", RemuxDisplay.AudioAfterLineFromPlan(plan));
        writer.WriteString("subtitle_before", RemuxDisplay.SubtitleBeforeLineFromProbe(split.Subtitles));
        writer.WriteString("subtitle_after", RemuxDisplay.SubtitleAfterLineFromPlan(plan, removeAll: config.SubtitleMode == "remove_all"));
        writer.WriteString("metadata_removed", RemuxDisplay.MetadataRemovedLineFromPlan(plan));
        writer.WriteEndObject();
        writer.WritePropertyName("metadata_argv");
        WriteStrings(writer, MetadataStreams.ArgvFlags(plan.Metadata));
        writer.WriteEndObject();
    }

    private static void WriteRawIndices(Utf8JsonWriter writer, string name, IEnumerable<ProbeStreamInfo> streams)
    {
        writer.WritePropertyName(name);
        writer.WriteStartArray();
        foreach (var stream in streams)
        {
            if (stream.Get("index") is { } index)
            {
                index.WriteTo(writer);
            }
            else
            {
                writer.WriteNullValue();
            }
        }

        writer.WriteEndArray();
    }

    private static void WritePlan(Utf8JsonWriter writer, RemuxPlan plan)
    {
        writer.WriteStartObject();
        writer.WritePropertyName("video_indices");
        WriteInts(writer, plan.VideoIndices);
        writer.WritePropertyName("audio");
        WriteTracks(writer, plan.Audio);
        writer.WritePropertyName("subtitles");
        WriteTracks(writer, plan.Subtitles);
        writer.WritePropertyName("removed_audio");
        WriteStrings(writer, plan.RemovedAudio);
        writer.WritePropertyName("removed_subtitles");
        WriteStrings(writer, plan.RemovedSubtitles);
        writer.WriteNumber("default_audio_output_index", plan.DefaultAudioOutputIndex);
        writer.WritePropertyName("audio_selection_notes");
        WriteStrings(writer, plan.AudioSelectionNotes);
        writer.WritePropertyName("removed_images");
        WriteStrings(writer, plan.RemovedImages);
        writer.WritePropertyName("removed_attachments");
        WriteStrings(writer, plan.RemovedAttachments);
        writer.WritePropertyName("metadata_notes");
        WriteStrings(writer, plan.MetadataNotes);
        writer.WritePropertyName("metadata");
        WriteMetadata(writer, plan.Metadata);
        writer.WriteEndObject();
    }

    private static void WriteTracks(Utf8JsonWriter writer, IEnumerable<PlannedTrack> tracks)
    {
        writer.WriteStartArray();
        foreach (var t in tracks)
        {
            writer.WriteStartObject();
            writer.WriteNumber("input_index", t.InputIndex);
            writer.WriteString("lang_label", t.LangLabel);
            writer.WriteBoolean("commentary", t.Commentary);
            writer.WriteBoolean("forced", t.Forced);
            writer.WriteBoolean("default", t.Default);
            writer.WriteNumber("channels", t.Channels);
            writer.WriteBoolean("lossless", t.Lossless);
            writer.WriteNumber("bitrate", t.Bitrate);
            writer.WriteNumber("codec_rank", t.CodecRank);
            writer.WriteString("codec_name", t.CodecName);
            writer.WriteString("kind", t.Kind == TrackKind.Audio ? "audio" : "subtitle");
            writer.WriteEndObject();
        }

        writer.WriteEndArray();
    }

    private static void WriteMetadata(Utf8JsonWriter writer, MetadataRules rules)
    {
        writer.WriteStartObject();
        writer.WriteBoolean("remove_images", rules.RemoveImages);
        writer.WriteBoolean("remove_attachments", rules.RemoveAttachments);
        writer.WriteBoolean("remove_title", rules.RemoveTitle);
        writer.WriteBoolean("remove_language_tags", rules.RemoveLanguageTags);
        writer.WriteBoolean("remove_other_metadata", rules.RemoveOtherMetadata);
        writer.WriteEndObject();
    }

    private static void WriteConfig(Utf8JsonWriter writer, RefinerRulesConfig config)
    {
        writer.WriteStartObject();
        writer.WriteString("primary_audio_lang", config.PrimaryAudioLang);
        writer.WriteString("secondary_audio_lang", config.SecondaryAudioLang);
        writer.WriteString("tertiary_audio_lang", config.TertiaryAudioLang);
        writer.WriteString("default_audio_slot", config.DefaultAudioSlot);
        writer.WriteBoolean("remove_commentary", config.RemoveCommentary);
        writer.WriteString("subtitle_mode", config.SubtitleMode);
        writer.WritePropertyName("subtitle_langs");
        WriteStrings(writer, config.SubtitleLangs);
        writer.WriteBoolean("preserve_forced_subs", config.PreserveForcedSubs);
        writer.WriteBoolean("preserve_default_subs", config.PreserveDefaultSubs);
        writer.WriteString("audio_preference_mode", config.AudioPreferenceMode);
        writer.WriteString("audio_sorters_json", config.AudioSortersJson);
        writer.WritePropertyName("metadata");
        WriteMetadata(writer, config.Metadata);
        writer.WritePropertyName("preferred_audio_indices");
        WriteInts(writer, config.PreferredAudioIndices);
        writer.WriteString("original_language_note", config.OriginalLanguageNote);
        writer.WriteEndObject();
    }

    private static RefinerRulesConfig ReadConfig(JsonElement json)
    {
        var metadata = json.GetProperty("metadata");
        return new RefinerRulesConfig
        {
            PrimaryAudioLang = json.GetProperty("primary_audio_lang").GetString()!,
            SecondaryAudioLang = json.GetProperty("secondary_audio_lang").GetString()!,
            TertiaryAudioLang = json.GetProperty("tertiary_audio_lang").GetString()!,
            DefaultAudioSlot = json.GetProperty("default_audio_slot").GetString()!,
            RemoveCommentary = json.GetProperty("remove_commentary").GetBoolean(),
            SubtitleMode = json.GetProperty("subtitle_mode").GetString()!,
            SubtitleLangs = Strings(json.GetProperty("subtitle_langs")),
            PreserveForcedSubs = json.GetProperty("preserve_forced_subs").GetBoolean(),
            PreserveDefaultSubs = json.GetProperty("preserve_default_subs").GetBoolean(),
            AudioPreferenceMode = json.GetProperty("audio_preference_mode").GetString()!,
            AudioSortersJson = json.GetProperty("audio_sorters_json").GetString()!,
            Metadata = new MetadataRules
            {
                RemoveImages = metadata.GetProperty("remove_images").GetBoolean(),
                RemoveAttachments = metadata.GetProperty("remove_attachments").GetBoolean(),
                RemoveTitle = metadata.GetProperty("remove_title").GetBoolean(),
                RemoveLanguageTags = metadata.GetProperty("remove_language_tags").GetBoolean(),
                RemoveOtherMetadata = metadata.GetProperty("remove_other_metadata").GetBoolean(),
            },
            PreferredAudioIndices = json.GetProperty("preferred_audio_indices").EnumerateArray().Select(e => e.GetInt32()).ToList(),
            OriginalLanguageNote = json.GetProperty("original_language_note").GetString()!,
        };
    }

    private static SortableTrack ReadSortableTrack(JsonElement json) => new()
    {
        Index = json.GetProperty("index").GetInt32(),
        Language = json.GetProperty("language").GetString()!,
        Title = json.GetProperty("title").GetString()!,
        Commentary = json.GetProperty("commentary").GetBoolean(),
        Default = json.GetProperty("default").GetBoolean(),
        Forced = json.GetProperty("forced").GetBoolean(),
        Channels = json.GetProperty("channels").GetInt64(),
        Bitrate = json.GetProperty("bitrate").GetInt64(),
        Codec = json.GetProperty("codec").GetString()!,
        CodecRank = json.GetProperty("codec_rank").GetInt64(),
    };

    // --- JSON plumbing -----------------------------------------------------------------

    private static JsonDocument Load(string fileName) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(GoldenDirectory, fileName), Encoding.UTF8));

    private static string Write(Action<Utf8JsonWriter> write)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            write(writer);
        }

        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static void WriteStrings(Utf8JsonWriter writer, IEnumerable<string> values)
    {
        writer.WriteStartArray();
        foreach (var value in values)
        {
            writer.WriteStringValue(value);
        }

        writer.WriteEndArray();
    }

    private static void WriteInts(Utf8JsonWriter writer, IEnumerable<int> values)
    {
        writer.WriteStartArray();
        foreach (var value in values)
        {
            writer.WriteNumberValue(value);
        }

        writer.WriteEndArray();
    }

    private static void WriteLongs(Utf8JsonWriter writer, IEnumerable<long> values)
    {
        writer.WriteStartArray();
        foreach (var value in values)
        {
            writer.WriteNumberValue(value);
        }

        writer.WriteEndArray();
    }

    private static string? NullableString(JsonElement element) => element.ValueKind == JsonValueKind.Null ? null : element.GetString();

    private static List<string> Strings(JsonElement array) => array.EnumerateArray().Select(e => e.GetString()!).ToList();

    private static void AssertJsonEqual(JsonElement expected, string actualJson, string context)
    {
        using var actual = JsonDocument.Parse(actualJson);
        var difference = FindDifference(expected, actual.RootElement, "$");
        Assert.True(
            difference is null,
            $"{context}: {difference}\nexpected: {expected.GetRawText()}\nactual:   {actualJson}");
    }

    private static string? FindDifference(JsonElement expected, JsonElement actual, string path)
    {
        if (expected.ValueKind != actual.ValueKind)
        {
            return $"{path}: expected {expected.ValueKind} {expected.GetRawText()}, got {actual.ValueKind} {actual.GetRawText()}";
        }

        switch (expected.ValueKind)
        {
            case JsonValueKind.Object:
                var expectedNames = expected.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal).ToList();
                var actualNames = actual.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal).ToList();
                if (!expectedNames.SequenceEqual(actualNames))
                {
                    return $"{path}: expected keys [{string.Join(", ", expectedNames)}], got [{string.Join(", ", actualNames)}]";
                }

                foreach (var name in expectedNames)
                {
                    var found = FindDifference(expected.GetProperty(name), actual.GetProperty(name), $"{path}.{name}");
                    if (found is not null)
                    {
                        return found;
                    }
                }

                return null;
            case JsonValueKind.Array:
                var expectedItems = expected.EnumerateArray().ToList();
                var actualItems = actual.EnumerateArray().ToList();
                if (expectedItems.Count != actualItems.Count)
                {
                    return $"{path}: expected {expectedItems.Count} items {expected.GetRawText()}, got {actualItems.Count} {actual.GetRawText()}";
                }

                for (var i = 0; i < expectedItems.Count; i++)
                {
                    var found = FindDifference(expectedItems[i], actualItems[i], $"{path}[{i}]");
                    if (found is not null)
                    {
                        return found;
                    }
                }

                return null;
            case JsonValueKind.String:
                return string.Equals(expected.GetString(), actual.GetString(), StringComparison.Ordinal)
                    ? null
                    : $"{path}: expected {expected.GetRawText()}, got {actual.GetRawText()}";
            case JsonValueKind.Number:
                return decimal.Parse(expected.GetRawText(), NumberStyles.Float, CultureInfo.InvariantCulture)
                    == decimal.Parse(actual.GetRawText(), NumberStyles.Float, CultureInfo.InvariantCulture)
                    ? null
                    : $"{path}: expected {expected.GetRawText()}, got {actual.GetRawText()}";
            default:
                return null;
        }
    }
}
