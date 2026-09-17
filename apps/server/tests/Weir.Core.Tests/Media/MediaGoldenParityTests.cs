using System.Globalization;
using System.Text.Json;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Media;

/// <summary>
/// <c>Weir.Core.Media</c> against answers recorded from the Python reference by
/// <c>scripts/generate-ffmpeg-golden.py</c>: command lines token for token, hardware choices, output
/// validation messages and Python's text handling. The orchestration (ffprobe logs, progress runs,
/// detection) is held to the same files in <c>Weir.Infrastructure.Tests</c>.
/// </summary>
public sealed class MediaGoldenParityTests
{
    private static readonly string GoldenDirectory = Path.Combine(AppContext.BaseDirectory, "Media", "golden");

    [Fact]
    public void Remux_command_lines_match_the_python_layer()
    {
        using var document = Load("argv.json");
        var cases = document.RootElement.GetProperty("remux").EnumerateArray().ToList();
        Assert.True(cases.Count >= 40, $"Expected at least 40 remux argv cases, found {cases.Count}.");

        foreach (var item in cases)
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            var flags = input.GetProperty("input_flags");
            var argv = FfmpegCommands.BuildRemuxArgv(
                input.GetProperty("ffmpeg_bin").GetString()!,
                input.GetProperty("src").GetString()!,
                input.GetProperty("dst").GetString()!,
                ReadPlan(input.GetProperty("plan")),
                flags.ValueKind == JsonValueKind.Null ? null : Strings(flags));

            var expected = item.GetProperty("expected");
            var expectedArgv = GoldenDivergences.RemuxArgv(Strings(expected.GetProperty("argv")), input);
            AssertTokens(expectedArgv, argv, name);
            // #547 changed the plain argv (see GoldenDivergences.RemuxArgv), which shifts where "-progress pipe:1
            // -nostats" lands relative to the output path too; re-deriving the expectation from the same patched
            // list (rather than patching the fixture's separately-recorded progress_argv a second, differently
            // shaped way) keeps this a proof of WithProgress's insertion logic instead of a second copy of item 1-3.
            AssertTokens(FfmpegCommands.WithProgress(expectedArgv), FfmpegCommands.WithProgress(argv), name + " (progress)");
        }
    }

    [Fact]
    public void Ffprobe_integrity_and_progress_command_lines_match_the_python_layer()
    {
        using var document = Load("argv.json");
        var root = document.RootElement;
        foreach (var item in root.GetProperty("ffprobe").EnumerateArray())
        {
            var input = item.GetProperty("input");
            var argv = FfmpegCommands.BuildFfprobeArgv(
                input.GetProperty("ffprobe_bin").GetString()!,
                input.GetProperty("src").GetString()!,
                input.GetProperty("probe_size_mb").GetInt64(),
                input.GetProperty("analyze_duration_seconds").GetInt64());
            AssertTokens(GoldenDivergences.FfprobeArgv(Strings(item.GetProperty("expected"))), argv, input.GetRawText());
        }

        foreach (var item in root.GetProperty("integrity").EnumerateArray())
        {
            var input = item.GetProperty("input");
            var argv = FfmpegCommands.BuildIntegrityArgv(input.GetProperty("ffmpeg_bin").GetString()!, input.GetProperty("path").GetString()!);
            AssertTokens(Strings(item.GetProperty("expected")), argv, input.GetRawText());
        }

        foreach (var item in root.GetProperty("progress_argv").EnumerateArray())
        {
            AssertTokens(Strings(item.GetProperty("expected")), FfmpegCommands.WithProgress(Strings(item.GetProperty("input"))), item.GetRawText());
        }

        var constants = root.GetProperty("constants");
        Assert.True(constants.GetProperty("REFINER_FFMPEG_TIMEOUT_S").GetInt32() == FfmpegCommands.FfmpegTimeoutSeconds, "REFINER_FFMPEG_TIMEOUT_S");
        Assert.True(constants.GetProperty("REFINER_FFMPEG_SLOW_GRACE_S").GetInt32() == FfmpegCommands.FfmpegSlowGraceSeconds, "REFINER_FFMPEG_SLOW_GRACE_S");
        Assert.True(constants.GetProperty("REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S").GetInt32() == FfmpegCommands.FfmpegMaxProjectedRemainingSeconds, "REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S");
        Assert.True(constants.GetProperty("_REFINER_FFPROBE_LOG_MAX_CHARS").GetInt32() == FfmpegCommands.ProbeLogMaxChars, "_REFINER_FFPROBE_LOG_MAX_CHARS");
        Assert.True(constants.GetProperty("_REFINER_FFMPEG_STDERR_TAIL_BYTES").GetInt32() == FfmpegCommands.FfmpegStderrTailBytes, "_REFINER_FFMPEG_STDERR_TAIL_BYTES");
        Assert.Equal(Strings(constants.GetProperty("_UNREADABLE_MEDIA_MARKERS")), ProbeOutput.UnreadableMediaMarkers);
    }

    [Fact]
    public void Hardware_decisions_match_the_python_layer()
    {
        using var document = Load("hardware.json");
        var root = document.RootElement;
        var decisions = root.GetProperty("decisions").EnumerateArray().ToList();
        Assert.NotEmpty(decisions);

        foreach (var item in decisions)
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            var settingsJson = input.GetProperty("settings");
            var settings = new HardwareSettings
            {
                Mode = settingsJson.GetProperty("mode").GetString()!,
                Device = settingsJson.GetProperty("device").GetString()!,
                DisabledVendors = Strings(settingsJson.GetProperty("disabled_vendors")),
                Strictness = settingsJson.GetProperty("strictness").GetString()!,
            };
            Assert.Equal(settingsJson.GetProperty("wants_hardware").GetBoolean(), settings.WantsHardware);
            var reportJson = input.GetProperty("report");
            var report = new AccelerationReport
            {
                AvailableMethods = Strings(reportJson.GetProperty("available_methods")),
                Detected = reportJson.GetProperty("detected").GetBoolean(),
                Detail = reportJson.GetProperty("detail").GetString()!,
            };
            Assert.Equal(Strings(reportJson.GetProperty("vendors")), report.Vendors);

            var decision = HardwareAcceleration.Decide(settings, report);

            var expected = item.GetProperty("expected");
            Assert.True(expected.GetProperty("method").GetString() == decision.Method, name);
            AssertTokens(Strings(expected.GetProperty("argv_flags")), decision.ArgvFlags, name);
            Assert.True(expected.GetProperty("fell_back_to_software").GetBoolean() == decision.FellBackToSoftware, name);
            Assert.True(expected.GetProperty("using_hardware").GetBoolean() == decision.UsingHardware, name);
            Assert.Equal(expected.GetProperty("reason").GetString(), decision.Reason);
        }

        foreach (var item in root.GetProperty("parse_disabled_vendors").EnumerateArray())
        {
            Assert.Equal(Strings(item.GetProperty("expected")), HardwareAcceleration.ParseDisabledVendors(NullableString(item.GetProperty("input"))));
        }

        foreach (var item in root.GetProperty("normalize_strictness").EnumerateArray())
        {
            Assert.Equal(item.GetProperty("expected").GetString(), HardwareAcceleration.NormalizeStrictness(NullableString(item.GetProperty("input"))));
        }

        foreach (var item in root.GetProperty("normalize_decode_mode").EnumerateArray())
        {
            Assert.Equal(item.GetProperty("expected").GetString(), HardwareAcceleration.NormalizeDecodeMode(NullableString(item.GetProperty("input"))));
        }

        var vendors = root.GetProperty("vendor_methods").EnumerateArray().ToList();
        Assert.Equal(vendors.Count, HardwareAcceleration.VendorMethods.Count);
        for (var i = 0; i < vendors.Count; i++)
        {
            Assert.Equal(vendors[i][0].GetString(), HardwareAcceleration.VendorMethods[i].Key);
            Assert.Equal(Strings(vendors[i][1]), HardwareAcceleration.VendorMethods[i].Value);
        }

        Assert.Equal(Strings(root.GetProperty("strictness_levels")), HardwareAcceleration.StrictnessLevels);
    }

    [Fact]
    public void Hwaccels_output_is_read_as_the_python_layer_reads_it()
    {
        using var document = Load("hardware.json");
        var cases = document.RootElement.GetProperty("detection").EnumerateArray()
            .Where(item => !item.GetProperty("input").TryGetProperty("raise", out _))
            .ToList();
        Assert.NotEmpty(cases);

        foreach (var item in cases)
        {
            var input = item.GetProperty("input");
            var expected = item.GetProperty("expected");
            AssertTokens(Strings(expected.GetProperty("argv")), FfmpegCommands.BuildHwaccelsArgv("ffmpeg"), "hwaccels argv");

            var report = HardwareAcceleration.ReportFromHwaccels(input.GetProperty("returncode").GetInt32(), input.GetProperty("stdout").GetString());

            AssertReport(expected.GetProperty("report"), report, item.GetProperty("name").GetString()!);
        }
    }

    [Fact]
    public void Remux_output_validation_matches_the_python_layer()
    {
        using var document = Load("validation.json");
        var root = document.RootElement;
        foreach (var item in root.GetProperty("remux_output").EnumerateArray())
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            using var probe = JsonDocument.Parse(input.GetProperty("probe").GetString()!);
            var durationText = input.GetProperty("expected_duration_seconds");
            double? expectedDuration = durationText.ValueKind == JsonValueKind.Null ? null : Py.TryFloatFromText(durationText.GetString()!);

            var outcome = Outcome(() => ProbeOutput.ValidateRemuxOutput(probe.RootElement, input.GetProperty("expected_audio").GetInt32(), expectedDuration));

            AssertOutcome(item.GetProperty("expected"), outcome, name);
        }

        foreach (var item in root.GetProperty("durations").EnumerateArray())
        {
            using var data = JsonDocument.Parse(item.GetProperty("input").GetString()!);
            var expected = item.GetProperty("expected");
            var result = expected.GetProperty("result");
            var actual = ProbeOutput.DurationSeconds(data.RootElement);
            Assert.Equal(result.ValueKind == JsonValueKind.Null ? null : result.GetString(), actual is null ? null : PyConvert.FloatRepr(actual.Value));
        }

        foreach (var item in root.GetProperty("integrity").EnumerateArray())
        {
            var input = item.GetProperty("input");
            var outcome = Outcome(() =>
            {
                if (input.GetProperty("returncode").GetInt32() != 0)
                {
                    throw ProbeOutput.IntegrityFailure(input.GetProperty("stderr").GetString());
                }
            });
            AssertOutcome(item.GetProperty("expected"), outcome, input.GetRawText());
        }
    }

    [Fact]
    public void Python_text_handling_is_reproduced()
    {
        using var document = Load("text.json");
        var root = document.RootElement;
        foreach (var item in root.GetProperty("decode").EnumerateArray())
        {
            var bytes = Convert.FromHexString(item.GetProperty("input").GetString()!);
            var expected = item.GetProperty("expected");
            var label = item.GetProperty("input").GetString()!;
            Assert.True(expected.GetProperty("captured").GetString() == ProbeOutput.CapturedText(bytes), "captured " + label);
            Assert.True(expected.GetProperty("tail").GetString() == ProbeOutput.TailText(bytes), "tail " + label);
            Assert.True(expected.GetProperty("tail_4").GetString() == ProbeOutput.TailText(bytes, 4), "tail_4 " + label);
            Assert.True(expected.GetProperty("tail_1").GetString() == ProbeOutput.TailText(bytes, 1), "tail_1 " + label);

            var expectedLines = Strings(expected.GetProperty("lines"));
            for (var chunk = 1; chunk <= Math.Max(1, bytes.Length); chunk++)
            {
                var lines = new List<string>();
                var splitter = new UniversalNewlineSplitter(lines.Add);
                for (var offset = 0; offset < bytes.Length; offset += chunk)
                {
                    splitter.Feed(bytes.AsSpan(offset, Math.Min(chunk, bytes.Length - offset)));
                }

                splitter.Finish();
                Assert.True(expectedLines.SequenceEqual(lines), $"lines {label} in chunks of {chunk}");
            }
        }

        foreach (var item in root.GetProperty("format_1f").EnumerateArray())
        {
            var value = Py.TryFloatFromText(item.GetProperty("input").GetString()!)!.Value;
            Assert.Equal(item.GetProperty("expected").GetString(), PyText.FormatFixed(value, 1));
        }

        foreach (var item in root.GetProperty("splitlines").EnumerateArray())
        {
            Assert.Equal(Strings(item.GetProperty("expected")), PyText.SplitLines(item.GetProperty("input").GetString()!));
        }

        foreach (var item in root.GetProperty("clip").EnumerateArray())
        {
            var input = item.GetProperty("input");
            Assert.Equal(item.GetProperty("expected").GetString(), PyText.Clip(input[0].GetString()!, input[1].GetInt32()));
        }

        foreach (var item in root.GetProperty("timeout_messages").EnumerateArray())
        {
            var input = item.GetProperty("input");
            var argv = Strings(input.GetProperty("argv"));
            var timeoutText = input.GetProperty("timeout").GetString()!;
            var message = timeoutText.Contains('.', StringComparison.Ordinal)
                ? ProbeOutput.TimeoutMessage(argv, double.Parse(timeoutText, System.Globalization.CultureInfo.InvariantCulture))
                : ProbeOutput.TimeoutMessage(argv, int.Parse(timeoutText, System.Globalization.CultureInfo.InvariantCulture));
            Assert.Equal(item.GetProperty("expected").GetString(), message);
        }
    }

    // --- helpers ---------------------------------------------------------------------------

    internal static RemuxPlan ReadPlan(JsonElement plan) => new()
    {
        VideoIndices = plan.GetProperty("video_indices").EnumerateArray().Select(e => e.GetInt32()).ToList(),
        Audio = plan.GetProperty("audio").EnumerateArray().Select(ReadTrack).ToList(),
        Subtitles = plan.GetProperty("subtitles").EnumerateArray().Select(ReadTrack).ToList(),
        RemovedAudio = Strings(plan.GetProperty("removed_audio")),
        RemovedSubtitles = Strings(plan.GetProperty("removed_subtitles")),
        DefaultAudioOutputIndex = plan.GetProperty("default_audio_output_index").GetInt32(),
        AudioSelectionNotes = Strings(plan.GetProperty("audio_selection_notes")),
        RemovedImages = Strings(plan.GetProperty("removed_images")),
        RemovedAttachments = Strings(plan.GetProperty("removed_attachments")),
        MetadataNotes = Strings(plan.GetProperty("metadata_notes")),
        Metadata = new MetadataRules
        {
            RemoveImages = plan.GetProperty("metadata").GetProperty("remove_images").GetBoolean(),
            RemoveAttachments = plan.GetProperty("metadata").GetProperty("remove_attachments").GetBoolean(),
            RemoveTitle = plan.GetProperty("metadata").GetProperty("remove_title").GetBoolean(),
            RemoveLanguageTags = plan.GetProperty("metadata").GetProperty("remove_language_tags").GetBoolean(),
            RemoveOtherMetadata = plan.GetProperty("metadata").GetProperty("remove_other_metadata").GetBoolean(),
        },
    };

    private static PlannedTrack ReadTrack(JsonElement track) => new()
    {
        InputIndex = track.GetProperty("input_index").GetInt32(),
        LangLabel = track.GetProperty("lang_label").GetString()!,
        Commentary = track.GetProperty("commentary").GetBoolean(),
        Forced = track.GetProperty("forced").GetBoolean(),
        Default = track.GetProperty("default").GetBoolean(),
        Channels = track.GetProperty("channels").GetInt32(),
        Lossless = track.GetProperty("lossless").GetBoolean(),
        Bitrate = track.GetProperty("bitrate").GetInt64(),
        CodecRank = track.GetProperty("codec_rank").GetInt32(),
        CodecName = track.GetProperty("codec_name").GetString()!,
        Kind = track.GetProperty("kind").GetString() == "subtitle" ? TrackKind.Subtitle : TrackKind.Audio,
    };

    private static void AssertReport(JsonElement expected, AccelerationReport report, string label)
    {
        Assert.True(Strings(expected.GetProperty("available_methods")).SequenceEqual(report.AvailableMethods), label);
        Assert.True(expected.GetProperty("detected").GetBoolean() == report.Detected, label);
        Assert.Equal(expected.GetProperty("detail").GetString(), report.Detail);
        Assert.True(Strings(expected.GetProperty("vendors")).SequenceEqual(report.Vendors), label);
    }

    private static Exception? Outcome(Action action)
    {
        try
        {
            action();
            return null;
        }
        catch (Exception error) when (error is MediaToolException or RulesInputException)
        {
            return error;
        }
    }

    private static void AssertOutcome(JsonElement expected, Exception? actual, string label)
    {
        if (expected.TryGetProperty("ok", out _))
        {
            Assert.True(actual is null, $"{label}: expected success, got {actual}");
            return;
        }

        var error = expected.GetProperty("error");
        Assert.True(actual is not null, $"{label}: expected {error.GetRawText()}, got success");
        Assert.True(error.GetProperty("type").GetString() == PythonType(actual), $"{label}: expected {error.GetRawText()}, got {PythonType(actual)}: {actual.Message}");
        if (actual is MediaToolException)
        {
            Assert.Equal(error.GetProperty("message").GetString(), actual.Message);
        }
    }

    private static string PythonType(Exception error) => error switch
    {
        MediaUnreadableException => "MediaUnreadableError",
        MediaCompletenessException => "MediaCompletenessError",
        MediaToolException => "RuntimeError",
        RulesInputException rules => rules.PythonError,
        _ => error.GetType().Name,
    };

    private static void AssertTokens(IReadOnlyList<string> expected, IReadOnlyList<string> actual, string label)
    {
        if (!expected.SequenceEqual(actual))
        {
            Assert.Fail($"{label}:\n expected {PyText.ListRepr(expected)}\n actual   {PyText.ListRepr(actual)}");
        }
    }

    private static List<string> Strings(JsonElement array) => array.EnumerateArray().Select(e => e.GetString()!).ToList();

    private static string? NullableString(JsonElement value) => value.ValueKind == JsonValueKind.Null ? null : value.GetString();

    private static JsonDocument Load(string fileName) => JsonDocument.Parse(File.ReadAllText(Path.Combine(GoldenDirectory, fileName)));
}

