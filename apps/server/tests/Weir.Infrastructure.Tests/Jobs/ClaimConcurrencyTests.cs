using System.Collections.Concurrent;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// No double claim under parallel workers, and correct recovery of expired leases, on a real SQLite file
/// with every worker on its own connection pool (as separate processes would be).
/// </summary>
public sealed class ClaimConcurrencyTests : IDisposable
{
    private const string Kind = "refiner.test.parallel.v1";
    private static readonly DateTimeOffset T0 = JobsTestDatabase.T0;
    private readonly JobsTestDatabase _db = new();

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task Parallel_claims_never_lease_the_same_row_twice()
    {
        const int jobs = 300;
        const int workers = 24;
        await EnqueueManyAsync(jobs);
        var claims = new ConcurrentBag<(long Id, string Owner)>();
        using var barrier = new Barrier(workers);

        await Task.WhenAll(Enumerable.Range(0, workers).Select(index => Task.Run(async () =>
        {
            var store = SeparateStore();
            barrier.SignalAndWait();
            while (await store.ClaimNextAsync($"w{index}", T0.AddHours(1), T0) is { } job)
            {
                claims.Add((job.Id, job.LeaseOwner!));
            }
        })));

        Assert.Equal(jobs, claims.Count);
        Assert.Equal(jobs, claims.Select(c => c.Id).Distinct().Count());
        Assert.Equal(jobs, _db.Count("SELECT count(*) FROM refiner_jobs WHERE status = 'leased' AND attempt_count = 1"));
        // The owner recorded on each row is the worker that got it back from the claim.
        var owners = claims.ToDictionary(c => c.Id, c => c.Owner);
        foreach (var row in await _db.Store.ListAsync())
        {
            Assert.Equal(owners[row.Id], row.LeaseOwner);
        }
    }

    [Fact]
    public async Task Parallel_workers_run_every_job_exactly_once()
    {
        const int jobs = 200;
        const int workers = 16;
        await EnqueueManyAsync(jobs);
        var runs = new ConcurrentDictionary<long, int>();
        var running = new ConcurrentDictionary<long, byte>();
        var overlaps = 0;
        var handler = new DelegateHandler(Kind, async context =>
        {
            if (!running.TryAdd(context.Id, 0))
            {
                Interlocked.Increment(ref overlaps);
            }

            runs.AddOrUpdate(context.Id, 1, (_, count) => count + 1);
            await Task.Yield();
            running.TryRemove(context.Id, out _);
        });

        await Task.WhenAll(Enumerable.Range(0, workers).Select(index => Task.Run(async () =>
        {
            var processor = new RefinerJobProcessor(
                SeparateStore(),
                new JobHandlerRegistry([handler]),
                new RecordingActivityWriter(),
                new NoUnhandledJobFailureRecorder(),
                new NoJobNotifications(),
                _db.Clock,
                NullLogger<RefinerJobProcessor>.Instance);
            while (await processor.ProcessOneAsync($"w{index}", 3600, T0) == JobProcessOutcome.Processed)
            {
            }
        })));

        Assert.Equal(0, overlaps);
        Assert.Equal(jobs, runs.Count);
        Assert.All(runs.Values, count => Assert.Equal(1, count));
        Assert.Equal(jobs, _db.Count("SELECT count(*) FROM refiner_jobs WHERE status = 'completed' AND attempt_count = 1"));
    }

