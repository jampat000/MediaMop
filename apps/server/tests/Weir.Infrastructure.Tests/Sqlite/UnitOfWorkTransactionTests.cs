using Microsoft.Data.Sqlite;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Jobs;

namespace Weir.Infrastructure.Tests.Sqlite;

/// <summary>
/// #586: a unit of work whose transaction opens with a read and writes afterwards. In WAL mode a
/// deferred <c>BEGIN</c> pins the connection's read snapshot at that first read; if any other
/// connection commits a real write before the upgrade to a writer, SQLite refuses it with
/// <c>SQLITE_BUSY_SNAPSHOT</c> — an error <c>busy_timeout</c> cannot resolve, because waiting never
/// makes a stale snapshot current again.
/// </summary>
public sealed class UnitOfWorkTransactionTests
{
    private const string InsertJob =
        "INSERT INTO jobs (dedupe_key, job_kind, status, max_attempts) VALUES (@dedupe, 'processing.remux_pass', 'pending', 3)";

    /// <summary>
    /// A write from another connection that barely waits: <c>PRAGMA busy_timeout=0</c> stops SQLite
    /// waiting on the lock, and a one second <c>CommandTimeout</c> stops Microsoft.Data.Sqlite re-running
    /// the statement for the thirty seconds it would otherwise allow. So this answers in about a second at
    /// worst, either way, and the test needs no second thread and no sleep to say whether the write lock
    /// was held. Not <c>CommandTimeout = 0</c>: that is ADO.NET for "no limit", which here means retrying
    /// a busy database forever.
    /// </summary>
    private static bool ForeignWriteSucceeds(JobsTestDatabase db, string dedupeKey)
    {
        using var connection = db.Database.Open();
        using var noWait = connection.CreateCommand();
        noWait.CommandText = "PRAGMA busy_timeout=0";
        noWait.ExecuteNonQuery();
        using var command = connection.CreateCommand();
        command.CommandTimeout = 1;
        command.CommandText = InsertJob;
        command.Parameters.AddWithValue("@dedupe", dedupeKey);
        try
        {
            command.ExecuteNonQuery();
            return true;
        }
        catch (SqliteException exception) when (exception.SqliteErrorCode is 5 or 6)
        {
            return false;
        }
    }

    [Fact]
    public async Task A_units_transaction_holds_the_write_lock_from_the_moment_it_begins()
    {
        using var db = new JobsTestDatabase();
        var uow = await UnitOfWork.OpenAsync(db.Database);
        await using (uow.ConfigureAwait(false))
        {
            Assert.True(ForeignWriteSucceeds(db, "before-the-transaction"), "no transaction is open yet");

            // The job queue's enqueue takes the unit's transaction and reads before it inserts.
            uow.WriteTransaction();
            Assert.Equal(1, await uow.CountAsync("SELECT count(*) FROM jobs"));

            // Nothing may commit between that read and the write it is about to become.
            Assert.False(ForeignWriteSucceeds(db, "during-the-transaction"), "the write lock must already be held");
            await uow.CommitAsync();
        }
    }

    [Fact]
    public async Task A_read_then_write_unit_survives_another_writer_arriving_in_between()
    {
        using var db = new JobsTestDatabase();
        var uow = await UnitOfWork.OpenAsync(db.Database);
        await using (uow.ConfigureAwait(false))
        {
            // The endpoint's own reads, before it has written anything (authorisation, lookups).
            await uow.CountAsync("SELECT count(*) FROM jobs");

            // The enqueue's own shape: take the transaction, look the dedupe key up, then insert. Another
            // writer arrives in between. Whether it gets in (deferred) or is turned away (immediate) is
            // not what is under test and is deliberately not asserted here — what matters is that this
            // unit of work still completes either way.
            uow.WriteTransaction();
            await uow.CountAsync("SELECT count(*) FROM jobs WHERE dedupe_key = 'mine'");
            ForeignWriteSucceeds(db, "someone-else");

            await uow.ExecuteAsync(InsertJob, ("@dedupe", "mine"));
            await uow.CommitAsync();
        }

        Assert.Equal(1, db.Count("SELECT count(*) FROM jobs WHERE dedupe_key = 'mine'"));
    }

    /// <summary>
    /// Which reads matter, exactly. The issue first read this as the endpoint's own authorisation read
    /// pinning the snapshot; it does not. Reads taken before anything has written run in autocommit, each
    /// one its own short read transaction, so they leave nothing pinned for a later write to trip over.
    /// Only a read issued once the transaction is open can strand it — which is why the fix belongs at
    /// <c>BEGIN</c> and not at the endpoint.
    /// </summary>
    [Fact]
    public async Task Reads_before_the_transaction_leave_nothing_for_a_later_write_to_trip_over()
    {
        using var db = new JobsTestDatabase();
        var uow = await UnitOfWork.OpenAsync(db.Database);
        await using (uow.ConfigureAwait(false))
        {
            await uow.CountAsync("SELECT count(*) FROM jobs");
            await uow.CountAsync("SELECT count(*) FROM libraries");
            Assert.True(ForeignWriteSucceeds(db, "between-the-reads-and-the-write"));

            await uow.ExecuteAsync(InsertJob, ("@dedupe", "mine"));
            await uow.CommitAsync();
        }

        Assert.Equal(1, db.Count("SELECT count(*) FROM jobs WHERE dedupe_key = 'mine'"));
    }

    [Fact]
    public async Task A_unit_that_only_reads_never_takes_the_write_lock()
    {
        using var db = new JobsTestDatabase();
        var uow = await UnitOfWork.OpenAsync(db.Database);
        await using (uow.ConfigureAwait(false))
        {
            await uow.CountAsync("SELECT count(*) FROM jobs");
            await uow.CountAsync("SELECT count(*) FROM libraries");
            Assert.False(uow.InTransaction);
            Assert.True(ForeignWriteSucceeds(db, "unblocked"), "reads must not serialise against writers");
        }
    }
}
