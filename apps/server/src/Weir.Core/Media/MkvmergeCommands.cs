using System.Globalization;
using System.Text.Json;
using Weir.Core.Json;
using Weir.Core.Rules;
using Weir.Core.Text;

namespace Weir.Core.Media;

/// <summary>
/// One track as <c>mkvmerge -J</c> reports it: its own id (what every <c>--...-tracks</c> and per-track
/// option addresses) and its type (<c>video</c>, <c>audio</c> or <c>subtitles</c>).
/// </summary>
public sealed record MkvmergeTrack(int Id, string Type);

/// <summary>
/// One attachment as <c>mkvmerge -J</c> reports it. Attachment ids are a separate numbering from track ids.
/// </summary>
/// <param name="Id">Its id, which <c>--attachments</c> addresses.</param>
/// <param name="ContentType">Its MIME type, e.g. <c>image/jpeg</c> for cover art or <c>font/ttf</c> for a font.</param>
/// <param name="FileName">Its file name, e.g. <c>cover.jpg</c>.</param>
public sealed record MkvmergeAttachment(int Id, string ContentType, string FileName)
{
    /// <summary>
    /// True for cover art rather than a font or similar: Matroska stores a poster as an attachment, and it is
    /// what ffprobe surfaces as a video stream flagged <c>attached_pic</c> — so this is the attachment that
    /// <see cref="Weir.Core.Rules.MetadataRules.RemoveImages"/> governs, while every other attachment is
    /// governed by <see cref="Weir.Core.Rules.MetadataRules.RemoveAttachments"/>.
    /// Matched on the MIME type first, then on the names the Matroska cover-art convention reserves
    /// (<c>cover</c>/<c>small_cover</c>, with the landscape and portrait variants).
    /// </summary>
    public bool IsCoverArt =>
        ContentType.StartsWith("image/", StringComparison.OrdinalIgnoreCase)
        || CoverArtNames.Contains(Path.GetFileNameWithoutExtension(FileName));

    private static readonly HashSet<string> CoverArtNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "cover", "small_cover", "cover_land", "small_cover_land",
    };
}

/// <summary>What <c>mkvmerge -J</c> says about a source file.</summary>
/// <param name="Tracks">Its tracks, in the order mkvmerge lists them (ascending id).</param>
/// <param name="Attachments">Its attachments, which are numbered separately from tracks.</param>
/// <param name="ChapterEntries">How many chapter entries the file carries, 0 when it has none.</param>
public sealed record MkvmergeIdentification(
    IReadOnlyList<MkvmergeTrack> Tracks,
    IReadOnlyList<MkvmergeAttachment> Attachments,
    int ChapterEntries);

/// <summary>
/// Raised when a source's mkvmerge tracks cannot be lined up with its ffprobe streams, so no plan built
/// against ffprobe indices can be addressed to mkvmerge safely. See
/// <see cref="MkvmergeCommands.MapStreamIndicesToTrackIds"/>: Weir refuses the write rather than guessing
/// and silently keeping the wrong tracks.
/// </summary>
public sealed class MkvmergeTrackMappingException(string message) : Exception(message);

/// <summary>
/// Raised when mkvmerge could write the file but the result would not be the shape
/// <see cref="RemuxOutputValidation"/> expects, so ffmpeg should write it instead. Not an error: the caller
/// falls back and the file is processed normally.
/// </summary>
public sealed class MkvmergeUnsupportedPlanException(string message) : Exception(message);

/// <summary>
/// The mkvmerge command lines for #548: Matroska writes go through mkvmerge, while ffprobe and ffmpeg keep
/// probing, validating and every non-Matroska container (<see cref="FfmpegCommands"/>).
/// <para>
/// mkvmerge addresses tracks by <b>its own ids</b>, which are not ffprobe's stream indices, and a
/// <see cref="RemuxPlan"/> is built entirely from ffprobe indices. The two numberings diverge exactly where
/// Weir cares: Matroska carries cover art as an <i>attachment</i>, which ffprobe surfaces as an extra video
/// stream (<c>disposition.attached_pic = 1</c>) while mkvmerge does not list it as a track at all — so every
/// track after a cover would shift by one. Measured on a real file (an E-AC-3 episode with two SubRip tracks
/// and a <c>cover</c> attachment): ffprobe reported streams 0 video, 1 audio, 2 and 3 subtitle and 4 mjpeg
/// with <c>attached_pic = 1</c>, while <c>mkvmerge -J</c> reported tracks 0 video, 1 audio, 2 and 3 subtitles
/// plus one attachment named <c>cover</c>. <see cref="MapStreamIndicesToTrackIds"/> therefore lines the two
/// lists up and <i>checks</i> the types agree, rather than assuming index equals id.
/// </para>
/// </summary>
public static class MkvmergeCommands
{
    /// <summary>The wall-clock limit for one mkvmerge run, matching <see cref="FfmpegCommands.FfmpegTimeoutSeconds"/>.</summary>
    public const int MkvmergeTimeoutSeconds = FfmpegCommands.FfmpegTimeoutSeconds;