/// <summary>
/// Deliberate divergences from the golden fixtures in <c>tests/Weir.Core.Tests/Media/golden</c>: fixing a bug on
/// purpose makes the .NET port behave differently from the Python code the fixtures were captured from.
/// Regenerating the fixtures with <c>scripts/generate-ffmpeg-golden.py</c> would erase that difference (Python
/// was not changed), so each entry here patches the loaded expectation instead, named for the GitHub issue that
/// required it, keeping every other case in the file an unmodified proof of parity. See apps/server/README.md,
/// "ffmpeg parity", for the mechanism.
/// </summary>
internal static class GoldenDivergences
{
    /// <summary>
    /// #539 item 1: ffprobe now runs with "-v error" (the golden fixture has Python's "-v quiet") so that
    /// unreadable-media markers reach stderr instead of being suppressed. #498: ffprobe also now runs with
    /// "-show_chapters" (absent from the fixture, captured before that option existed) so a probe's JSON always
    /// carries a chapters array for <see cref="Weir.Core.Rules.ProbeResult.Chapters"/>.
    /// </summary>
    public static IReadOnlyList<string> FfprobeArgv(IReadOnlyList<string> golden)
    {
        var patched = golden.ToList();
        var index = patched.IndexOf("-v");
        if (index >= 0 && index + 1 < patched.Count && patched[index + 1] == "quiet")
        {
            patched[index + 1] = "error";
        }

        var showFormatIndex = patched.IndexOf("-show_format");
        if (showFormatIndex >= 0)
        {
            patched.Insert(showFormatIndex + 1, "-show_chapters");
        }

        return patched;
    }

