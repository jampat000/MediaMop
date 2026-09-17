// Issue #503 trial harness. For every *.mkv in a corpus directory:
//   1. ffprobe the source.
//   2. Build a representative RemuxPlan (drop one audio track, keep all subtitles, set
//      default/forced flags from the source disposition) and run it through
//      Weir.Core.Media.FfmpegCommands.BuildRemuxArgv exactly as the real remux pass would.
//   3. Build the equivalent mkvmerge command line for the same kept tracks, order and flags.
//   4. Run both, ffprobe + mkvinfo both outputs, run a decode-error check on both, and record
//      track count/order/flags/attachments/chapters, file size and wall time.
//
// Output: a Markdown table fragment and one JSON file per source under <outDir>/results/.
// Not part of Weir.slnx; not built or run by CI. See docs/trials/503-mkvmerge-vs-ffmpeg.md.
using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

if (args.Length < 6)
{
    Console.Error.WriteLine("usage: Trial503Harness <corpusDir> <outDir> <ffmpegExe> <ffprobeExe> <mkvmergeExe> <mkvinfoExe>");
    return 2;
}

var corpusDir = args[0];
var outDir = args[1];
var ffmpegExe = args[2];
var ffprobeExe = args[3];
var mkvmergeExe = args[4];
var mkvinfoExe = args[5];

var ffmpegOutDir = Path.Combine(outDir, "ffmpeg");
var mkvmergeOutDir = Path.Combine(outDir, "mkvmerge");
var resultsDir = Path.Combine(outDir, "results");
Directory.CreateDirectory(ffmpegOutDir);
Directory.CreateDirectory(mkvmergeOutDir);
Directory.CreateDirectory(resultsDir);

var sources = Directory.GetFiles(corpusDir, "*.mkv").OrderBy(p => p, StringComparer.Ordinal).ToList();
Console.WriteLine($"Found {sources.Count} corpus files in {corpusDir}");

var mdRows = new List<string>();
mdRows.Add("| File | ffmpeg ms | mkvmerge ms | ffmpeg bytes | mkvmerge bytes | tracks match | flags match | attachments | chapters | ffmpeg decode errors | mkvmerge decode errors | notes |");
mdRows.Add("|---|---|---|---|---|---|---|---|---|---|---|---|");

foreach (var src in sources)
{
    var name = Path.GetFileNameWithoutExtension(src);
    Console.WriteLine($"=== {name} ===");
    try
    {
        var result = await ProcessOneAsync(src, name);
        mdRows.Add(result.MarkdownRow);
        await File.WriteAllTextAsync(Path.Combine(resultsDir, name + ".json"), result.Json);
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"FAILED: {name}: {ex}");
        mdRows.Add($"| {name} | ERROR | | | | | | | | | | {Escape(ex.Message)} |");
    }
}

await File.WriteAllTextAsync(Path.Combine(outDir, "summary.md"), string.Join('\n', mdRows) + "\n");
Console.WriteLine("Wrote " + Path.Combine(outDir, "summary.md"));
return 0;

static string Escape(string s) => s.Replace("|", "\\|", StringComparison.Ordinal).Replace("\n", " ", StringComparison.Ordinal);

