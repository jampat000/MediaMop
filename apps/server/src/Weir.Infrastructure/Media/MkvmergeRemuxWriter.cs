using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

namespace Weir.Infrastructure.Media;

/// <summary>Today's writer: ffmpeg writes every container (<see cref="FfmpegCommands.BuildRemuxArgv"/>).</summary>
public sealed class FfmpegRemuxWriter(MediaTools tools) : IRemuxWriter
{
    public string Name => "ffmpeg";

    /// <summary>ffmpeg writes every container Weir supports, so this is always true.</summary>
    public bool CanWrite(string destination) => true;

    public Task WriteAsync(RemuxWriteRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        return tools.WriteWithFfmpegAsync(request, cancellationToken);
    }
}

/// <summary>
/// #548: mkvmerge writes Matroska. ffmpeg keeps probing, validating and every other container.
/// <para>
/// The plan addresses streams by ffprobe index and mkvmerge addresses its own track ids, so every write first
/// identifies the source with <c>mkvmerge -J</c> and lines the two numberings up
/// (<see cref="MkvmergeCommands.MapStreamIndicesToTrackIds"/>). When they cannot be lined up — the check is
/// deliberately strict — this throws <see cref="MkvmergeTrackMappingException"/> rather than write a file with
/// the wrong tracks kept, and <see cref="RemuxWriterSelector"/> falls back to ffmpeg.
/// </para>
/// <para>
/// Hardware acceleration has no counterpart here: it only ever affected ffmpeg's decode path, and a remux is a
/// stream copy, so a plan carrying an <see cref="AccelerationDecision"/> is written identically either way.
/// </para>
/// </summary>
public sealed class MkvmergeRemuxWriter(MediaTools tools, IMediaToolResolver resolver) : IRemuxWriter
{
    public string Name => "mkvmerge";

    /// <summary>Matroska only, and only when mkvmerge is actually installed.</summary>
    public bool CanWrite(string destination)
    {
        ArgumentNullException.ThrowIfNull(destination);
        return MkvmergeCommands.SupportsDestination(destination) && resolver.ResolveMkvmerge() is not null;
    }

    public async Task WriteAsync(RemuxWriteRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        var mkvmerge = resolver.ResolveMkvmerge()
            ?? throw new MediaToolException("mkvmerge was not found, so it cannot write this file.");
        var identification = await tools.IdentifyMkvmergeAsync(mkvmerge, request.Source, cancellationToken).ConfigureAwait(false);
        var trackIds = MkvmergeCommands.MapStreamIndicesToTrackIds(SourceStreams(request.SourceProbe), identification);
        RefuseKeptCoverArt(request.Plan, trackIds);
        var argv = MkvmergeCommands.BuildRemuxArgv(
            mkvmerge,
            request.Source,
            request.Destination,
            request.Plan,
            trackIds,
            identification.Attachments);
        await tools.RunMkvmergeAsync(argv, request.ProgressCallback, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Hands back to ffmpeg when the plan <i>keeps</i> embedded cover art, which is the default
    /// (<see cref="MetadataRules.RemoveImages"/> is off unless the rules turn it on).
    /// <para>
    /// The two writers genuinely disagree about what kept cover art is. ffmpeg maps it as an output video
    /// stream, so it lands in <see cref="RemuxPlan.VideoIndices"/> order, second after the real video. mkvmerge
    /// writes it as the Matroska attachment it actually is, which ffprobe then reports <i>after</i> every real
    /// stream. #500's <see cref="RemuxOutputValidation"/> checks output positions against the plan and is
    /// deliberately not changed by #548, so it reads mkvmerge's (correct) output as "planned position 1 to be
    /// video, output has audio".
    /// </para>
    /// <para>
    /// Rather than weaken the validation that guards the shipping ffmpeg path, mkvmerge declines these files
    /// and ffmpeg writes them exactly as it does today. Deciding whether validation should treat cover art as
    /// non-positional — which would let mkvmerge take these too — is its own change, on its own evidence.
    /// </para>
    /// </summary>
    private static void RefuseKeptCoverArt(RemuxPlan plan, IReadOnlyDictionary<int, int> trackIds)
    {
        var kept = plan.VideoIndices.Where(index => !trackIds.ContainsKey(index)).ToList();
        if (kept.Count > 0)
        {
            throw new MkvmergeUnsupportedPlanException(
                "the rules keep this file's embedded cover art, which mkvmerge stores as an attachment rather "
                + "than a video track, so ffmpeg is writing it instead.");
        }
    }

    /// <summary>The source's ffprobe streams, in the order ffprobe listed them.</summary>
    private static IReadOnlyList<ProbeStreamInfo> SourceStreams(JsonElement probe)
    {
        if (probe.ValueKind != JsonValueKind.Object
            || probe.TryGetProperty("streams", out var streams) is false
            || streams.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return [.. streams.EnumerateArray()
            .Where(stream => stream.ValueKind == JsonValueKind.Object)
            .Select(stream => new ProbeStreamInfo(stream))];
    }
}

/// <summary>
/// Picks the writer for one output, honouring the library's <see cref="RemuxWriterChoice"/> and falling back
/// to ffmpeg whenever mkvmerge cannot take the job — a non-Matroska container, or mkvmerge not installed.
/// </summary>
public sealed class RemuxWriterSelector(FfmpegRemuxWriter ffmpeg, MkvmergeRemuxWriter mkvmerge)
{
    /// <summary>
    /// The writer for <paramref name="destination"/> under <paramref name="choice"/>. Choosing the best tool
    /// never means failing a file the best tool cannot write: ffmpeg takes those, here and again at write
    /// time if mkvmerge declines one it thought it could take.
    /// </summary>
    public IRemuxWriter Select(string destination, string? choice)
    {
        ArgumentNullException.ThrowIfNull(destination);
        if (!RemuxWriterChoice.PrefersBestTool(choice))
        {
            return ffmpeg;
        }

        return mkvmerge.CanWrite(destination) ? mkvmerge : ffmpeg;
    }
}
