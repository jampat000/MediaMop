using System.Text.Json;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Ports of the leasing assertions in <c>test_refiner_schedules_and_pause.py</c>: the schedule and the pause
/// gate leasing, not only enqueue (#337), and a running job finishes.
/// </summary>
public sealed class AdmissionClaimTests : IDisposable
{
    private const string Remux = "refiner.file.remux_pass.v1";
    private const string Scan = "refiner.watched_folder.remux_scan_dispatch.v1";
    private static readonly DateTimeOffset Now = new(2026, 8, 26, 14, 0, 0, TimeSpan.Zero);
    private static readonly string Never = new('0', ScheduleGrid.SlotsPerWeek);
    private readonly JobsTestDatabase _db = new();

    public AdmissionClaimTests()
    {
        _db.SeedSuiteSettings();
    }

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task A_job_is_not_leased_for_a_library_outside_its_window()
    {
        var library = _db.AddLibrary(scheduleGrid: Never);
        await QueueAsync(Remux, library);

        var admission = await EvaluateAsync(Now);

        Assert.Contains(library, admission.BlockedLibraryIds);
        Assert.Null(await ClaimAsync(admission));
        Assert.Equal(RefinerJobStatus.Pending, (string?)_db.Scalar("SELECT status FROM refiner_jobs"));
    }

    [Fact]
    public async Task A_job_is_leased_once_the_window_opens()
    {
        var slots = Never.ToCharArray();
        for (var slot = 0; slot < ScheduleGrid.SlotsPerDay; slot++)
        {
            slots[(2 * ScheduleGrid.SlotsPerDay) + slot] = '1';
        }

        var library = _db.AddLibrary(scheduleGrid: new string(slots));
        await QueueAsync(Remux, library);

        var claimed = await ClaimAsync(await EvaluateAsync(Now));

        Assert.NotNull(claimed);
        Assert.Equal(RefinerJobStatus.Leased, claimed.Status);
    }

    [Fact]
    public async Task One_library_being_shut_does_not_block_another()
    {
        var shut = _db.AddLibrary(name: "Movies", scheduleGrid: Never);
        var open = _db.AddLibrary(name: "TV");
        await QueueAsync(Remux, shut, "shut");
        await QueueAsync(Remux, open, "open");

        var claimed = await ClaimAsync(await EvaluateAsync(Now));

        Assert.NotNull(claimed);
        using var payload = JsonDocument.Parse(claimed.PayloadJson!);
        Assert.Equal(open, payload.RootElement.GetProperty("library_id").GetInt64());
    }

    [Fact]
    public async Task A_job_naming_no_library_is_still_claimable()
    {
        var shut = _db.AddLibrary(scheduleGrid: Never);
        await QueueAsync(Remux, shut, "shut");
        await QueueAsync(Scan, null, "nolib");

        var claimed = await ClaimAsync(await EvaluateAsync(Now));

        Assert.NotNull(claimed);
        Assert.Equal(Scan, claimed.JobKind);
    }

    [Fact]
    public async Task A_running_job_finishes_when_the_window_closes()
    {
        var library = _db.AddLibrary();
        await QueueAsync(Remux, library);
        Assert.NotNull(await ClaimAsync(await EvaluateAsync(Now)));

        _db.Execute("UPDATE refiner_libraries SET schedule_grid = @grid", ("@grid", Never));
        var admission = await EvaluateAsync(Now);

        Assert.Contains(library, admission.BlockedLibraryIds);
        var still = (await _db.Store.ListAsync()).Single();
        Assert.Equal(RefinerJobStatus.Leased, still.Status);
        Assert.Equal("w1", still.LeaseOwner);
        Assert.Null(await ClaimAsync(admission, "w2"));
    }

    [Fact]
    public async Task A_disabled_library_blocks_leasing_too()
    {
        var library = _db.AddLibrary(enabled: false);
        await QueueAsync(Remux, library);

        Assert.Null(await ClaimAsync(await EvaluateAsync(Now)));
    }

    [Fact]
    public async Task A_library_at_its_own_concurrency_cap_waits()
    {
        var library = _db.AddLibrary(maxConcurrentFiles: 1);
        await QueueAsync(Remux, library, "one");
        await QueueAsync(Remux, library, "two");

        Assert.NotNull(await ClaimAsync(await EvaluateAsync(Now)));
        Assert.Null(await ClaimAsync(await EvaluateAsync(Now), "w2"));
    }

