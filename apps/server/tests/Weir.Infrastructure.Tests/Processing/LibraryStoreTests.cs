using Weir.Core.Processing;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Jobs;

namespace Weir.Infrastructure.Tests.Processing;

/// <summary>Real-SQLite proof of <c>LibraryStore</c> (port of the persistence half of
/// <c>processing_library_crud.py</c>/<c>processing_library_service.py</c>, ADR-0014).</summary>
public sealed class LibraryStoreTests
{
    private static ProcessingLibraryInput NewLibrary(string name, string watched = "", string output = "", string mediaType = "movie") => new()
    {
        Name = name,
        MediaType = mediaType,
        WatchedFolder = watched,
        OutputFolder = output,
    };

    [Fact]
    public async Task A_fresh_database_seeds_the_movies_and_tv_libraries()
    {
        using var db = new JobsTestDatabase(keepSeedRows: true);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var rows = await LibraryStore.ListAsync(uow);

        Assert.Equal(["Movies", "TV"], rows.Select(r => r.Name));
        Assert.Equal(["movie", "tv"], rows.Select(r => r.MediaType));
    }

    [Fact]
    public async Task Creating_a_library_assigns_the_next_display_order_and_round_trips_every_field()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var created = await LibraryStore.CreateAsync(uow, NewLibrary("4K", watched: @"c:\media\4k-in", output: @"c:\media\4k-out"));

        Assert.True(created.Id > 0);
        Assert.Equal("4K", created.Name);
        Assert.Equal("movie", created.MediaType);
        Assert.Equal(@"c:\media\4k-in", created.WatchedFolder);
        Assert.Equal(ProcessingFailurePolicies.PassThrough, created.FailurePolicy);

