using System.Globalization;
using System.Text.Json;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Python and .NET share one queue: rows enqueued by one are claimed, completed, failed and recovered by
/// the other, with the same claim text comparisons and lease checks.
/// </summary>
public sealed class CrossBackendTests : IDisposable
{
    private const string Kind = "refiner.test.cross.v1";
    private static readonly DateTimeOffset T0 = new(2026, 4, 10, 12, 0, 0, 123_456 / 1000, TimeSpan.Zero);
    private readonly JobsTestDatabase _db = new(keepSeedRows: true);

    public void Dispose() => _db.Dispose();

    [PythonFact]
    public async Task Python_enqueues_and_dotnet_claims_and_completes()
    {
        var results = await PythonAsync(
            new { op = "enqueue", key = "py-1", kind = Kind, payload = "{\"library_id\": 1}" },
            new { op = "enqueue", key = "py-2", kind = Kind, max_attempts = 5 },
            new { op = "enqueue", key = "py-1", kind = Kind });
        Assert.Equal(results[0].GetProperty("id").GetInt64(), results[2].GetProperty("id").GetInt64());

        var first = await _db.Store.ClaimNextAsync("dotnet", T0.AddHours(1), T0);
        var second = await _db.Store.ClaimNextAsync("dotnet", T0.AddHours(1), T0);
        Assert.Equal((1, 3), (first!.AttemptCount, first.MaxAttempts));
        Assert.Equal(5, second!.MaxAttempts);
        Assert.True(await _db.Store.CompleteClaimedAsync(first.Id, "dotnet", T0));
        Assert.True(await _db.Store.FailClaimedAsync(second.Id, "dotnet", "boom", T0));

        var read = await PythonAsync(
            new { op = "orm_get", id = first.Id },
            new { op = "orm_get", id = second.Id },
            new { op = "claim", owner = "python", lease_seconds = 60, now = Iso(T0.AddSeconds(29)) },
            new { op = "claim", owner = "python", lease_seconds = 60, now = Iso(T0.AddSeconds(31)) });
        Assert.Equal("completed", read[0].GetProperty("status").GetString());
        Assert.Equal("pending", read[1].GetProperty("status").GetString());
        Assert.Equal("2026-04-10T12:00:30.123000", read[1].GetProperty("not_before").GetString());
        Assert.Equal(JsonValueKind.Null, read[2].ValueKind);
        Assert.Equal(second.Id, read[3].GetProperty("id").GetInt64());
        Assert.Equal(2, read[3].GetProperty("attempt_count").GetInt32());
    }

    [PythonFact]
    public async Task Dotnet_enqueues_and_python_claims_and_completes()
    {
        var job = await _db.Store.EnqueueOrGetAsync("net-1", Kind, "{\"x\":1}");
        var duplicate = await PythonAsync(new { op = "enqueue", key = "net-1", kind = Kind });
        Assert.Equal(job.Id, duplicate[0].GetProperty("id").GetInt64());

        var claimed = await PythonAsync(
            new { op = "claim", owner = "python", lease_seconds = 300, now = Iso(T0) },
            new { op = "orm_get", id = job.Id },
            new { op = "claim", owner = "python-2", lease_seconds = 300, now = Iso(T0) });
        Assert.Equal(job.Id, claimed[0].GetProperty("id").GetInt64());
        Assert.Equal(JsonValueKind.Null, claimed[2].ValueKind);

        // .NET reads the lease Python wrote and refuses to take it while it is live.
        Assert.Null(await _db.Store.ClaimNextAsync("dotnet", T0.AddHours(1), T0.AddSeconds(299)));
        var row = (await _db.Store.GetAsync(job.Id))!;
        Assert.Equal(("python", T0.AddSeconds(300)), (row.LeaseOwner, row.LeaseExpiresAt));

        var completed = await PythonAsync(
            new { op = "complete", id = job.Id, owner = "python", now = Iso(T0.AddSeconds(10)) },
            new { op = "get", id = job.Id });
        Assert.True(completed[0].GetProperty("ok").GetBoolean());
        Assert.Equal(RefinerJobStatus.Completed, (await _db.Store.GetAsync(job.Id))!.Status);
    }

    [PythonFact]
    public async Task A_lease_dotnet_wrote_is_checked_by_python_and_its_expiry_lets_python_reclaim()
    {
        var job = await _db.Store.EnqueueOrGetAsync("lease", Kind);
        Assert.NotNull(await _db.Store.ClaimNextAsync("dotnet-dead", T0.AddSeconds(60), T0));
        Assert.Equal("2026-04-10 12:01:00.123000+00:00", _db.Scalar("SELECT lease_expires_at FROM refiner_jobs"));

        var results = await PythonAsync(
            new { op = "complete", id = job.Id, owner = "python", now = Iso(T0) },
            new { op = "claim", owner = "python", lease_seconds = 300, now = Iso(T0.AddSeconds(59)) },
            new { op = "claim", owner = "python", lease_seconds = 300, now = Iso(T0.AddSeconds(61)) },
            new { op = "orm_get", id = job.Id });

        Assert.False(results[0].GetProperty("ok").GetBoolean());
        Assert.Equal(JsonValueKind.Null, results[1].ValueKind);
        Assert.Equal(2, results[2].GetProperty("attempt_count").GetInt32());
        Assert.Equal("2026-04-10T12:06:01.123000+00:00", results[3].GetProperty("lease_expires_at").GetString());
        Assert.False(await _db.Store.CompleteClaimedAsync(job.Id, "dotnet-dead", T0));
        Assert.True(await _db.Store.CompleteClaimedAsync(job.Id, "python", T0.AddSeconds(100)));
    }