    /// <summary>The limit for an identification run, which only reads headers.</summary>
    public const int IdentifyTimeoutSeconds = 120;

    /// <summary>How much of mkvmerge's output a failure message keeps.</summary>
    public const int StderrTailBytes = FfmpegCommands.FfmpegStderrTailBytes;

    /// <summary>mkvmerge exit code 1 is "completed with warnings", which is a success for our purposes.</summary>
    public const int ExitCodeWarnings = 1;

    /// <summary>
    /// The containers this writer handles. WebM stays on ffmpeg: it is a constrained Matroska profile and the
    /// #503 trial's corpus was all <c>.mkv</c>, so mkvmerge's attachment and codec allowances were never shown
    /// to carry over (see docs/trials/503-mkvmerge-vs-ffmpeg.md, "Recommendation").
    /// </summary>
    public static IReadOnlySet<string> SupportedExtensions { get; } = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { ".mkv" };

    /// <summary>True when <paramref name="destination"/> is a container this writer is allowed to write.</summary>
    public static bool SupportsDestination(string destination)
    {
        ArgumentNullException.ThrowIfNull(destination);
        var lastDot = destination.LastIndexOf('.');
        var lastSeparator = Math.Max(destination.LastIndexOf('/'), destination.LastIndexOf('\\'));
        return lastDot > lastSeparator && SupportedExtensions.Contains(destination[lastDot..]);
    }

    /// <summary><c>mkvmerge -J &lt;src&gt;</c>: identify the source as JSON, reading headers only.</summary>
    public static IReadOnlyList<string> BuildIdentifyArgv(string mkvmergeBin, string src)
    {
        ArgumentNullException.ThrowIfNull(mkvmergeBin);
        ArgumentNullException.ThrowIfNull(src);
        return [mkvmergeBin, "-J", src];
    }

    /// <summary><c>mkvmerge --version</c>, for the health check and the version on the system page.</summary>
    public static IReadOnlyList<string> BuildVersionArgv(string mkvmergeBin)
    {
        ArgumentNullException.ThrowIfNull(mkvmergeBin);
        return [mkvmergeBin, "--version"];
    }

    /// <summary>Reads what <see cref="BuildIdentifyArgv"/> printed.</summary>
    public static MkvmergeIdentification ParseIdentification(JsonElement json)
    {
        var tracks = new List<MkvmergeTrack>();
        var attachments = new List<MkvmergeAttachment>();
        var chapters = 0;
        if (json.ValueKind != JsonValueKind.Object)
        {
            return new MkvmergeIdentification(tracks, attachments, chapters);
        }

        var trackArray = Py.Get(json, "tracks");
        if (trackArray is { ValueKind: JsonValueKind.Array })
        {
            foreach (var track in trackArray.Value.EnumerateArray())
            {
                if (track.ValueKind == JsonValueKind.Object
                    && Py.TryInt(Py.Get(track, "id"), out var id))
                {
                    tracks.Add(new MkvmergeTrack((int)id, Py.Lower(PyStrings.Strip(Py.StrOr(Py.Get(track, "type"), string.Empty)))));
                }
            }
        }

        var attachmentArray = Py.Get(json, "attachments");
        if (attachmentArray is { ValueKind: JsonValueKind.Array })
        {
            foreach (var attachment in attachmentArray.Value.EnumerateArray())
            {
                if (attachment.ValueKind == JsonValueKind.Object
                    && Py.TryInt(Py.Get(attachment, "id"), out var id))
                {
                    attachments.Add(new MkvmergeAttachment(
                        (int)id,
                        PyStrings.Strip(Py.StrOr(Py.Get(attachment, "content_type"), string.Empty)),
                        PyStrings.Strip(Py.StrOr(Py.Get(attachment, "file_name"), string.Empty))));
                }
            }
        }

        var chapterArray = Py.Get(json, "chapters");
        if (chapterArray is { ValueKind: JsonValueKind.Array })
        {
            foreach (var entry in chapterArray.Value.EnumerateArray())
            {
                if (entry.ValueKind == JsonValueKind.Object && Py.TryInt(Py.Get(entry, "num_entries"), out var count))
                {
                    chapters += (int)count;
                }
            }
        }

        return new MkvmergeIdentification(tracks, attachments, chapters);
    }