        var reloaded = await LibraryStore.GetAsync(uow, created.Id);
        Assert.NotNull(reloaded);
        Assert.Equal(created.Name, reloaded!.Name);
    }

    [Fact]
    public async Task Two_libraries_may_not_share_a_name()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));

        var exception = await Assert.ThrowsAsync<ProcessingLibraryException>(() => LibraryStore.CreateAsync(uow, NewLibrary("Anime")));
        Assert.Contains("already exists", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_librarys_watched_folder_may_not_overlap_another_librarys_output_folder()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        await LibraryStore.CreateAsync(uow, NewLibrary("Anime", watched: @"c:\media\anime-in", output: @"c:\media\anime-out"));

        var exception = await Assert.ThrowsAsync<ProcessingLibraryException>(() =>
            LibraryStore.CreateAsync(uow, NewLibrary("Anime 4K", watched: @"c:\media\anime-out", output: @"c:\media\anime4k-out")));
        Assert.Contains("Anime", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Deleting_a_library_with_queued_work_is_refused()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var library = await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));
        await uow.CommitAsync(); // release the write lock before the raw connection below takes it
        db.Execute(
            "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status) VALUES ('k1', 'processing.file.remux_pass.v1', @payload, 'pending')",
            ("@payload", $"{{\"library_id\": {library.Id}}}"));

        var exception = await Assert.ThrowsAsync<ProcessingLibraryException>(() => LibraryStore.DeleteAsync(uow, library));
        Assert.Contains("1 job", exception.Message, StringComparison.Ordinal);

        Assert.NotNull(await LibraryStore.GetAsync(uow, library.Id));
    }

    [Fact]
    public async Task Deleting_a_library_with_no_queued_work_succeeds()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var library = await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));

        await LibraryStore.DeleteAsync(uow, library);

        Assert.Null(await LibraryStore.GetAsync(uow, library.Id));
    }

    [Fact]
    public async Task Reordering_lists_libraries_in_the_new_display_order()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var a = await LibraryStore.CreateAsync(uow, NewLibrary("A"));
        var b = await LibraryStore.CreateAsync(uow, NewLibrary("B"));

        var reordered = await LibraryStore.ReorderAsync(uow, [b.Id, a.Id]);

        Assert.Equal(["B", "A"], reordered.Select(r => r.Name));
    }

    [Fact]
    public async Task Reordering_without_every_library_is_refused()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var a = await LibraryStore.CreateAsync(uow, NewLibrary("A"));
        await LibraryStore.CreateAsync(uow, NewLibrary("B"));

        await Assert.ThrowsAsync<ProcessingLibraryException>(() => LibraryStore.ReorderAsync(uow, [a.Id]));
    }

    [Fact]
    public async Task Manager_links_can_be_set_then_cleared()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var library = await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));
        await uow.CommitAsync(); // release the write lock before the raw connection below takes it
        db.Execute("INSERT INTO media_manager_connections (id, kind, name) VALUES (1, 'sonarr', 'Sonarr')");

        await LibraryStore.SetManagerLinksAsync(uow, library.Id, [1]);
        Assert.Equal([1L], await LibraryStore.ManagerConnectionIdsAsync(uow, library.Id));

        await LibraryStore.SetManagerLinksAsync(uow, library.Id, []);
        Assert.Empty(await LibraryStore.ManagerConnectionIdsAsync(uow, library.Id));
    }

    [Fact]
    public async Task Linking_an_unknown_manager_connection_is_refused()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var library = await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));

        await Assert.ThrowsAsync<ProcessingLibraryException>(() => LibraryStore.SetManagerLinksAsync(uow, library.Id, [999]));
    }

    [Fact]
    public async Task A_rule_set_still_used_by_a_library_cannot_be_deleted()
    {
        using var db = new JobsTestDatabase(keepSeedRows: true);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var ruleSet = await LibraryStore.GetRuleSetAsync(uow, 1);
        Assert.NotNull(ruleSet);

        var exception = await Assert.ThrowsAsync<ProcessingLibraryException>(() => LibraryStore.DeleteRuleSetAsync(uow, ruleSet!));
        Assert.Contains("still used", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_rule_set_no_longer_referenced_can_be_deleted()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var ruleSet = await LibraryStore.CreateRuleSetAsync(uow, new Weir.Core.Processing.LibraryRules.RuleSetInput { Name = "Spare" });

        await LibraryStore.DeleteRuleSetAsync(uow, ruleSet);

        Assert.Null(await LibraryStore.GetRuleSetAsync(uow, ruleSet.Id));
    }

    [Fact]
    public async Task Creating_a_rule_set_fills_empty_sorters_from_the_default_preset()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var ruleSet = await LibraryStore.CreateRuleSetAsync(uow, new Weir.Core.Processing.LibraryRules.RuleSetInput { Name = "Custom" });

        Assert.False(string.IsNullOrWhiteSpace(ruleSet.AudioSortersJson));
        Assert.NotEqual("[]", ruleSet.AudioSortersJson.Trim());
    }

    [Fact]
    public async Task Creating_and_updating_a_rule_set_round_trips_every_495_497_498_field()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var overrides = new Weir.Core.Rules.TrackNameOverrides
        {
            Forced = "{language} (Forced)",
            HearingImpaired = "{language} (SDH)",
            Commentary = "{language} (Commentary)",
            AudioDescription = "{language} (AD)",
        };
        var input = new Weir.Core.Processing.LibraryRules.RuleSetInput
        {
            Name = "Round trip",
            RemoveHearingImpairedSubs = true,
            AudioKeepMode = Weir.Core.Rules.RemuxRuleValues.AudioKeepModePerLanguage,
            SubtitleMaxPerLanguage = 3,
            SubtitleQualityStrategy = Weir.Core.Rules.RemuxRuleValues.SubtitleStrategyImageFirst,
            StandardizeTrackNames = true,
            TrackNameTemplate = "{language} {channels} {codec}",
            TrackNameOverrides = overrides,
            ClearVideoTrackNames = true,
            RemoveChapters = true,
        };

        var created = await LibraryStore.CreateRuleSetAsync(uow, input);
        var reloadedAfterCreate = await LibraryStore.GetRuleSetAsync(uow, created.Id);

        foreach (var row in new[] { created, reloadedAfterCreate })
        {
            Assert.True(row!.RemoveHearingImpairedSubs);
            Assert.Equal(Weir.Core.Rules.RemuxRuleValues.AudioKeepModePerLanguage, row.AudioKeepMode);
            Assert.Equal(3, row.SubtitleMaxPerLanguage);
            Assert.Equal(Weir.Core.Rules.RemuxRuleValues.SubtitleStrategyImageFirst, row.SubtitleQualityStrategy);
            Assert.True(row.StandardizeTrackNames);
            Assert.Equal("{language} {channels} {codec}", row.TrackNameTemplate);
            Assert.Equal(overrides, row.TrackNameOverrides);
            Assert.True(row.ClearVideoTrackNames);
            Assert.True(row.RemoveChapters);
        }

        // The plain sorter list (filled from the default preset, same as any other new rule set)
        // survives the same round trip, unaffected by packing the new fields alongside it in the
        // same column.
        Assert.False(string.IsNullOrWhiteSpace(reloadedAfterCreate!.SubtitleSortersJson));
        Assert.Equal(created.SubtitleSortersJson, reloadedAfterCreate.SubtitleSortersJson);

        var updated = await LibraryStore.UpdateRuleSetAsync(
            uow,
            created,
            input with { RemoveHearingImpairedSubs = false, AudioKeepMode = Weir.Core.Rules.RemuxRuleValues.AudioKeepModeSingle, SubtitleMaxPerLanguage = 0 });
        var reloadedAfterUpdate = await LibraryStore.GetRuleSetAsync(uow, created.Id);

        Assert.False(updated.RemoveHearingImpairedSubs);
        Assert.Equal(Weir.Core.Rules.RemuxRuleValues.AudioKeepModeSingle, updated.AudioKeepMode);
        Assert.Equal(0, updated.SubtitleMaxPerLanguage);
        Assert.False(reloadedAfterUpdate!.RemoveHearingImpairedSubs);
        // Untouched-by-the-update fields (#498) survive the update too.
        Assert.True(reloadedAfterUpdate.StandardizeTrackNames);
        Assert.Equal(overrides, reloadedAfterUpdate.TrackNameOverrides);
    }

    [Fact]
    public async Task A_pre_495_497_498_row_with_a_plain_sorter_array_column_reads_back_every_new_field_at_its_default()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var created = await LibraryStore.CreateRuleSetAsync(uow, new Weir.Core.Processing.LibraryRules.RuleSetInput { Name = "Legacy row" });
        await uow.CommitAsync(); // release the write lock before the raw connection below takes it

        // Simulate a row written before #495/#497/#498 existed: subtitle_sorters_json holds only the
        // plain sorter array this column has always stored, never the extras envelope.
        const string legacySorters = """[{"field":"forced","value":null,"reversed":false}]""";
        db.Execute("UPDATE rule_sets SET subtitle_sorters_json = @json WHERE id = @id", ("@json", legacySorters), ("@id", created.Id));

        var reloaded = await LibraryStore.GetRuleSetAsync(uow, created.Id);

        Assert.Equal(legacySorters, reloaded!.SubtitleSortersJson);
        Assert.False(reloaded.RemoveHearingImpairedSubs);
        Assert.Equal(Weir.Core.Rules.RemuxRuleValues.AudioKeepModeSingle, reloaded.AudioKeepMode);
        Assert.Equal(0, reloaded.SubtitleMaxPerLanguage);
        Assert.Equal(Weir.Core.Rules.RemuxRuleValues.SubtitleStrategyTextFirst, reloaded.SubtitleQualityStrategy);
        Assert.False(reloaded.StandardizeTrackNames);
        Assert.Equal(Weir.Core.Rules.TrackNaming.DefaultTemplate, reloaded.TrackNameTemplate);
        Assert.Equal(new Weir.Core.Rules.TrackNameOverrides(), reloaded.TrackNameOverrides);
        Assert.False(reloaded.ClearVideoTrackNames);
        Assert.False(reloaded.RemoveChapters);
    }

    [Fact]
    public async Task Active_job_count_matches_the_library_id_carried_in_the_payload()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var library = await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));
        await uow.CommitAsync(); // release the write lock before the raw connection below takes it
        db.Execute(
            "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status) VALUES ('k1', 'processing.file.remux_pass.v1', @payload, 'leased')",
            ("@payload", $"{{\"library_id\": {library.Id}}}"));
        db.Execute(
            "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status) VALUES ('k2', 'processing.file.remux_pass.v1', @payload, 'completed')",
            ("@payload", $"{{\"library_id\": {library.Id}}}"));

        var reloaded = await LibraryStore.GetAsync(uow, library.Id);
        var active = await LibraryStore.ActiveJobCountAsync(uow, reloaded!);

        Assert.Equal(1, active);
    }
}
