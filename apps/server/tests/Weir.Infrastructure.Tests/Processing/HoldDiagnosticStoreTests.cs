using Weir.Core.Processing;
using Weir.Core.Security;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.MediaManagers;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.Processing;

/// <summary>
/// Closes #522's "why held" diagnostic gap: it must ask every linked manager's live queue and apply the
/// same domain rules as the watched-folder scan, not report every library as consulted-but-silent (port of
/// the manager-signal scenarios from <c>test_processing_candidate_gate_evaluate.py</c>), driven through
/// <see cref="HoldDiagnosticStore.EvaluateAsync"/> with a fake Radarr/Sonarr behind
/// <see cref="FakeManagerHttp"/>.
/// </summary>
public sealed class HoldDiagnosticStoreTests
{
    private static async Task<(StoreFixture Store, FakeManagerHttp Http, MediaManagerConnectionService Connections)> BuildAsync()
    {
        var store = new StoreFixture(("WEIR_CREDENTIALS_SECRET", "hold-diagnostic-tests-credentials-secret"));
        var cipher = new CredentialCipher(store.Options.CredentialsSecret, store.Options.SessionSecret, store.Options.PreviousCredentialsSecrets, store.Clock);
        var http = new FakeManagerHttp();
        var ports = new HttpMediaManagerPorts(http);
        var connections = new MediaManagerConnectionService(store.Options, cipher, ports);
        return (store, http, connections);
    }

    private static void RouteQueue(FakeManagerHttp http, string recordsJson) =>
        http.Json(HttpMethod.Get, "/api/v3/queue", "{\"records\":" + recordsJson + "}");

    private static async Task<(long LibraryId, long FileId)> SeedFileAsync(StoreFixture store, string relativePath, IReadOnlyList<long> managerConnectionIds)
    {
        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var library = await LibraryStore.CreateAsync(uow, new ProcessingLibraryInput
        {
            Name = "Movies " + Guid.NewGuid().ToString("N")[..8],
            MediaType = ProcessingMediaScopes.Movie,
            WatchedFolder = store.Home.Join("watch"),
            OutputFolder = store.Home.Join("out"),
            ManagerConnectionIds = managerConnectionIds,
        });
        var fileId = await FileStateStore.RecordFileStateAsync(
            uow, library.Id, relativePath,
            new FileStateVerdict(ProcessingFileStatuses.OnHold, "held for the test"),
            sizeBytes: 100, sizeChangedAt: store.Clock.GetUtcNow(), seenAt: store.Clock.GetUtcNow());
        await uow.CommitAsync();
        return (library.Id, fileId);
    }

    [Fact]
    public async Task Wait_upstream_when_the_linked_manager_still_lists_the_file()
    {
        var (store, http, connections) = await BuildAsync();
        using var _ = store;
        var connectionId = await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "radarr", "4K", "http://radarr.local", "key"));
        var (libraryId, fileId) = await SeedFileAsync(store, "Solaris (1972)/Solaris.mkv", [connectionId]);
        RouteQueue(http, "[{\"status\":\"downloading\",\"outputPath\":\"Solaris (1972)/Solaris.mkv\",\"movie\":{\"title\":\"Solaris\",\"year\":1972}}]");

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.GetAsync(uow, fileId);
        var library = await LibraryStore.GetAsync(uow, libraryId);
        var outcome = await HoldDiagnosticStore.EvaluateAsync(uow, file!, library!, connections);

        Assert.Equal(CandidateGateVerdict.WaitUpstream, outcome.Verdict);
        Assert.True(outcome.Owned);
        Assert.True(outcome.BlockedUpstream);
        Assert.Equal("Radarr (4K)", outcome.BlockedByConnection);
        Assert.Contains("Radarr (4K) is still importing this file", outcome.Reasons[0], StringComparison.Ordinal);
    }

    [Fact]
    public async Task Not_held_when_the_linked_manager_reports_an_empty_queue()
    {
        var (store, http, connections) = await BuildAsync();
        using var _ = store;
        var connectionId = await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "radarr", "Main", "http://radarr.local", "key"));
        var (libraryId, fileId) = await SeedFileAsync(store, "Clear (2000)/Clear.mkv", [connectionId]);
        RouteQueue(http, "[]");

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.GetAsync(uow, fileId);
        var library = await LibraryStore.GetAsync(uow, libraryId);
        var outcome = await HoldDiagnosticStore.EvaluateAsync(uow, file!, library!, connections);

        Assert.Equal(CandidateGateVerdict.NotHeld, outcome.Verdict);
        Assert.False(outcome.Owned);
        Assert.False(outcome.BlockedUpstream);
        Assert.Equal(1, outcome.ManagersReporting);
    }

    [Fact]
    public async Task No_upstream_signal_when_no_manager_is_linked()
    {
        var (store, _, connections) = await BuildAsync();
        using var _ = store;
        var (libraryId, fileId) = await SeedFileAsync(store, "Unlinked (2000)/Unlinked.mkv", []);

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.GetAsync(uow, fileId);
        var library = await LibraryStore.GetAsync(uow, libraryId);
        var outcome = await HoldDiagnosticStore.EvaluateAsync(uow, file!, library!, connections);

        Assert.Equal(CandidateGateVerdict.NoUpstreamSignal, outcome.Verdict);
        Assert.Equal(0, outcome.ManagersConsulted);
        Assert.Contains("No media manager is connected for Movies", outcome.Reasons[0], StringComparison.Ordinal);
    }

    [Fact]
    public async Task No_upstream_signal_when_the_linked_manager_is_unreachable()
    {
        var (store, http, connections) = await BuildAsync();
        using var _ = store;
        var connectionId = await store.WithUnitOfWork(uow => connections.CreateAsync(uow, "radarr", "Main", "http://radarr.local", "key"));
        var (libraryId, fileId) = await SeedFileAsync(store, "Stalled (2000)/Stalled.mkv", [connectionId]);
        http.Throw(HttpMethod.Get, "/api/v3/queue", new HttpRequestException("Connection refused."));

        await using var uow = await UnitOfWork.OpenAsync(store.Database);
        var file = await FileStateStore.GetAsync(uow, fileId);
        var library = await LibraryStore.GetAsync(uow, libraryId);
        var outcome = await HoldDiagnosticStore.EvaluateAsync(uow, file!, library!, connections);

        Assert.Equal(CandidateGateVerdict.NoUpstreamSignal, outcome.Verdict);
        Assert.Equal(0, outcome.ManagersReporting);
        Assert.Equal(["Radarr (Main)"], outcome.ManagersWithoutQueueSignal);
    }
}