    /// <summary>mkvmerge's type word for an ffprobe <c>codec_type</c>.</summary>
    private static string MkvmergeTypeFor(string ffprobeCodecType) => ffprobeCodecType switch
    {
        "video" => "video",
        "audio" => "audio",
        "subtitle" => "subtitles",
        _ => string.Empty,
    };

    /// <summary>
    /// Lines a source's ffprobe streams up with its mkvmerge tracks and returns ffprobe stream index →
    /// mkvmerge track id.
    /// <para>
    /// Only ffprobe streams that mkvmerge also counts as tracks take part: <c>video</c>, <c>audio</c> and
    /// <c>subtitle</c> streams that are not cover art (<c>disposition.attached_pic</c>), because Matroska
    /// stores cover art as an attachment, which mkvmerge numbers separately. ffprobe's own
    /// <c>attachment</c>-typed streams (fonts) are likewise attachments to mkvmerge and take no part.
    /// </para>
    /// <para>
    /// The two lists are then matched in order and their types compared. A disagreement means this file does
    /// not follow the correspondence above, so rather than write a file with the wrong tracks kept, this
    /// throws <see cref="MkvmergeTrackMappingException"/> and the caller falls back to ffmpeg.
    /// </para>
    /// </summary>
    /// <param name="streams">The source's ffprobe streams, in the order ffprobe listed them.</param>
    /// <param name="identification">What <c>mkvmerge -J</c> said about the same file.</param>
    public static IReadOnlyDictionary<int, int> MapStreamIndicesToTrackIds(
        IReadOnlyList<ProbeStreamInfo> streams,
        MkvmergeIdentification identification)
    {
        ArgumentNullException.ThrowIfNull(streams);
        ArgumentNullException.ThrowIfNull(identification);
        var mappable = new List<(int Index, string Type)>();
        foreach (var stream in streams)
        {
            var type = MkvmergeTypeFor(stream.CodecType);
            if (type.Length == 0 || IsMatroskaAttachment(stream) || stream.Index is not { } index)
            {
                continue;
            }

            mappable.Add(((int)index, type));
        }

        if (mappable.Count != identification.Tracks.Count)
        {
            throw new MkvmergeTrackMappingException(
                $"mkvmerge reported {Plural.Of(identification.Tracks.Count, "track")} but ffprobe reported "
                + $"{Plural.Of(mappable.Count, "matching stream")}, so a plan built from ffprobe indices "
                + "cannot be addressed to mkvmerge safely.");
        }

        var map = new Dictionary<int, int>(mappable.Count);
        for (var i = 0; i < mappable.Count; i++)
        {
            var (index, type) = mappable[i];
            var track = identification.Tracks[i];
            if (!string.Equals(track.Type, type, StringComparison.Ordinal))
            {
                throw new MkvmergeTrackMappingException(
                    $"ffprobe stream {index.ToString(CultureInfo.InvariantCulture)} is {type} but the mkvmerge track in the same "
                    + $"position (id {track.Id.ToString(CultureInfo.InvariantCulture)}) is {track.Type}, so the two numberings do not line up.");
            }

            map[index] = track.Id;
        }

        return map;
    }

    /// <summary>
    /// True for a stream Matroska carries as an attachment rather than a track: cover art (which ffprobe
    /// reports as a video stream flagged <c>attached_pic</c>) and ffprobe's own <c>attachment</c> streams.
    /// </summary>
    private static bool IsMatroskaAttachment(ProbeStreamInfo stream)
    {
        if (string.Equals(stream.CodecType, "attachment", StringComparison.Ordinal))
        {
            return true;
        }

        var disposition = stream.Get("disposition");
        if (!Py.IsDict(disposition))
        {
            return false;
        }

        var attachedPic = Py.Get(disposition!.Value, "attached_pic");
        return Py.Truthy(attachedPic) && Py.Int(attachedPic) != 0;
    }

