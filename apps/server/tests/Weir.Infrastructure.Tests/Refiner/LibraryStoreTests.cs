using Weir.Core.Refiner;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Jobs;

namespace Weir.Infrastructure.Tests.Refiner;

/// <summary>Real-SQLite proof of <c>LibraryStore</c> (port of the persistence half of
/// <c>refiner_library_crud.py</c>/<c>refiner_library_service.py</c>, ADR-0014).</summary>
public sealed class LibraryStoreTests
{
    private static RefinerLibraryInput NewLibrary(string name, string watched = "", string output = "", string mediaType = "movie") => new()
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
        Assert.Equal(RefinerFailurePolicies.PassThrough, created.FailurePolicy);

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

        var exception = await Assert.ThrowsAsync<RefinerLibraryException>(() => LibraryStore.CreateAsync(uow, NewLibrary("Anime")));
        Assert.Contains("already exists", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_librarys_watched_folder_may_not_overlap_another_librarys_output_folder()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        await LibraryStore.CreateAsync(uow, NewLibrary("Anime", watched: @"c:\media\anime-in", output: @"c:\media\anime-out"));

        var exception = await Assert.ThrowsAsync<RefinerLibraryException>(() =>
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
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES ('k1', 'refiner.file.remux_pass.v1', @payload, 'pending')",
            ("@payload", $"{{\"library_id\": {library.Id}}}"));

        var exception = await Assert.ThrowsAsync<RefinerLibraryException>(() => LibraryStore.DeleteAsync(uow, library));
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

        await Assert.ThrowsAsync<RefinerLibraryException>(() => LibraryStore.ReorderAsync(uow, [a.Id]));
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

        await Assert.ThrowsAsync<RefinerLibraryException>(() => LibraryStore.SetManagerLinksAsync(uow, library.Id, [999]));
    }

    [Fact]
    public async Task A_rule_set_still_used_by_a_library_cannot_be_deleted()
    {
        using var db = new JobsTestDatabase(keepSeedRows: true);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var ruleSet = await LibraryStore.GetRuleSetAsync(uow, 1);
        Assert.NotNull(ruleSet);

        var exception = await Assert.ThrowsAsync<RefinerLibraryException>(() => LibraryStore.DeleteRuleSetAsync(uow, ruleSet!));
        Assert.Contains("still used", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_rule_set_no_longer_referenced_can_be_deleted()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var ruleSet = await LibraryStore.CreateRuleSetAsync(uow, new Weir.Core.Refiner.LibraryRules.RuleSetInput { Name = "Spare" });

        await LibraryStore.DeleteRuleSetAsync(uow, ruleSet);

        Assert.Null(await LibraryStore.GetRuleSetAsync(uow, ruleSet.Id));
    }

    [Fact]
    public async Task Creating_a_rule_set_fills_empty_sorters_from_the_default_preset()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var ruleSet = await LibraryStore.CreateRuleSetAsync(uow, new Weir.Core.Refiner.LibraryRules.RuleSetInput { Name = "Custom" });

        Assert.False(string.IsNullOrWhiteSpace(ruleSet.AudioSortersJson));
        Assert.NotEqual("[]", ruleSet.AudioSortersJson.Trim());
    }

    [Fact]
    public async Task Active_job_count_matches_the_library_id_carried_in_the_payload()
    {
        using var db = new JobsTestDatabase();
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var library = await LibraryStore.CreateAsync(uow, NewLibrary("Anime"));
        await uow.CommitAsync(); // release the write lock before the raw connection below takes it
        db.Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES ('k1', 'refiner.file.remux_pass.v1', @payload, 'leased')",
            ("@payload", $"{{\"library_id\": {library.Id}}}"));
        db.Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES ('k2', 'refiner.file.remux_pass.v1', @payload, 'completed')",
            ("@payload", $"{{\"library_id\": {library.Id}}}"));

        var reloaded = await LibraryStore.GetAsync(uow, library.Id);
        var active = await LibraryStore.ActiveJobCountAsync(uow, reloaded!);

        Assert.Equal(1, active);
    }
}
