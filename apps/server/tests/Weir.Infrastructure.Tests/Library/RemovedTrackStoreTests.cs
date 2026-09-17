using Weir.Core.Library;
using Weir.Core.Rules;
using Weir.Infrastructure.Library;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Library;

/// <summary>Both <see cref="IRemovedTrackStore"/> implementations (#509 step 1): in-memory and payload-backed.</summary>
public sealed class RemovedTrackStoreTests
{
    private static RemovedTrackRecord Track(string lang, RemovedTrackType type = RemovedTrackType.Audio) => new()
    {
        Language = lang,
        Type = type,
        Codec = "aac",
        Reason = "not selected",
    };

    [Fact]
    public async Task In_memory_store_round_trips_and_replaces_on_a_second_record()
    {
        var store = new InMemoryRemovedTrackStore();
        var key = new RemovedTrackFileKey(1, "Movies/A.mkv");

        Assert.Empty(await store.GetAsync(key));

        await store.RecordAsync(key, [Track("jpn")]);
        Assert.Equal(["jpn"], (await store.GetAsync(key)).Select(t => t.Language));

        // A second recording (a re-clean under different rules) replaces, it does not accumulate.
        await store.RecordAsync(key, [Track("fre"), Track("spa", RemovedTrackType.Subtitle)]);
        var tracks = await store.GetAsync(key);
        Assert.Equal(["fre", "spa"], tracks.Select(t => t.Language));

        var all = await store.GetAllAsync();
        var only = Assert.Single(all);
        Assert.Equal(key, only.Key);
    }

    [Fact]
    public async Task File_log_backed_store_round_trips_through_the_existing_detail_json_column()
    {
        using var fixture = new StoreFixture();
        var store = new FileLogRemovedTrackStore(fixture.Database, fixture.Clock);
        var key = new RemovedTrackFileKey(1, "Movies/A.mkv");

        Assert.Empty(await store.GetAsync(key));

        await store.RecordAsync(key, [Track("jpn"), Track("spa", RemovedTrackType.Subtitle)]);

        var tracks = await store.GetAsync(key);
        Assert.Equal(2, tracks.Count);
        Assert.Equal("jpn", tracks[0].Language);
        Assert.Equal(RemovedTrackType.Audio, tracks[0].Type);
        Assert.Equal("aac", tracks[0].Codec);
        Assert.Equal("spa", tracks[1].Language);
        Assert.Equal(RemovedTrackType.Subtitle, tracks[1].Type);

        var all = await store.GetAllAsync();
        var only = Assert.Single(all);
        Assert.Equal(key, only.Key);
    }

    [Fact]
    public async Task File_log_backed_store_reads_the_newest_row_when_recorded_twice()
    {
        using var fixture = new StoreFixture();
        var store = new FileLogRemovedTrackStore(fixture.Database, fixture.Clock);
        var key = new RemovedTrackFileKey(null, "Movies/B.mkv");

        await store.RecordAsync(key, [Track("jpn")]);
        fixture.Clock.Set(fixture.Clock.GetUtcNow().AddMinutes(1));
        await store.RecordAsync(key, [Track("fre")]);

        var tracks = await store.GetAsync(key);
        var only = Assert.Single(tracks);
        Assert.Equal("fre", only.Language);
    }

    [Fact]
    public async Task File_log_backed_store_falls_back_to_legacy_free_text_removed_lists()
    {
        using var fixture = new StoreFixture();
        var store = new FileLogRemovedTrackStore(fixture.Database, fixture.Clock);
        await using (var uow = await Weir.Infrastructure.Sqlite.UnitOfWork.OpenAsync(fixture.Database))
        {
            await uow.ExecuteAsync(
                "INSERT INTO refiner_file_logs (library_id, relative_path, outcome, detail_json) VALUES (@lib, @path, 'refiner.file.remux_pass.v1', @detail)",
                ("@lib", 2L),
                ("@path", "Movies/Legacy.mkv"),
                ("@detail", """{"removed_audio":["jpn: removed (not selected — eng dts kept)"],"removed_subtitles":["spa"]}"""));
            await uow.CommitAsync();
        }

        var tracks = await store.GetAsync(new RemovedTrackFileKey(2, "Movies/Legacy.mkv"));

        Assert.Equal(2, tracks.Count);
        Assert.Equal("jpn", tracks[0].Language);
        Assert.Equal(RemovedTrackType.Audio, tracks[0].Type);
        Assert.Equal("unknown", tracks[0].Codec);
        Assert.Equal("spa", tracks[1].Language);
        Assert.Equal(RemovedTrackType.Subtitle, tracks[1].Type);
    }
}