    private static readonly HashSet<string> AttachmentIncapableExtensions = new(StringComparer.OrdinalIgnoreCase) { ".mp4", ".m4v", ".mov" };

    private static readonly string[] StaleStatisticsTagKeys =
    [
        "DURATION", "NUMBER_OF_FRAMES", "NUMBER_OF_BYTES", "BPS",
        "_STATISTICS_WRITING_APP", "_STATISTICS_WRITING_DATE_UTC", "_STATISTICS_TAGS", "ENCODER",
    ];

    /// <summary>
    /// #547 fixes three bugs in <see cref="Weir.Core.Media.FfmpegCommands.BuildRemuxArgv"/> that change nearly
    /// every remux argv fixture with an audio or subtitle track (which is nearly all of them): item 1 adds an
    /// attachment map (<c>-map 0:t?</c>) unless attachments are being removed or the output container cannot
    /// carry one (mirroring the production extension check); item 2 changes each disposition token from a flat
    /// overwrite (<c>default</c>/<c>0</c>/<c>forced</c>/<c>default+forced</c>) to the additive form
    /// (<c>+default</c>/<c>-default</c> combined with <c>+forced</c>/<c>-forced</c>) that preserves whatever else
    /// ffmpeg copied through from the source stream's own disposition instead of discarding it; item 3 adds a
    /// fixed clear of stale per-track statistics tags on every kept video/audio/subtitle stream. None of the
    /// fixtures these cases were captured from ever set #498's StandardizeTrackNames/ClearVideoTrackNames
    /// (<see cref="MediaGoldenParityTests.ReadPlan"/> does not even read those two fields), so the new tags always
    /// land right before the output path, at the very end — see apps/server/README.md, "ffmpeg parity".
    /// </summary>
    public static IReadOnlyList<string> RemuxArgv(IReadOnlyList<string> golden, JsonElement input)
    {
        var argv = golden.ToList();
        var plan = input.GetProperty("plan");
        var metadata = plan.GetProperty("metadata");
        var dst = input.GetProperty("dst").GetString()!;
        var videoCount = plan.GetProperty("video_indices").GetArrayLength();
        var audioCount = plan.GetProperty("audio").GetArrayLength();
        var subtitleCount = plan.GetProperty("subtitles").GetArrayLength();
        var rules = new MetadataRules
        {
            RemoveImages = metadata.GetProperty("remove_images").GetBoolean(),
            RemoveAttachments = metadata.GetProperty("remove_attachments").GetBoolean(),
            RemoveTitle = metadata.GetProperty("remove_title").GetBoolean(),
            RemoveLanguageTags = metadata.GetProperty("remove_language_tags").GetBoolean(),
            RemoveOtherMetadata = metadata.GetProperty("remove_other_metadata").GetBoolean(),
        };

        var mapsAttachments = !rules.RemoveAttachments && SupportsAttachmentOutput(dst);
        if (mapsAttachments)
        {
            argv.InsertRange(argv.IndexOf("-c"), ["-map", "0:t?"]);
        }

        if (mapsAttachments && rules.RemoveOtherMetadata)
        {
            // The restore lands after the *whole* MetadataStreams.ArgvFlags(rules) block (which, when both
            // RemoveOtherMetadata and RemoveTitle are set, also carries a "-metadata title=" pair after
            // "-map_metadata -1" — see MetadataStreams.ArgvFlags), not right after "-map_metadata -1" itself;
            // reusing the real production flags list here keeps this in step with that block's actual length.
            var insertAt = argv.IndexOf("-c") + 2 + MetadataStreams.ArgvFlags(rules).Count;
            argv.InsertRange(insertAt, ["-map_metadata:s:t", "0:s:t"]);
        }

        for (var i = 0; i < argv.Count - 1; i++)
        {
            if (argv[i].StartsWith("-disposition:a:", StringComparison.Ordinal))
            {
                argv[i + 1] = argv[i + 1] == "default" ? "+default" : "-default";
            }
            else if (argv[i].StartsWith("-disposition:s:", StringComparison.Ordinal))
            {
                var (hasDefault, hasForced) = argv[i + 1] switch
                {
                    "default+forced" => (true, true),
                    "default" => (true, false),
                    "forced" => (false, true),
                    _ => (false, false),
                };
                argv[i + 1] = (hasDefault ? "+default" : "-default") + (hasForced ? "+forced" : "-forced");
            }
        }

        var statsTokens = new List<string>();
        AppendStatsClearTokens(statsTokens, 'v', videoCount);
        AppendStatsClearTokens(statsTokens, 'a', audioCount);
        AppendStatsClearTokens(statsTokens, 's', subtitleCount);
        argv.InsertRange(argv.Count - 1, statsTokens);

        return argv;
    }

    private static bool SupportsAttachmentOutput(string dst)
    {
        var lastDot = dst.LastIndexOf('.');
        var lastSeparator = Math.Max(dst.LastIndexOf('/'), dst.LastIndexOf('\\'));
        return lastDot <= lastSeparator || !AttachmentIncapableExtensions.Contains(dst[lastDot..]);
    }

    private static void AppendStatsClearTokens(List<string> tokens, char streamType, int count)
    {
        for (var i = 0; i < count; i++)
        {
            var specifier = $"-metadata:s:{streamType}:{i.ToString(CultureInfo.InvariantCulture)}";
            foreach (var key in StaleStatisticsTagKeys)
            {
                tokens.Add(specifier);
                tokens.Add($"{key}=");
            }
        }
    }
}