async Task<(string MarkdownRow, string Json)> ProcessOneAsync(string src, string name)
{
    var probe = await FfprobeJsonAsync(ffprobeExe, src);
    var streams = probe.RootElement.GetProperty("streams").EnumerateArray().Select(ParseStream).ToList();

    var videoReal = streams.Where(s => s.CodecType == "video" && !s.AttachedPic).ToList();
    var audio = streams.Where(s => s.CodecType == "audio").OrderBy(s => s.Index).ToList();
    var subs = streams.Where(s => s.CodecType == "subtitle").OrderBy(s => s.Index).ToList();

    // Representative plan: drop a commentary-flagged audio track if there is one and more than
    // one audio track exists, else drop the last audio track if there is more than one. Keep every
    // subtitle. Default = the source's own default track if it kept one, else the first kept track
    // of that kind. Forced is preserved from the source disposition.
    var droppedAudio = audio.Count > 1 ? (audio.FirstOrDefault(a => a.Comment) ?? audio[^1]) : null;
    var keptAudio = audio.Where(a => a != droppedAudio).ToList();
    var keptSubs = subs;

    var defaultAudio = keptAudio.FirstOrDefault(a => a.Default) ?? keptAudio.FirstOrDefault();
    var plannedAudio = keptAudio.Select(a => new PlannedTrack
    {
        InputIndex = a.Index,
        LangLabel = a.Language ?? "und",
        Commentary = a.Comment,
        Forced = false,
        Default = a == defaultAudio,
        Channels = a.Channels,
        CodecName = a.CodecName ?? string.Empty,
        Kind = TrackKind.Audio,
    }).ToList();

    var defaultSub = keptSubs.FirstOrDefault(s => s.Default);
    var plannedSubs = keptSubs.Select(s => new PlannedTrack
    {
        InputIndex = s.Index,
        LangLabel = s.Language ?? "und",
        Forced = s.Forced,
        Default = s == defaultSub,
        CodecName = s.CodecName ?? string.Empty,
        Kind = TrackKind.Subtitle,
    }).ToList();

    var plan = new RemuxPlan
    {
        VideoIndices = videoReal.Select(v => v.Index).ToList(),
        Audio = plannedAudio,
        Subtitles = plannedSubs,
    };

    var ffmpegDst = Path.Combine(ffmpegOutDir, name + ".mkv");
    var ffmpegArgv = FfmpegCommands.BuildRemuxArgv(ffmpegExe, src, ffmpegDst, plan);
    var ffmpegRun = await RunAsync(ffmpegArgv, TimeSpan.FromMinutes(5));

    // mkvmerge track ids are 0-based, assigned only to real tracks (video/audio/subtitle), in the
    // order they appear in the file - attachments and images-as-attached-pictures are not counted.
    // ffprobe indexes the same streams (plus attachments) in the same relative order, so the Nth
    // "real" ffprobe stream is mkvmerge track id N-1... i.e. position within the filtered list.
    var mkvIdByProbeIndex = streams
        .Where(s => s.CodecType is "video" or "audio" or "subtitle")
        .OrderBy(s => s.Index)
        .Select((s, mkvId) => (s.Index, MkvId: mkvId))
        .ToDictionary(t => t.Index, t => t.MkvId);

    var mkvVideoIds = videoReal.Select(v => mkvIdByProbeIndex[v.Index]).ToList();
    var mkvAudioIds = keptAudio.Select(a => mkvIdByProbeIndex[a.Index]).ToList();
    var mkvSubIds = keptSubs.Select(s => mkvIdByProbeIndex[s.Index]).ToList();

    var mkvArgs = new List<string> { mkvmergeExe, "-o", Path.Combine(mkvmergeOutDir, name + ".mkv") };

    if (mkvVideoIds.Count > 0)
    {
        mkvArgs.AddRange(["-d", string.Join(',', mkvVideoIds)]);
    }

    if (mkvAudioIds.Count > 0)
    {
        mkvArgs.AddRange(["-a", string.Join(',', mkvAudioIds)]);
    }
    else
    {
        mkvArgs.Add("--no-audio");
    }

    if (mkvSubIds.Count > 0)
    {
        mkvArgs.AddRange(["-s", string.Join(',', mkvSubIds)]);
    }
    else
    {
        mkvArgs.Add("--no-subtitles");
    }

    foreach (var a in plannedAudio)
    {
        var id = mkvIdByProbeIndex[a.InputIndex];
        mkvArgs.AddRange(["--default-track-flag", $"{id.ToString(CultureInfo.InvariantCulture)}:{(a.Default ? "yes" : "no")}"]);
    }

    foreach (var s in plannedSubs)
    {
        var id = mkvIdByProbeIndex[s.InputIndex];
        mkvArgs.AddRange(["--default-track-flag", $"{id.ToString(CultureInfo.InvariantCulture)}:{(s.Default ? "yes" : "no")}"]);
        mkvArgs.AddRange(["--forced-display-flag", $"{id.ToString(CultureInfo.InvariantCulture)}:{(s.Forced ? "yes" : "no")}"]);
    }

    var orderIds = mkvVideoIds.Concat(mkvAudioIds).Concat(mkvSubIds).Select(id => $"0:{id.ToString(CultureInfo.InvariantCulture)}");
    mkvArgs.Add(src);
    mkvArgs.AddRange(["--track-order", string.Join(',', orderIds)]);

    var mkvRun = await RunAsync(mkvArgs, TimeSpan.FromMinutes(5));

    var ffmpegOk = ffmpegRun.ExitCode == 0 && File.Exists(ffmpegDst);
    var mkvOk = (mkvRun.ExitCode is 0 or 1) && File.Exists(Path.Combine(mkvmergeOutDir, name + ".mkv"));

    JsonDocument? ffmpegProbe = ffmpegOk ? await FfprobeJsonAsync(ffprobeExe, ffmpegDst) : null;
    JsonDocument? mkvProbe = mkvOk ? await FfprobeJsonAsync(ffprobeExe, Path.Combine(mkvmergeOutDir, name + ".mkv")) : null;

    var ffmpegDecode = ffmpegOk ? await DecodeCheckAsync(ffmpegExe, ffmpegDst) : "n/a (no output)";
    var mkvDecode = mkvOk ? await DecodeCheckAsync(ffmpegExe, Path.Combine(mkvmergeOutDir, name + ".mkv")) : "n/a (no output)";

    var ffmpegMkvinfo = ffmpegOk ? await RunTextAsync([mkvinfoExe, ffmpegDst]) : string.Empty;
    var mkvMkvinfo = mkvOk ? await RunTextAsync([mkvinfoExe, Path.Combine(mkvmergeOutDir, name + ".mkv")]) : string.Empty;

    var ffmpegFacts = ffmpegProbe is null ? null : Summarize(ffmpegProbe);
    var mkvFacts = mkvProbe is null ? null : Summarize(mkvProbe);

    var tracksMatch = ffmpegFacts is not null && mkvFacts is not null
        && ffmpegFacts.Tracks.SequenceEqual(mkvFacts.Tracks, StringComparer.Ordinal);
    var flagsMatch = ffmpegFacts is not null && mkvFacts is not null
        && ffmpegFacts.Dispositions.SequenceEqual(mkvFacts.Dispositions, StringComparer.Ordinal);

    var ffmpegAttachCount = CountAttachmentStreams(ffmpegProbe);
    var mkvAttachCount = CountAttachmentStreams(mkvProbe);
    var sourceAttachCount = streams.Count(s => s.CodecType == "attachment");

    var ffmpegChapterCount = await ChapterCountAsync(ffprobeExe, ffmpegOk ? ffmpegDst : null);
    var mkvChapterCount = await ChapterCountAsync(ffprobeExe, mkvOk ? Path.Combine(mkvmergeOutDir, name + ".mkv") : null);

    var notes = new List<string>();
    if (sourceAttachCount > 0 && ffmpegAttachCount < sourceAttachCount)
    {
        notes.Add($"ffmpeg dropped {sourceAttachCount - ffmpegAttachCount}/{sourceAttachCount} attachment(s) (BuildRemuxArgv never maps codec_type=attachment streams)");
    }

    if (sourceAttachCount > 0 && mkvAttachCount < sourceAttachCount)
    {
        notes.Add($"mkvmerge dropped {sourceAttachCount - mkvAttachCount}/{sourceAttachCount} attachment(s)");
    }

    if (!ffmpegOk)
    {
        notes.Add("ffmpeg failed: " + Truncate(ffmpegRun.Stderr, 300));
    }

    if (!mkvOk)
    {
        notes.Add("mkvmerge failed: " + Truncate(mkvRun.Stderr, 300));
    }

    if (ffmpegOk && !string.IsNullOrWhiteSpace(ffmpegDecode) && ffmpegDecode != "clean")
    {
        notes.Add("ffmpeg output decode: " + Truncate(ffmpegDecode, 200));
    }

    if (mkvOk && !string.IsNullOrWhiteSpace(mkvDecode) && mkvDecode != "clean")
    {
        notes.Add("mkvmerge output decode: " + Truncate(mkvDecode, 200));
    }

    var ffmpegSize = ffmpegOk ? new FileInfo(ffmpegDst).Length : -1;
    var mkvSize = mkvOk ? new FileInfo(Path.Combine(mkvmergeOutDir, name + ".mkv")).Length : -1;

    var row = "| " + name + " | " + ffmpegRun.ElapsedMs + " | " + mkvRun.ElapsedMs + " | " + ffmpegSize + " | " + mkvSize + " | "
        + (tracksMatch ? "yes" : "NO") + " | " + (flagsMatch ? "yes" : "NO") + " | "
        + $"src={sourceAttachCount} ffmpeg={ffmpegAttachCount} mkvmerge={mkvAttachCount}" + " | "
        + $"src? ffmpeg={ffmpegChapterCount} mkvmerge={mkvChapterCount}" + " | "
        + Escape(ffmpegDecode) + " | " + Escape(mkvDecode) + " | " + Escape(string.Join("; ", notes)) + " |";

    var jsonOut = JsonSerializer.Serialize(new
    {
        name,
        source = src,
        ffmpeg = new { argv = ffmpegArgv, exitCode = ffmpegRun.ExitCode, elapsedMs = ffmpegRun.ElapsedMs, size = ffmpegSize, decode = ffmpegDecode, stderr = ffmpegRun.Stderr, mkvinfo = ffmpegMkvinfo },
        mkvmerge = new { argv = mkvArgs, exitCode = mkvRun.ExitCode, elapsedMs = mkvRun.ElapsedMs, size = mkvSize, decode = mkvDecode, stderr = mkvRun.Stderr, mkvinfo = mkvMkvinfo },
        sourceAttachments = sourceAttachCount,
        ffmpegAttachments = ffmpegAttachCount,
        mkvmergeAttachments = mkvAttachCount,
        tracksMatch,
        flagsMatch,
        notes,
    }, new JsonSerializerOptions { WriteIndented = true });

    Console.WriteLine("  ffmpeg: " + (ffmpegOk ? "ok" : "FAILED") + $" ({ffmpegRun.ElapsedMs} ms, {ffmpegSize} bytes)");
    Console.WriteLine("  mkvmerge: " + (mkvOk ? "ok" : "FAILED") + $" ({mkvRun.ElapsedMs} ms, {mkvSize} bytes)");
    if (notes.Count > 0)
    {
        Console.WriteLine("  notes: " + string.Join("; ", notes));
    }

    return (row, jsonOut);
}

