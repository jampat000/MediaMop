namespace Weir.Core.Rules;

/// <summary>One stream's plain-language rule verdict for the "Choose tracks" screen (issue #501).</summary>
public sealed record TrackDecision(int InputIndex, string Kind, bool WouldKeep, string Reason);

public static partial class RemuxRules
{
    /// <summary>
    /// What the saved rules would do with every stream, and why (issue #501's <c>GET .../tracks</c>). This mirrors
    /// <see cref="PlanRemux"/>'s decisions stream by stream instead of returning one collapsed plan, so an operator
    /// choosing tracks by hand can see the reasoning next to each row. It is read-only and does not affect planning.
    /// </summary>
    public static IReadOnlyList<TrackDecision> ExplainTracks(
        IReadOnlyList<ProbeStreamInfo> video,
        IReadOnlyList<ProbeStreamInfo> audio,
        IReadOnlyList<ProbeStreamInfo> subtitles,
        RefinerRulesConfig config,
        IReadOnlyList<ProbeStreamInfo>? attachments = null)
    {
        ArgumentNullException.ThrowIfNull(video);
        ArgumentNullException.ThrowIfNull(audio);
        ArgumentNullException.ThrowIfNull(subtitles);
        ArgumentNullException.ThrowIfNull(config);

        var rules = config.Metadata;
        var decisions = new List<TrackDecision>();

        var (realVideo, imageStreams) = MetadataStreams.SplitVideoAndImages(video);
        var realIndices = new HashSet<int>();
        foreach (var (_, index) in WithIndex(realVideo))
        {
            realIndices.Add(index);
        }

        foreach (var (stream, index) in WithIndex(video))
        {
            if (realIndices.Contains(index))
            {
                decisions.Add(new TrackDecision(index, "video", true, "Kept as the video track."));
                continue;
            }

            var keep = !rules.RemoveImages;
            decisions.Add(new TrackDecision(
                index,
                "image",
                keep,
                keep
                    ? "Embedded image kept because remove embedded images is off."
                    : $"Removed {MetadataStreams.DescribeImageStream(stream)} because remove embedded images is enabled."));
        }

        foreach (var (stream, index) in WithIndex(attachments ?? []))
        {
            var keep = !rules.RemoveAttachments;
            decisions.Add(new TrackDecision(
                index,
                "attachment",
                keep,
                keep
                    ? "Attachment kept because remove attachments is off."
                    : $"Removed {MetadataStreams.DescribeAttachmentStream(stream)} because remove attachments is enabled."));
        }

        var commentaryExcluded = new HashSet<int>();
        var candidates = new List<AudioCandidate>();
        foreach (var (stream, index) in WithIndex(audio))
        {
            var flags = TrackFlagsReader.Detect(stream);
            if (config.RemoveCommentary && flags.Commentary.Value)
            {
                commentaryExcluded.Add(index);
                continue;
            }

            candidates.Add(CandidateFromStream(stream, index));
        }

        var scratchNotes = new List<string>();
        var winner = candidates.Count > 0 ? SelectAudioWinner(config, [.. candidates], scratchNotes) : null;
        foreach (var (_, index) in WithIndex(audio))
        {
            if (commentaryExcluded.Contains(index))
            {
                decisions.Add(new TrackDecision(index, "audio", false, "Removed: commentary track, and remove commentary is enabled."));
                continue;
            }

            var candidate = candidates.First(c => c.InputIndex == index);
            if (winner is not null && winner.InputIndex == index)
            {
                decisions.Add(new TrackDecision(index, "audio", true, $"Kept: selected as the best audio track ({DescribeCandidate(candidate)})."));
            }
            else
            {
                decisions.Add(new TrackDecision(
                    index,
                    "audio",
                    false,
                    winner is null
                        ? "Removed: no audio track could be selected."
                        : $"Removed: not selected ({DescribeCandidate(winner)} was kept instead)."));
            }
        }

        var removeAll = config.SubtitleMode == RemuxRuleValues.SubtitleModeRemoveAll || config.SubtitleLangs.Count == 0;
        var selectedLangs = removeAll ? [] : new HashSet<string>(config.SubtitleLangs.Select(NormalizeLang), StringComparer.Ordinal);
        foreach (var (stream, index) in WithIndex(subtitles))
        {
            var lang = NormalizeLang(stream.Tag("language"));
            if (removeAll)
            {
                decisions.Add(new TrackDecision(index, "subtitle", false, "Removed: the saved rules remove every subtitle track."));
                continue;
            }

            if (lang.Length == 0 || !selectedLangs.Contains(lang))
            {
                decisions.Add(new TrackDecision(
                    index, "subtitle", false, $"Removed: language '{(lang.Length > 0 ? lang : "und")}' is not in the configured subtitle languages."));
                continue;
            }

            var flags = TrackFlagsReader.Detect(stream);
            if (config.RemoveHearingImpairedSubs && flags.HearingImpaired.Value)
            {
                var source = flags.HearingImpaired.Source == TrackFlagSource.Disposition ? "its hearing-impaired flag" : "its name";
                decisions.Add(new TrackDecision(
                    index, "subtitle", false, $"Removed: hearing-impaired subtitle ({source}), and remove hearing-impaired subtitles is enabled."));
                continue;
            }

            var forced = config.PreserveForcedSubs && flags.Forced.Value;
            var reason = $"Kept: language '{lang}' matches the configured subtitle languages.";
            if (forced && flags.Forced.Source == TrackFlagSource.Name)
            {
                reason += " Counts as forced because its name says so.";
            }

            decisions.Add(new TrackDecision(index, "subtitle", true, reason));
        }

        return decisions;
    }
}
