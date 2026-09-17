using Weir.Core.Json;

namespace Weir.Core.Rules;

/// <summary>What to strip (<c>refiner_metadata_rules.MetadataRules</c>). All off by default, so an upgrade changes nothing.</summary>
public sealed record MetadataRules
{
    public bool RemoveImages { get; init; }
    public bool RemoveAttachments { get; init; }
    public bool RemoveTitle { get; init; }
    public bool RemoveLanguageTags { get; init; }
    public bool RemoveOtherMetadata { get; init; }

    public bool AnyEnabled => RemoveImages || RemoveAttachments || RemoveTitle || RemoveLanguageTags || RemoveOtherMetadata;
}

/// <summary>
/// Embedded images, attachments and container metadata (<c>refiner_metadata_rules.py</c>).
/// An embedded poster is an mjpeg video stream, so the planner separates it from the picture.
/// </summary>
public static class MetadataStreams
{
    private static readonly HashSet<string> ImageCodecs = new(StringComparer.Ordinal) { "mjpeg", "png", "bmp", "gif", "webp", "jpeg", "tiff" };

    /// <summary>True for an embedded poster or thumbnail carried as a video stream.</summary>
    public static bool IsImageStream(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var disposition = stream.Get("disposition");
        if (Py.IsDict(disposition))
        {
            var attachedPic = Py.Get(disposition!.Value, "attached_pic");
            if (Py.Truthy(attachedPic) && Py.Int(attachedPic) != 0)
            {
                return true;
            }
        }

        var codec = Py.Lower(PyStrings.Strip(Py.StrOr(stream.Get("codec_name"), string.Empty)));
        if (!ImageCodecs.Contains(codec))
        {
            return false;
        }

        // A codec alone is not proof: a single frame, or a stream with no frame rate, is a still.
        var frames = stream.Get("nb_frames");
        if (!Py.IsNone(frames) && Py.TryInt(frames, out var frameCount) && frameCount <= 1)
        {
            return true;
        }

        var rate = PyStrings.Strip(Py.StrOr(stream.Get("avg_frame_rate"), string.Empty));
        return rate is "" or "0/0" or "0/1";
    }

    /// <summary>True for an attached font or similar.</summary>
    public static bool IsAttachmentStream(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        return Py.Lower(PyStrings.Strip(Py.StrOr(stream.Get("codec_type"), string.Empty))) == "attachment";
    }

    /// <summary>(real video, embedded images). A file of nothing but images keeps its first stream as the picture.</summary>
    public static (IReadOnlyList<ProbeStreamInfo> Real, IReadOnlyList<ProbeStreamInfo> Images) SplitVideoAndImages(IEnumerable<ProbeStreamInfo> videoStreams)
    {
        ArgumentNullException.ThrowIfNull(videoStreams);
        var real = new List<ProbeStreamInfo>();
        var images = new List<ProbeStreamInfo>();
        foreach (var stream in videoStreams)
        {
            (IsImageStream(stream) ? images : real).Add(stream);
        }

        if (real.Count == 0 && images.Count > 0)
        {
            return ([images[0]], images.Skip(1).ToList());
        }

        return (real, images);
    }

    public static string DescribeImageStream(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var codec = PyStrings.Strip(Py.StrOr(stream.Get("codec_name"), "unknown"));
        var width = stream.Get("width");
        var height = stream.Get("height");
        var size = Py.Truthy(width) && Py.Truthy(height) ? $"{Py.Str(width)}x{Py.Str(height)}" : "unknown size";
        return $"embedded image ({codec}, {size})";
    }

    public static string DescribeAttachmentStream(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var tags = stream.Get("tags");
        var name = string.Empty;
        if (Py.IsDict(tags))
        {
            var filename = Py.Get(tags!.Value, "filename");
            var chosen = Py.Truthy(filename) ? filename : Py.Get(tags.Value, "title");
            name = PyStrings.Strip(Py.StrOr(chosen, string.Empty));
        }

        return name.Length > 0 ? $"attachment ({name})" : "attachment";
    }

    /// <summary>The ffmpeg flags for container-level stripping, in the order the reference emits them.</summary>
    public static IReadOnlyList<string> ArgvFlags(MetadataRules rules)
    {
        ArgumentNullException.ThrowIfNull(rules);
        var flags = new List<string>();
        if (rules.RemoveOtherMetadata)
        {
            flags.AddRange(["-map_metadata", "-1"]);
        }
        else if (rules.RemoveTitle)
        {
            flags.AddRange(["-metadata", "title="]);
        }

        if (rules.RemoveOtherMetadata && rules.RemoveTitle)
        {
            flags.AddRange(["-metadata", "title="]);
        }

        if (rules.RemoveLanguageTags)
        {
            flags.AddRange(["-metadata:s", "language="]);
        }

        return flags;
    }

    /// <summary>What was stripped, for the before/after display and the activity detail.</summary>
    public static IReadOnlyList<string> RemovalNotes(
        MetadataRules rules,
        IEnumerable<ProbeStreamInfo> removedImages,
        IEnumerable<ProbeStreamInfo> removedAttachments)
    {
        ArgumentNullException.ThrowIfNull(rules);
        ArgumentNullException.ThrowIfNull(removedImages);
        ArgumentNullException.ThrowIfNull(removedAttachments);
        var notes = new List<string>();
        notes.AddRange(removedImages.Select(s => $"Removed {DescribeImageStream(s)}."));
        notes.AddRange(removedAttachments.Select(s => $"Removed {DescribeAttachmentStream(s)}."));
        if (rules.RemoveTitle)
        {
            notes.Add("Removed the container title.");
        }

        if (rules.RemoveLanguageTags)
        {
            notes.Add("Removed stream language tags.");
        }

        if (rules.RemoveOtherMetadata)
        {
            notes.Add("Removed the remaining container metadata.");
        }

        return notes;
    }
}