static string Truncate(string s, int max) => s.Length <= max ? s : s[..max] + "...";

static int CountAttachmentStreams(JsonDocument? probe)
{
    if (probe is null)
    {
        return 0;
    }

    return probe.RootElement.GetProperty("streams").EnumerateArray().Count(s => s.GetProperty("codec_type").GetString() == "attachment");
}

static async Task<int> ChapterCountAsync(string ffprobeExe, string? path)
{
    if (path is null)
    {
        return -1;
    }

    var psi = new ProcessStartInfo(ffprobeExe)
    {
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    psi.ArgumentList.Add("-v");
    psi.ArgumentList.Add("error");
    psi.ArgumentList.Add("-show_chapters");
    psi.ArgumentList.Add("-print_format");
    psi.ArgumentList.Add("json");
    psi.ArgumentList.Add(path);
    using var proc = Process.Start(psi)!;
    var stdout = await proc.StandardOutput.ReadToEndAsync();
    await proc.StandardError.ReadToEndAsync();
    await proc.WaitForExitAsync();
    using var doc = JsonDocument.Parse(stdout);
    return doc.RootElement.GetProperty("chapters").GetArrayLength();
}

static async Task<string> DecodeCheckAsync(string ffmpegExe, string path)
{
    var psi = new ProcessStartInfo(ffmpegExe)
    {
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    foreach (var a in new[] { "-v", "error", "-i", path, "-f", "null", "-" })
    {
        psi.ArgumentList.Add(a);
    }

    using var proc = Process.Start(psi)!;
    var stderr = await proc.StandardError.ReadToEndAsync();
    await proc.StandardOutput.ReadToEndAsync();
    await proc.WaitForExitAsync();
    return string.IsNullOrWhiteSpace(stderr) ? "clean" : stderr.Trim();
}

static async Task<string> RunTextAsync(IReadOnlyList<string> argv)
{
    var psi = new ProcessStartInfo(argv[0]) { RedirectStandardOutput = true, RedirectStandardError = true };
    foreach (var a in argv.Skip(1))
    {
        psi.ArgumentList.Add(a);
    }

    using var proc = Process.Start(psi)!;
    var stdout = await proc.StandardOutput.ReadToEndAsync();
    await proc.StandardError.ReadToEndAsync();
    await proc.WaitForExitAsync();
    return stdout;
}

static async Task<(int ExitCode, string Stdout, string Stderr, long ElapsedMs)> RunAsync(IReadOnlyList<string> argv, TimeSpan timeout)
{
    var psi = new ProcessStartInfo(argv[0]) { RedirectStandardOutput = true, RedirectStandardError = true };
    foreach (var a in argv.Skip(1))
    {
        psi.ArgumentList.Add(a);
    }

    var sw = Stopwatch.StartNew();
    using var proc = Process.Start(psi)!;
    var stdoutTask = proc.StandardOutput.ReadToEndAsync();
    var stderrTask = proc.StandardError.ReadToEndAsync();
    using var cts = new CancellationTokenSource(timeout);
    await proc.WaitForExitAsync(cts.Token);
    sw.Stop();
    return (proc.ExitCode, await stdoutTask, await stderrTask, sw.ElapsedMilliseconds);
}

static async Task<JsonDocument> FfprobeJsonAsync(string ffprobeExe, string path)
{
    var psi = new ProcessStartInfo(ffprobeExe)
    {
        RedirectStandardOutput = true,
        RedirectStandardError = true,
    };
    foreach (var a in new[] { "-v", "error", "-show_streams", "-show_format", "-print_format", "json", path })
    {
        psi.ArgumentList.Add(a);
    }

    using var proc = Process.Start(psi)!;
    var stdout = await proc.StandardOutput.ReadToEndAsync();
    var stderr = await proc.StandardError.ReadToEndAsync();
    await proc.WaitForExitAsync();
    if (proc.ExitCode != 0)
    {
        throw new InvalidOperationException($"ffprobe failed on {path}: {stderr}");
    }

    return JsonDocument.Parse(stdout);
}

static ProbedStream ParseStream(JsonElement e)
{
    var index = e.GetProperty("index").GetInt32();
    var codecType = e.GetProperty("codec_type").GetString() ?? string.Empty;
    string? codecName = e.TryGetProperty("codec_name", out var cn) ? cn.GetString() : null;
    string? language = null;
    if (e.TryGetProperty("tags", out var tags))
    {
        if (tags.TryGetProperty("language", out var lang))
        {
            language = lang.GetString();
        }
    }

    var disposition = e.TryGetProperty("disposition", out var d) ? d : default;
    bool Flag(string key) => disposition.ValueKind == JsonValueKind.Object && disposition.TryGetProperty(key, out var v) && v.GetInt32() != 0;

    var channels = e.TryGetProperty("channels", out var ch) ? ch.GetInt32() : 0;

    return new ProbedStream(index, codecType, codecName, language, Flag("default"), Flag("forced"), Flag("comment"), Flag("attached_pic"), channels);
}

static Facts Summarize(JsonDocument probe)
{
    var tracks = new List<string>();
    var dispositions = new List<string>();
    foreach (var s in probe.RootElement.GetProperty("streams").EnumerateArray())
    {
        var type = s.GetProperty("codec_type").GetString();
        if (type is not ("video" or "audio" or "subtitle"))
        {
            continue;
        }

        var codec = s.TryGetProperty("codec_name", out var cn) ? cn.GetString() : "?";
        var lang = s.TryGetProperty("tags", out var tags) && tags.TryGetProperty("language", out var l) ? l.GetString() : "und";
        tracks.Add($"{type}:{codec}:{lang}");

        if (s.TryGetProperty("disposition", out var disp))
        {
            var def = disp.TryGetProperty("default", out var dv) && dv.GetInt32() != 0;
            var forced = disp.TryGetProperty("forced", out var fv) && fv.GetInt32() != 0;
            dispositions.Add($"{type}:default={def}:forced={forced}");
        }
    }

    return new Facts(tracks, dispositions);
}

internal sealed record ProbedStream(int Index, string CodecType, string? CodecName, string? Language, bool Default, bool Forced, bool Comment, bool AttachedPic, int Channels);

internal sealed record Facts(List<string> Tracks, List<string> Dispositions);