    [PythonFact]
    public async Task A_python_worker_that_died_mid_job_is_recovered_by_dotnet_and_the_reverse()
    {
        var jobs = await PythonAsync(
            new { op = "enqueue", key = "a", kind = Kind },
            new { op = "enqueue", key = "b", kind = Kind, max_attempts = 1 },
            new { op = "claim", owner = "python-dead", lease_seconds = 3600, now = Iso(T0) },
            new { op = "claim", owner = "python-dead", lease_seconds = 3600, now = Iso(T0) });
        Assert.Equal(2, jobs.Length - 2);

        var report = await StartupRecovery.RunAsync(_db.Store, _db.Home, T0.AddMinutes(1), Microsoft.Extensions.Logging.Abstractions.NullLogger.Instance);
        Assert.Equal(new StartupJobRecoveryResult(1, 1), report.Jobs);

        Assert.NotNull(await _db.Store.ClaimNextAsync("dotnet-dead", T0.AddHours(1), T0.AddMinutes(2)));
        var recovered = await PythonAsync(
            new { op = "recover", now = Iso(T0.AddMinutes(3)) },
            new { op = "get", id = 1 },
            new { op = "get", id = 2 });
        Assert.Equal(1, recovered[0].GetProperty("refiner_requeued").GetInt32());
        Assert.Equal("pending", recovered[1].GetProperty("status").GetString());
        Assert.Equal("failed", recovered[2].GetProperty("status").GetString());
        Assert.Equal(
            "Refiner job was interrupted by a Weir restart after its final attempt. Recovered at 2026-04-10T12:01:00.123000+00:00 and marked failed so the operator can inspect it.",
            recovered[2].GetProperty("last_error").GetString());
    }

    [PythonFact]
    public async Task Both_workers_store_the_same_failure_wording()
    {
        await _db.Store.EnqueueOrGetAsync("py-fail", "refiner.test.python_fail.v1", maxAttempts: 2);
        await _db.Store.EnqueueOrGetAsync("net-fail", "refiner.test.dotnet_fail.v1", maxAttempts: 2);

        var processed = await PythonAsync(new { op = "process", owner = "python", kind = "refiner.test.python_fail.v1", now = Iso(T0), @raise = "boom" });
        Assert.Equal("processed", processed[0].GetProperty("outcome").GetString());
        var processor = _db.Processor([new DelegateHandler("refiner.test.dotnet_fail.v1", _ => throw new AlreadyRecordedFailureException("boom"))]);
        Assert.Equal(JobProcessOutcome.Processed, await processor.ProcessOneAsync("dotnet", now: T0));

        var python = (await _db.Store.ListAsync()).Single(j => j.DedupeKey == "py-fail");
        var dotnet = (await _db.Store.ListAsync()).Single(j => j.DedupeKey == "net-fail");
        Assert.Equal(
            "Refiner job failed: The job hit an unexpected error. Weir will try this job again shortly. Technical detail: RuntimeError: boom",
            python.LastError);
        Assert.Equal(python.LastError!.Replace("RuntimeError", "AlreadyRecordedFailure", StringComparison.Ordinal), dotnet.LastError);
        Assert.Equal(python.NotBefore, dotnet.NotBefore);
        Assert.Equal((string?)_db.Scalar("SELECT not_before FROM refiner_jobs WHERE dedupe_key = 'py-fail'"), (string?)_db.Scalar("SELECT not_before FROM refiner_jobs WHERE dedupe_key = 'net-fail'"));
    }

    [PythonFact]
    public async Task A_pause_python_saved_gates_the_dotnet_claim_and_both_agree_on_admission()
    {
        await _db.Store.EnqueueOrGetAsync("remux", "refiner.file.remux_pass.v1");
        var results = await PythonAsync(
            new { op = "pause", scan_while_paused = false, until = Iso(T0.AddHours(1)) },
            new { op = "admission", now = Iso(T0) },
            new { op = "admission", now = Iso(T0.AddHours(2)) });
        Assert.True(results[1].GetProperty("paused").GetBoolean());
        Assert.False(results[2].GetProperty("paused").GetBoolean());

        var paused = await _db.Store.InTransactionAsync((c, t) => WorkAdmissionReader.Evaluate(c, t, T0));
        var resumed = await _db.Store.InTransactionAsync((c, t) => WorkAdmissionReader.Evaluate(c, t, T0.AddHours(2)));
        Assert.True(paused.Pause.Paused);
        Assert.False(resumed.Pause.Paused);
        Assert.Equal(results[1].GetProperty("available").GetInt32(), paused.AvailableUnits);
        Assert.Equal(results[1].GetProperty("blocked").EnumerateArray().Select(e => e.GetInt64()), paused.BlockedLibraryIds.Order());
        Assert.Null(await _db.Store.ClaimNextAdmittedAsync("dotnet", T0.AddHours(1), T0, kinds: null));
        Assert.NotNull(await _db.Store.ClaimNextAdmittedAsync("dotnet", T0.AddHours(3), T0.AddHours(2), kinds: null));
    }

    private Task<JsonElement[]> PythonAsync(params object[] ops) => PythonBackend.RunAsync(_db.DbPath, _db.Home, ops);

    private static string Iso(DateTimeOffset value) => value.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffffzzz", CultureInfo.InvariantCulture);
}