    [Fact]
    public async Task A_pause_stops_processing_but_scanning_continues_by_default()
    {
        var library = _db.AddLibrary();
        await QueueAsync(Remux, library, "remux");
        await QueueAsync(Scan, library, "scan");
        _db.Pause(scanWhilePaused: true);

        var claimed = await ClaimAsync(await EvaluateAsync(Now));

        Assert.NotNull(claimed);
        Assert.Equal(Scan, claimed.JobKind);
        Assert.Null(await ClaimAsync(await EvaluateAsync(Now), "w2"));
    }

    [Fact]
    public async Task Scan_while_paused_off_stops_everything()
    {
        var library = _db.AddLibrary();
        await QueueAsync(Scan, library, "scan");
        _db.Pause(scanWhilePaused: false);

        Assert.Null(await ClaimAsync(await EvaluateAsync(Now)));
    }

    [Fact]
    public async Task Work_resumes_once_the_pause_expires()
    {
        var library = _db.AddLibrary();
        await QueueAsync(Remux, library);
        _db.Pause(scanWhilePaused: true, until: Now.AddHours(1));

        Assert.Null(await ClaimAsync(await EvaluateAsync(Now)));

        var later = Now.AddHours(2);
        var admission = await EvaluateAsync(later);
        Assert.False(admission.Pause.Paused);
        var claimed = await _db.Store.ClaimNextAsync("w1", later.AddHours(1), later, admission);

        Assert.NotNull(claimed);
        Assert.Equal(Remux, claimed.JobKind);
    }

    [Fact]
    public async Task No_admission_claims_exactly_as_before()
    {
        var library = _db.AddLibrary(scheduleGrid: Never);
        await QueueAsync(Remux, library);
        _db.Pause(scanWhilePaused: false);

        Assert.NotNull(await ClaimAsync(null));
    }

    [Fact]
    public async Task A_job_costing_more_than_the_budget_left_waits_and_a_free_job_still_runs()
    {
        _db.Execute("INSERT INTO refiner_operator_settings (id, runner_capacity) VALUES (1, 2)");
        await _db.Store.EnqueueOrGetAsync("big-1", Remux, runnerCost: 2);
        await _db.Store.EnqueueOrGetAsync("big-2", Remux, runnerCost: 1);
        await _db.Store.EnqueueOrGetAsync("free", Remux, runnerCost: 0);

        Assert.Equal("big-1", (await ClaimAsync(await EvaluateAsync(Now)))!.DedupeKey);
        var full = await EvaluateAsync(Now);
        Assert.Equal(0, full.AvailableUnits);
        Assert.Equal("free", (await ClaimAsync(full, "w2"))!.DedupeKey);
        Assert.Null(await ClaimAsync(await EvaluateAsync(Now), "w3"));
    }

    [Fact]
    public async Task The_worker_claim_reads_admission_in_the_same_transaction()
    {
        var library = _db.AddLibrary(scheduleGrid: Never);
        await QueueAsync(Remux, library);

        Assert.Null(await _db.Store.ClaimNextAdmittedAsync("w", Now.AddHours(1), Now, kinds: null));
        _db.Execute("UPDATE refiner_libraries SET schedule_grid = ''");
        Assert.NotNull(await _db.Store.ClaimNextAdmittedAsync("w", Now.AddHours(1), Now, kinds: null));
    }

    [Fact]
    public async Task Detection_prefix_matching_uses_like_as_python_does()
    {
        // LIKE ignores ASCII case and treats '_' as a wildcard; Python's pause filter has the same reach.
        _db.InsertRawJob("odd", "refiner.watched-folder.remux-scan-dispatch.v1");
        _db.Pause(scanWhilePaused: true);

        Assert.NotNull(await ClaimAsync(await EvaluateAsync(Now)));
    }

    private Task<WorkAdmission> EvaluateAsync(DateTimeOffset now) =>
        _db.Store.InTransactionAsync((connection, transaction) => WorkAdmissionReader.Evaluate(connection, transaction, now));

    private Task<RefinerJob?> ClaimAsync(WorkAdmission? admission, string owner = "w1") =>
        _db.Store.ClaimNextAsync(owner, Now.AddHours(1), Now, admission);

    private Task<RefinerJob> QueueAsync(string kind, long? libraryId, string key = "k")
    {
        var payload = libraryId is { } id
            ? $"{{\"media_scope\": \"movie\", \"library_id\": {id}}}"
            : "{\"media_scope\": \"movie\"}";
        return _db.Store.EnqueueOrGetAsync($"{kind}:{key}", kind, payload);
    }
}