    [Fact]
    public async Task An_expired_lease_is_recovered_by_another_worker_and_the_dead_owner_can_no_longer_finish_it()
    {
        var job = await _db.Store.EnqueueOrGetAsync("crash", Kind);
        var dead = SeparateStore();
        var alive = SeparateStore();
        Assert.NotNull(await dead.ClaimNextAsync("dead", T0.AddSeconds(300), T0));

        // Still inside the lease: nobody else may take it.
        Assert.Null(await alive.ClaimNextAsync("alive", T0.AddHours(1), T0.AddSeconds(299)));

        var reclaimed = await alive.ClaimNextAsync("alive", T0.AddHours(1), T0.AddSeconds(301));
        Assert.NotNull(reclaimed);
        Assert.Equal((job.Id, "alive", 2), (reclaimed.Id, reclaimed.LeaseOwner, reclaimed.AttemptCount));

        Assert.False(await dead.CompleteClaimedAsync(job.Id, "dead", T0.AddSeconds(200)));
        Assert.False(await dead.FailClaimedAsync(job.Id, "dead", "late", T0.AddSeconds(200)));
        Assert.False(await dead.FailLeasedAfterCompleteFailureAsync(job.Id, "dead", "late", T0.AddSeconds(200)));
        Assert.True(await alive.CompleteClaimedAsync(job.Id, "alive", T0.AddSeconds(302)));
        Assert.Equal(RefinerJobStatus.Completed, (await _db.Store.GetAsync(job.Id))!.Status);
    }

    [Fact]
    public async Task Parallel_reclaims_of_expired_leases_take_each_row_once()
    {
        const int jobs = 120;
        const int workers = 16;
        await EnqueueManyAsync(jobs);
        while (await _db.Store.ClaimNextAsync("crashed", T0.AddSeconds(1), T0) is not null)
        {
        }

        var claims = new ConcurrentBag<long>();
        using var barrier = new Barrier(workers);
        await Task.WhenAll(Enumerable.Range(0, workers).Select(index => Task.Run(async () =>
        {
            var store = SeparateStore();
            barrier.SignalAndWait();
            while (await store.ClaimNextAsync($"w{index}", T0.AddHours(1), T0.AddMinutes(10)) is { } job)
            {
                claims.Add(job.Id);
            }
        })));

        Assert.Equal(jobs, claims.Count);
        Assert.Equal(jobs, claims.Distinct().Count());
        Assert.Equal(jobs, _db.Count("SELECT count(*) FROM refiner_jobs WHERE attempt_count = 2 AND lease_owner <> 'crashed'"));
    }

    [Fact]
    public async Task Concurrent_enqueue_and_claim_lose_nothing()
    {
        const int producers = 6;
        const int perProducer = 40;
        const int consumers = 8;
        var produced = 0;
        var claims = new ConcurrentBag<long>();
        var producing = Enumerable.Range(0, producers).Select(p => Task.Run(async () =>
        {
            var store = SeparateStore();
            for (var i = 0; i < perProducer; i++)
            {
                await store.EnqueueOrGetAsync($"p{p}-{i}", Kind);
                // A duplicate enqueue returns the same row rather than adding one.
                await store.EnqueueOrGetAsync($"p{p}-{i}", Kind);
                Interlocked.Increment(ref produced);
            }
        })).ToArray();
        var consuming = Enumerable.Range(0, consumers).Select(c => Task.Run(async () =>
        {
            var store = SeparateStore();
            var idle = 0;
            while (idle < 20)
            {
                if (await store.ClaimNextAsync($"c{c}", T0.AddHours(1), T0) is { } job)
                {
                    claims.Add(job.Id);
                    idle = 0;
                }
                else if (Volatile.Read(ref produced) == producers * perProducer)
                {
                    idle++;
                }
                else
                {
                    await Task.Delay(1);
                }
            }
        })).ToArray();

        await Task.WhenAll(producing);
        await Task.WhenAll(consuming);

        Assert.Equal(producers * perProducer, _db.Count("SELECT count(*) FROM refiner_jobs"));
        Assert.Equal(producers * perProducer, claims.Count);
        Assert.Equal(producers * perProducer, claims.Distinct().Count());
    }

    private RefinerJobStore SeparateStore() => new(new SqliteDatabase(_db.DbPath), _db.Clock);

    private async Task EnqueueManyAsync(int count)
    {
        await _db.Store.InTransactionAsync((connection, transaction) =>
        {
            for (var i = 0; i < count; i++)
            {
                _db.Store.EnqueueOrGet(connection, transaction, $"job-{i}", Kind, null, 3, 0, 0);
            }

            return count;
        });
    }
}
