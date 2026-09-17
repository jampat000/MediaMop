using Weir.Core.Refiner;
using Weir.Infrastructure.Refiner.DirectPlay;

namespace Weir.Infrastructure.Tests.Refiner;

/// <summary>Ported from <c>apps/backend/tests/test_direct_play.py</c> (#467): the shipped device list and
/// the answers it gives for a handful of concrete files, against the real embedded <c>devices.json</c>.</summary>
public sealed class DirectPlayEvaluationTests
{
    private static readonly IReadOnlyList<DeviceProfile> Profiles = DeviceProfileLoader.Load(null);

    private static DeviceProfile Device(string id) => Profiles.First(p => p.Id == id);

    private static MediaFacts Facts(
        string? container = "mp4",
        string? videoCodec = "hevc",
        long? videoHeight = 2160,
        long? videoBitDepth = 10,
        IReadOnlyList<string>? audioCodecs = null) =>
        new(container, videoCodec, videoHeight, videoBitDepth, audioCodecs ?? ["aac"]);

    [Fact]
    public void Every_shipped_device_names_its_source_and_is_unique()
    {
        var ids = new HashSet<string>(Profiles.Select(p => p.Id), StringComparer.Ordinal);
        foreach (var required in new[] { "apple_tv_4k", "lg_webos", "samsung_tizen_2024", "iphone_ipad", "chromecast_google_tv", "fire_tv", "roku", "web_browser" })
        {
            Assert.Contains(required, ids);
        }

        Assert.Equal(Profiles.Count, ids.Count);
        Assert.All(Profiles, p => Assert.StartsWith("https://", p.Source, StringComparison.Ordinal));
        Assert.All(Profiles, p => Assert.NotEmpty(p.ContainersYes));
    }

    [Fact]
    public void An_operators_own_list_replaces_the_shipped_one_without_a_release()
    {
        using var temp = new TempDirectory();
        File.WriteAllText(
            Path.Combine(temp.Path, DirectPlayEvaluation.OverrideFileName),
            """
            {"devices": [{"id": "shield", "name": "Shield", "source": "https://example.test/shield",
            "containers": {"yes": ["mkv"]}, "video": {"hevc": {}}, "audio": {"yes": ["truehd"]}}]}
            """);

        var loaded = DeviceProfileLoader.Load(temp.Path);
        Assert.Equal(["shield"], loaded.Select(p => p.Id));
    }

    [Fact]
    public void An_unreadable_own_list_falls_back_to_the_shipped_one()
    {
        using var temp = new TempDirectory();
        File.WriteAllText(Path.Combine(temp.Path, DirectPlayEvaluation.OverrideFileName), "{not json");

        var loaded = DeviceProfileLoader.Load(temp.Path);
        Assert.Contains("apple_tv_4k", loaded.Select(p => p.Id));
    }

    [Fact]
    public void A_file_that_fits_plays_directly() => Assert.Equal("yes", DirectPlayEvaluation.Evaluate(Device("iphone_ipad"), Facts()).Verdict);

    [Fact]
    public void Apple_tvs_own_player_does_not_play_mkv_and_says_so()
    {
        var verdict = DirectPlayEvaluation.Evaluate(Device("apple_tv_4k"), Facts(container: "mkv"));
        Assert.Equal("no", verdict.Verdict);
        Assert.Equal(["cannot play MKV files"], verdict.Reasons);
    }

    [Fact]
    public void Dts_is_named_as_the_reason_on_a_2024_samsung()
    {
        var verdict = DirectPlayEvaluation.Evaluate(Device("samsung_tizen_2024"), Facts(container: "mkv", audioCodecs: ["dts"]));
        Assert.Equal("no", verdict.Verdict);
        Assert.Equal(["cannot play DTS audio"], verdict.Reasons);
    }

    [Fact]
    public void Model_dependent_support_is_maybe_not_yes()
    {
        Assert.Equal("maybe", DirectPlayEvaluation.Evaluate(Device("lg_webos"), Facts(container: "mkv", audioCodecs: ["dts"])).Verdict);
        Assert.Equal("maybe", DirectPlayEvaluation.Evaluate(Device("roku"), Facts(container: "mkv")).Verdict);
    }

    [Fact]
    public void One_unplayable_track_among_playable_ones_is_maybe()
    {
        var verdict = DirectPlayEvaluation.Evaluate(Device("iphone_ipad"), Facts(audioCodecs: ["aac", "truehd"]));
        Assert.Equal("maybe", verdict.Verdict);
        Assert.Equal(["may not play Dolby TrueHD audio on some tracks"], verdict.Reasons);
    }

    [Fact]
    public void A_limit_the_source_states_is_applied()
    {
        var verdict = DirectPlayEvaluation.Evaluate(Device("apple_tv_4k"), Facts(videoCodec: "h264", videoBitDepth: 10));
        Assert.Equal("no", verdict.Verdict);
        Assert.Contains("10-bit video is above 8-bit", verdict.Reasons[0], StringComparison.Ordinal);
    }

    [Fact]
    public void Samsung_plays_hevc_only_in_the_containers_it_names()
    {
        var verdict = DirectPlayEvaluation.Evaluate(Device("samsung_tizen_2024"), Facts(container: "avi"));
        Assert.Equal("no", verdict.Verdict);
        Assert.Contains("only in MKV, MP4, TS", verdict.Reasons[0], StringComparison.Ordinal);
    }

    [Fact]
    public void A_fact_nobody_measured_is_unknown_never_no()
    {
        // Built directly rather than through Facts(): its audioCodecs default would coalesce an explicit
        // null back to ["aac"], which is exactly the "measured" state this case must not be.
        var facts = new MediaFacts(Container: "mp4", VideoCodec: "h264", VideoHeight: 2160, VideoBitDepth: 8, AudioCodecs: null);
        var verdict = DirectPlayEvaluation.Evaluate(Device("roku"), facts);
        Assert.Equal("unknown", verdict.Verdict);
    }

    [Fact]
    public void Pcm_variants_count_as_pcm_and_containers_come_from_the_file_name()
    {
        Assert.Equal("yes", DirectPlayEvaluation.Evaluate(Device("apple_tv_4k"), Facts(audioCodecs: ["pcm_s24le"])).Verdict);
        Assert.Equal("mkv", DirectPlayEvaluation.ContainerForPath("Film/Film.2020.MKV"));
        Assert.Null(DirectPlayEvaluation.ContainerForPath("Film/no-extension"));
    }
}
