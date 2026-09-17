using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Tests.Jobs;

namespace Weir.Infrastructure.Tests.LibraryMode;

public sealed class RefinerJobSwapJournalTests : IDisposable
{
    private readonly JobsTestDatabase _db = new();
    private readonly RefinerJobSwapJournal _journal;

    public RefinerJobSwapJournalTests()
    {
        _journal = new RefinerJobSwapJournal(_db.Database);
    }

    public void Dispose() => _db.Dispose();

    private long Job(string dedupe, string? payload, string status = "leased")
    {
        _db.Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES ($key, 'refiner.library.clean.v1', $payload, $status)",
            ("$key", dedupe),
            ("$payload", payload),
            ("$status", status));
        return (long)_db.Scalar("SELECT id FROM refiner_jobs WHERE dedupe_key = $key", ("$key", dedupe))!;
    }

    private string? PayloadOf(long id) => _db.Scalar("SELECT payload_json FROM refiner_jobs WHERE id = $id", ("$id", id)) as string;

    [Fact]
    public async Task Each_state_is_written_onto_the_job_payload_keeping_every_other_key()
    {
        var id = Job("a", "{\"library_id\": 3, \"trigger\": \"library\"}");

        await _journal.RecordAsync(new SwapJournalEntry(id, "/lib/a.mkv", SwapJournalState.Committing));
        Assert.Equal(
            "{\"library_id\":3,\"trigger\":\"library\",\"library_swap\":{\"state\":\"committing\",\"original_path\":\"/lib/a.mkv\"," +
            "\"temp_path\":\"/lib/a.weir-tmp.mkv\",\"backup_path\":\"/lib/a.weir-bak.mkv\"}}",
            PayloadOf(id));

        await _journal.RecordAsync(new SwapJournalEntry(id, "/lib/a.mkv", SwapJournalState.Committed));
        Assert.EndsWith("\"state\":\"committed\",\"original_path\":\"/lib/a.mkv\",\"temp_path\":\"/lib/a.weir-tmp.mkv\",\"backup_path\":\"/lib/a.weir-bak.mkv\"},\"swap_committed\":true}", PayloadOf(id), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_job_without_a_payload_gets_one()
    {
        var id = Job("a", null);

        await _journal.RecordAsync(new SwapJournalEntry(id, "/lib/a.mkv", SwapJournalState.Writing));

        Assert.StartsWith("{\"library_swap\":{\"state\":\"writing\"", PayloadOf(id), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Unfinished_swaps_are_listed_in_job_order_and_everything_else_is_ignored()
    {
        var writing = Job("w", null);
        var committing = Job("c", null, "failed");
        var committed = Job("d", null, "completed");
        var finished = Job("f", null);
        var rolledBack = Job("r", null);
        var recovered = Job("v", null);
        Job("plain", "{\"relative_media_path\": \"a.mkv\"}");
        Job("malformed", "{\"library_swap\": ");
        Job("odd", "{\"library_swap\": {\"state\": \"exploded\", \"original_path\": \"/x.mkv\"}}");
        Job("no-path", "{\"library_swap\": {\"state\": \"writing\"}}");

        await _journal.RecordAsync(new SwapJournalEntry(writing, "/lib/w.mkv", SwapJournalState.Writing));
        await _journal.RecordAsync(new SwapJournalEntry(committing, "/lib/c.mkv", SwapJournalState.Committing));
        await _journal.RecordAsync(new SwapJournalEntry(committed, "/lib/d.mkv", SwapJournalState.Committed));
        await _journal.RecordAsync(new SwapJournalEntry(finished, "/lib/f.mkv", SwapJournalState.Finished));
        await _journal.RecordAsync(new SwapJournalEntry(rolledBack, "/lib/r.mkv", SwapJournalState.RolledBack));
        await _journal.RecordAsync(new SwapJournalEntry(recovered, "/lib/v.mkv", SwapJournalState.Recovered));

        var unfinished = await _journal.ListUnfinishedAsync();

        Assert.Equal(
            [
                new SwapJournalEntry(writing, "/lib/w.mkv", SwapJournalState.Writing),
                new SwapJournalEntry(committing, "/lib/c.mkv", SwapJournalState.Committing),
                new SwapJournalEntry(committed, "/lib/d.mkv", SwapJournalState.Committed),
            ],
            unfinished);
    }

    [Fact]
    public async Task A_missing_job_row_is_an_error()
    {
        var error = await Assert.ThrowsAsync<InvalidOperationException>(
            () => _journal.RecordAsync(new SwapJournalEntry(999, "/lib/a.mkv", SwapJournalState.Writing)));
        Assert.Equal("Job 999 does not exist, so its swap could not be recorded.", error.Message);
    }

    [Theory]
    [InlineData("[1, 2]")]
    [InlineData("{\"broken\": ")]
    public async Task A_payload_that_is_not_an_object_is_never_overwritten(string payload)
    {
        var id = Job("a", payload);

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => _journal.RecordAsync(new SwapJournalEntry(id, "/lib/a.mkv", SwapJournalState.Writing)));

        Assert.Equal(payload, PayloadOf(id));
    }
}