    /// <summary>
    /// The mkvmerge equivalent of <see cref="FfmpegCommands.BuildRemuxArgv"/>: the same
    /// <see cref="RemuxPlan"/>, expressed in mkvmerge's own options.
    /// <para>
    /// Differences from the ffmpeg argv, each deliberate and from the #503 trial:
    /// attachments and disposition flags other than default/forced are kept by mkvmerge's own defaults rather
    /// than by explicit flags; stale per-track statistics tags (<c>DURATION</c>, <c>BPS</c>, the
    /// <c>_STATISTICS_*</c> keys, ffmpeg's <c>ENCODER</c>) are dropped by mkvmerge by default, so the explicit
    /// clears <see cref="FfmpegCommands.BuildRemuxArgv"/> needs have no counterpart here.
    /// </para>
    /// </summary>
    /// <param name="mkvmergeBin">The resolved mkvmerge executable.</param>
    /// <param name="src">The source file.</param>
    /// <param name="dst">The output file. Must be a container in <see cref="SupportedExtensions"/>.</param>
    /// <param name="plan">The same plan the ffmpeg writer would be given.</param>
    /// <param name="trackIds">ffprobe stream index → mkvmerge track id, from <see cref="MapStreamIndicesToTrackIds"/>.</param>
    /// <param name="attachments">The source's attachments, from <see cref="ParseIdentification"/>.</param>
    public static IReadOnlyList<string> BuildRemuxArgv(
        string mkvmergeBin,
        string src,
        string dst,
        RemuxPlan plan,
        IReadOnlyDictionary<int, int> trackIds,
        IReadOnlyList<MkvmergeAttachment> attachments)
    {
        ArgumentNullException.ThrowIfNull(mkvmergeBin);
        ArgumentNullException.ThrowIfNull(src);
        ArgumentNullException.ThrowIfNull(dst);
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(trackIds);
        ArgumentNullException.ThrowIfNull(attachments);

        var video = plan.VideoIndices.Select(index => TrackId(trackIds, index)).ToList();
        var audio = plan.Audio.Select(track => TrackId(trackIds, track.InputIndex)).ToList();
        var subtitles = plan.Subtitles.Select(track => TrackId(trackIds, track.InputIndex)).ToList();

        var args = new List<string>
        {
            mkvmergeBin,
            // Machine-readable progress on stdout, the same role "-progress pipe:1" plays for ffmpeg.
            "--gui-mode",
            "--output",
            dst,
        };

        // Track selection. mkvmerge keeps every track of a type unless told which to keep, and an empty
        // selection is spelled with the "no-" form, so a plan that keeps no subtitles must say so explicitly.
        AddTrackSelection(args, "--video-tracks", "--no-video", video);
        AddTrackSelection(args, "--audio-tracks", "--no-audio", audio);
        AddTrackSelection(args, "--subtitle-tracks", "--no-subtitles", subtitles);

        AddAttachmentSelection(args, plan.Metadata, attachments);

        if (plan.Metadata.RemoveChapters)
        {
            args.Add("--no-chapters");
        }

        // "-map_metadata -1" in the ffmpeg argv: drop the container's own tags and every track's tags.
        if (plan.Metadata.RemoveOtherMetadata)
        {
            args.Add("--no-global-tags");
            args.Add("--no-track-tags");
        }

        if (plan.Metadata.RemoveTitle || plan.Metadata.RemoveOtherMetadata)
        {
            // mkvmerge writes no segment title when given an empty one, matching "-metadata title=".
            args.AddRange(["--title", string.Empty]);
        }

        // Per-track flags, addressed by mkvmerge track id. The ffmpeg argv indexes these by output position;
        // mkvmerge always addresses the input track, so the plan's order is irrelevant here.
        foreach (var (track, id) in plan.Audio.Zip(audio))
        {
            args.AddRange(["--default-track-flag", Flag(id, track.Default)]);
        }

        foreach (var (track, id) in plan.Subtitles.Zip(subtitles))
        {
            args.AddRange(["--default-track-flag", Flag(id, track.Default)]);
            args.AddRange(["--forced-display-flag", Flag(id, track.Forced)]);
        }

        if (plan.Metadata.RemoveLanguageTags)
        {
            // "-metadata:s language=": mkvmerge spells "no language" as the undetermined ISO code.
            foreach (var id in video.Concat(audio).Concat(subtitles))
            {
                args.AddRange(["--language", $"{id.ToString(CultureInfo.InvariantCulture)}:und"]);
            }
        }

        if (plan.Metadata.StandardizeTrackNames)
        {
            foreach (var (track, id) in plan.Audio.Zip(audio))
            {
                args.AddRange(["--track-name", $"{id.ToString(CultureInfo.InvariantCulture)}:{TrackNaming.RenderTrackName(plan.Metadata, track)}"]);
            }

            foreach (var (track, id) in plan.Subtitles.Zip(subtitles))
            {
                args.AddRange(["--track-name", $"{id.ToString(CultureInfo.InvariantCulture)}:{TrackNaming.RenderTrackName(plan.Metadata, track)}"]);
            }
        }

        if (plan.Metadata.ClearVideoTrackNames)
        {
            foreach (var id in video)
            {
                args.AddRange(["--track-name", $"{id.ToString(CultureInfo.InvariantCulture)}:"]);
            }
        }

        args.Add(src);

        // The output order: every kept video, then audio, then subtitles, which is the order
        // FfmpegCommands.BuildRemuxArgv maps them in and the order RemuxOutputValidation checks for.
        // "0:" is the first (and only) input file.
        var order = video.Concat(audio).Concat(subtitles)
            .Select(id => "0:" + id.ToString(CultureInfo.InvariantCulture));
        args.AddRange(["--track-order", string.Join(',', order)]);
        return args;
    }

