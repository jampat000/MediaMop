using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Tests for issue #501's <c>RemuxRules.ExplainTracks</c>: a stream-by-stream account of what the saved rules would
/// do and why, used by <c>GET /refiner/files/{id}/tracks</c> so an operator can see the reasoning before overriding it.
/// </summary>
public sealed class RemuxTrackExplainTests
{
    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static readonly ProbeStreamInfo Video = Stream("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");

    [Fact]
    public void The_video_track_is_always_explained_as_kept()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig();

        var decisions = RemuxRules.ExplainTracks([Video], [audio], [], config);

        var videoDecision = Assert.Single(decisions, d => d.Kind == "video");
        Assert.True(videoDecision.WouldKeep);
        Assert.Equal(0, videoDecision.InputIndex);
    }

    [Fact]
    public void A_commentary_track_is_explained_as_removed_when_remove_commentary_is_enabled()
    {
        var english = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}, "disposition": {"default": 1}}""");
        var commentary = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng", "title": "Director commentary"}}""");
        var config = RemuxRules.DefaultConfig() with { RemoveCommentary = true };

        var decisions = RemuxRules.ExplainTracks([Video], [english, commentary], [], config);

        var commentaryDecision = decisions.Single(d => d.InputIndex == 2);
        Assert.False(commentaryDecision.WouldKeep);
        Assert.Contains("commentary", commentaryDecision.Reason, StringComparison.OrdinalIgnoreCase);
        var englishDecision = decisions.Single(d => d.InputIndex == 1);
        Assert.True(englishDecision.WouldKeep);
    }

    [Fact]
    public void A_non_selected_audio_track_is_explained_as_removed_naming_the_winner()
    {
        var english = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");
        var japanese = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "jpn"}}""");
        var config = RemuxRules.DefaultConfig();

        var decisions = RemuxRules.ExplainTracks([Video], [english, japanese], [], config);

        var winner = decisions.Single(d => d.InputIndex == 1);
        Assert.True(winner.WouldKeep);
        Assert.Contains("selected", winner.Reason, StringComparison.OrdinalIgnoreCase);
        var loser = decisions.Single(d => d.InputIndex == 2);
        Assert.False(loser.WouldKeep);
        Assert.Contains("not selected", loser.Reason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void A_subtitle_in_a_configured_language_is_explained_as_kept()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");
        var englishSub = Stream("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["eng"] };

        var decisions = RemuxRules.ExplainTracks([Video], [audio], [englishSub], config);

        var subtitleDecision = decisions.Single(d => d.Kind == "subtitle");
        Assert.True(subtitleDecision.WouldKeep);
        Assert.Contains("eng", subtitleDecision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void A_subtitle_not_in_the_configured_languages_is_explained_as_removed()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");
        var frenchSub = Stream("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "fre"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["eng"] };

        var decisions = RemuxRules.ExplainTracks([Video], [audio], [frenchSub], config);

        var subtitleDecision = decisions.Single(d => d.Kind == "subtitle");
        Assert.False(subtitleDecision.WouldKeep);
        Assert.Contains("not in the configured", subtitleDecision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Every_subtitle_is_explained_as_removed_when_the_mode_removes_all()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");
        var englishSub = Stream("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeRemoveAll };

        var decisions = RemuxRules.ExplainTracks([Video], [audio], [englishSub], config);

        var subtitleDecision = decisions.Single(d => d.Kind == "subtitle");
        Assert.False(subtitleDecision.WouldKeep);
    }

    [Fact]
    public void An_embedded_image_is_explained_as_removed_when_remove_images_is_enabled()
    {
        var poster = Stream("""{"index": 1, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}}""");
        var audio = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with { Metadata = new MetadataRules { RemoveImages = true } };

        var decisions = RemuxRules.ExplainTracks([Video, poster], [audio], [], config);

        var imageDecision = decisions.Single(d => d.Kind == "image");
        Assert.False(imageDecision.WouldKeep);
        Assert.Contains("embedded image", imageDecision.Reason, StringComparison.OrdinalIgnoreCase);
    }
}
