using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Tests.Media;

namespace Weir.Infrastructure.Tests.Refiner.RemuxPass;

/// <summary>
/// The whole pass against real ffprobe and ffmpeg (<c>WEIR_FFMPEG_DIR</c> or PATH) on tiny generated files: a remux that drops a
/// language, a file already in shape, and the damaged inputs of #494 and #539.
/// </summary>
public sealed class RemuxPassRealFfmpegTests : IDisposable
{
    private readonly PassFolders _folders = new();
    private readonly RecordingFacts _facts = new();

    public void Dispose() => _folders.Dispose();

    private sealed class RealResolver : IMediaToolResolver
    {
        public (string Ffprobe, string Ffmpeg) Resolve() => RealFfmpeg.Tools!.Value;

        public string? ResolveMkvmerge() => RealMkvmerge.Tool;
    }

    private RemuxPassRunner Runner() =>
        new(
            new MediaTools(new ProcessRunner(), new RealResolver(), new ListLogger<MediaTools>(), TimeProvider.System),
            new RealResolver(),
            _facts,
            new FakeCleanupData(),
            new SkippedTvSeasonFolderCleanup(),
            new FakeOriginalLanguage(),
            new RemuxPassSettings { WatchedFolderMinFileAgeSeconds = 0 },
            TimeProvider.System,
            NullLogger<RemuxPassRunner>.Instance);

    private async Task<string> GenerateAsync(string relative, params string[] languages)
    {
        var path = Path.Join(_folders.Watched, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var argv = new List<string>
        {
            RealFfmpeg.Tools!.Value.Ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10",
        };
        foreach (var (_, i) in languages.Select((language, i) => (language, i)))
        {
            argv.AddRange(["-f", "lavfi", "-i", $"sine=frequency={440 * (i + 1)}:duration=3"]);
        }

        argv.AddRange(["-map", "0"]);
        for (var i = 0; i < languages.Length; i++)
        {
            argv.AddRange(["-map", (i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture)]);
        }

        argv.AddRange(["-c:v", "mpeg4", "-c:a", "aac"]);
        for (var i = 0; i < languages.Length; i++)
        {
            argv.AddRange([$"-metadata:s:a:{i}", $"language={languages[i]}", $"-disposition:a:{i}", i == 0 ? "default" : "0"]);
        }

        argv.Add(path);
        var result = await new ProcessRunner().RunAsync(new ProcessRequest { Argv = argv, Timeout = TimeSpan.FromMinutes(1) });
        Assert.True(result.ExitCode == 0, "fixture generation failed: " + ProbeOutput.TailText(result.Stderr));
        return path;
    }

    private Task<PyDict> Run(string relative) =>
        Runner().RunAsync(new RemuxPassRequest { Runtime = _folders.Runtime(), RelativeMediaPath = relative, RulesConfig = RemuxRules.DefaultConfig(), MinFileAgeSeconds = 0 });

    private static string Str(PyDict result, string key) => PyConvert.Str(result[key]);

    [RequiresFfmpegFact]
    public async Task A_handed_over_film_is_remuxed_without_the_unwanted_language_and_its_release_folder_removed()
    {
        var source = await GenerateAsync(Path.Join("Film.2001", "film.mkv"), "eng", "fre");

        var result = await Run("Film.2001/film.mkv");

        Assert.Equal(RemuxPassOutcomes.LiveOutputWritten, Str(result, "outcome"));
        var output = _folders.Out(Path.Join("Film.2001", "film.mkv"));
        Assert.Equal(Path.GetFullPath(output), Str(result, "output_file"));
        var probe = await new MediaTools(new ProcessRunner(), new RealResolver(), new ListLogger<MediaTools>(), TimeProvider.System).FfprobeJsonAsync(output);
        var audio = probe.GetProperty("streams").EnumerateArray().Where(s => s.GetProperty("codec_type").GetString() == "audio").ToList();
        Assert.Equal("eng", Assert.Single(audio).GetProperty("tags").GetProperty("language").GetString());
        Assert.False(File.Exists(source));
        Assert.False(Directory.Exists(Path.Join(_folders.Watched, "Film.2001")));
        Assert.Empty(Directory.EnumerateFiles(_folders.Work));
        Assert.Equal(2, Assert.Single(_facts.Measured).AudioTrackCount);
        Assert.Equal(JsonValueKind.Object, probe.ValueKind);
    }

    [RequiresFfmpegFact]
    public async Task A_film_already_in_shape_is_validated_and_placed_unchanged()
    {
        var source = await GenerateAsync(Path.Join("Ready", "film.mkv"), "eng");
        var bytes = await File.ReadAllBytesAsync(source);

        var result = await Run("Ready/film.mkv");

        Assert.Equal(RemuxPassOutcomes.LiveSkippedNotRequired, Str(result, "outcome"));
        Assert.Equal(bytes, await File.ReadAllBytesAsync(_folders.Out(Path.Join("Ready", "film.mkv"))));
    }

    [RequiresFfmpegFact]
    public async Task A_zero_filled_mkv_is_unreadable_content_not_a_completed_copy()
    {
        var path = Path.Join(_folders.Watched, "The.Terror.1963", "The.Terror.1963.mkv");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        await File.WriteAllBytesAsync(path, new byte[1024 * 1024]);

        var result = await Run("The.Terror.1963/The.Terror.1963.mkv");

        Assert.Equal(RemuxPassOutcomes.FailedBeforeExecution, Str(result, "outcome"));
        Assert.Equal(PyBool.True, result["content_unusable"]);
        Assert.False(File.Exists(_folders.Out(Path.Join("The.Terror.1963", "The.Terror.1963.mkv"))));
        Assert.True(File.Exists(path));
    }

    [RequiresFfmpegFact]
    public async Task A_truncated_mkv_never_completes_as_if_it_were_whole()
    {
        var whole = await GenerateAsync(Path.Join("Cut", "whole.mkv"), "eng");
        var bytes = await File.ReadAllBytesAsync(whole);
        File.Delete(whole);
        var truncated = Path.Join(_folders.Watched, "Cut", "film.mkv");
        await File.WriteAllBytesAsync(truncated, bytes[..(bytes.Length / 2)]);

        var result = await Run("Cut/film.mkv");

        Assert.NotEqual(RemuxPassOutcomes.LiveOutputWritten, Str(result, "outcome"));
        Assert.NotEqual(RemuxPassOutcomes.LiveSkippedNotRequired, Str(result, "outcome"));
        Assert.False(File.Exists(_folders.Out(Path.Join("Cut", "film.mkv"))));
        Assert.True(File.Exists(truncated));
    }
}