    /// <summary>The prefix <c>--gui-mode</c> puts on each progress line.</summary>
    private const string GuiProgressPrefix = "#GUI#progress ";

    /// <summary>
    /// Reads one <c>--gui-mode</c> progress line (<c>#GUI#progress 26%</c>) and returns the percentage, or null
    /// for any other line.
    /// <para>
    /// This is all mkvmerge offers: unlike ffmpeg's <c>-progress pipe:1</c> stream there is no processed
    /// timestamp, speed or ETA, so <see cref="FfmpegProgressUpdate.ProcessedSeconds"/>,
    /// <see cref="FfmpegProgressUpdate.Speed"/> and <see cref="FfmpegProgressUpdate.EtaSeconds"/> stay null for
    /// an mkvmerge write and the percentage is the tool's own rather than one derived from a duration.
    /// </para>
    /// </summary>
    public static double? TryParseProgressPercent(string line)
    {
        ArgumentNullException.ThrowIfNull(line);
        var text = PyStrings.Strip(line);
        if (!text.StartsWith(GuiProgressPrefix, StringComparison.Ordinal))
        {
            return null;
        }

        var value = PyStrings.Strip(text[GuiProgressPrefix.Length..]).TrimEnd('%');
        return double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var percent)
            ? Math.Clamp(percent, 0, 100)
            : null;
    }

    /// <summary><c>logger.debug</c>'s one-line summary, matching <see cref="FfmpegCommands.DebugSummary"/>.</summary>
    public static string DebugSummary(IReadOnlyList<string> argv)
    {
        ArgumentNullException.ThrowIfNull(argv);
        return "mkvmerge " + string.Join(' ', argv.Take(8)) + " ...";
    }

    /// <summary>
    /// Attachments, keeping <see cref="MetadataRules.RemoveImages"/> and
    /// <see cref="MetadataRules.RemoveAttachments"/> independent, as they are for the ffmpeg writer.
    /// <para>
    /// For ffmpeg the two never meet: cover art is a video stream the planner leaves out of
    /// <see cref="RemuxPlan.VideoIndices"/>, while <c>-map 0:t?</c> carries the fonts. For mkvmerge both are
    /// attachments, so the two rules have to be resolved together here — mkvmerge keeps every attachment
    /// unless told otherwise, so only a removal needs saying.
    /// </para>
    /// </summary>
    private static void AddAttachmentSelection(
        List<string> args,
        MetadataRules rules,
        IReadOnlyList<MkvmergeAttachment> attachments)
    {
        if (!rules.RemoveImages && !rules.RemoveAttachments)
        {
            return;
        }

        var kept = attachments
            .Where(attachment => attachment.IsCoverArt ? !rules.RemoveImages : !rules.RemoveAttachments)
            .Select(attachment => attachment.Id)
            .ToList();

        // "--attachments" with nothing to keep is not valid, and saying nothing would keep them all.
        if (kept.Count == 0)
        {
            args.Add("--no-attachments");
            return;
        }

        // Nothing to say when everything survives: this source has none of the kind being removed.
        if (kept.Count == attachments.Count)
        {
            return;
        }

        args.AddRange(["--attachments", string.Join(',', kept.Select(id => id.ToString(CultureInfo.InvariantCulture)))]);
    }

    private static string Flag(int trackId, bool on) =>
        $"{trackId.ToString(CultureInfo.InvariantCulture)}:{(on ? "yes" : "no")}";

    private static void AddTrackSelection(List<string> args, string keepOption, string dropOption, List<int> ids)
    {
        if (ids.Count == 0)
        {
            args.Add(dropOption);
            return;
        }

        args.AddRange([keepOption, string.Join(',', ids.Select(id => id.ToString(CultureInfo.InvariantCulture)))]);
    }

    private static int TrackId(IReadOnlyDictionary<int, int> trackIds, int streamIndex) =>
        trackIds.TryGetValue(streamIndex, out var id)
            ? id
            : throw new MkvmergeTrackMappingException(
                $"the plan keeps ffprobe stream {streamIndex.ToString(CultureInfo.InvariantCulture)}, which has no mkvmerge track id.");
}
