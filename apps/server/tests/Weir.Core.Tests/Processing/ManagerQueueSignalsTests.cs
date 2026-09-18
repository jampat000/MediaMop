using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Processing;

namespace Weir.Core.Tests.Processing;

/// <summary>Ported from <c>apps/backend/tests/test_processing_queue_adapter.py</c> (movie/TV dialect mapping).</summary>
public sealed class QueueRowMappingTests
{
    private static PyDict Row(string json) => (PyDict)PyJsonParser.Parse(json);

    // --- movie scope (the shape Radarr sends) ------------------------------------

    [Fact]
    public void Movie_active_downloading_row_path_match_owns_and_blocks()
    {
        var row = Row("""{"status":"downloading","outputPath":"D:\\Media\\Film.mkv","movie":{"title":"Solaris","year":1972}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect, candidatePath: "D:/media/film.mkv");
        Assert.True(v.AppliesToFile);
        Assert.False(v.IsImportPending);
        Assert.True(v.IsUpstreamActive);
        Assert.False(v.BlockingSuppressedForImportWait);
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v]));
        Assert.True(ProcessingDomain.ShouldBlockForUpstream([v]));
    }

    [Fact]
    public void Movie_import_pending_row_owns_by_path_suppression_carried()
    {
        var row = Row("""{"status":"importPending","outputPath":"/data/complete/movie.mkv","blockingSuppressedForImportWait":true,"movie":{"title":"Nashville","year":1975}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect, candidatePath: "/data/complete/movie.mkv");
        Assert.True(v.IsImportPending);
        Assert.False(v.IsUpstreamActive);
        Assert.True(v.BlockingSuppressedForImportWait);
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v]));
        Assert.False(ProcessingDomain.ShouldBlockForUpstream([v]));
    }

    [Fact]
    public void Movie_downloading_row_suppressed_does_not_block_but_still_owns()
    {
        var row = Row("""{"status":"downloading","outputPath":"/srv/queue/x.mkv","blocking_suppressed_for_import_wait":true,"movie":{"title":"Stalker","year":1979}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect, candidatePath: "/srv/queue/x.mkv");
        Assert.True(v.IsUpstreamActive);
        Assert.True(v.BlockingSuppressedForImportWait);
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v]));
        Assert.False(ProcessingDomain.ShouldBlockForUpstream([v]));
    }

    [Fact]
    public void Movie_completed_row_owns_via_title_year_anchor_only()
    {
        var row = Row("""{"status":"completed","title":"The.Towering.Inferno.1974.1080p.BluRay.x264","movie":{"title":"The Towering Inferno","year":1974}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect);
        Assert.False(v.AppliesToFile);
        Assert.False(v.IsUpstreamActive);
        Assert.Equal("The Towering Inferno", v.QueueTitle);
        Assert.Equal(1974, v.QueueYear);
        var cand = new FileAnchorCandidate("The Towering Inferno 1974 Remux");
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v], cand));
        Assert.False(ProcessingDomain.ShouldBlockForUpstream([v], cand));
    }

    [Fact]
    public void Movie_applicability_via_movie_id_without_path()
    {
        var row = Row("""{"status":"queued","movieId":42,"movie":{"title":"Heat","year":1995}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect, candidatePath: null, candidateEntityId: 42);
        Assert.True(v.AppliesToFile);
        Assert.True(v.IsUpstreamActive);
    }

    [Fact]
    public void Movie_title_only_applicability_via_anchor_no_path_or_id()
    {
        var row = Row("""{"status":"failed","movie":{"title":"The Conversation","year":1974}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect);
        Assert.False(v.AppliesToFile);
        var cand = new FileAnchorCandidate("The Conversation 1974");
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v], cand));
        Assert.False(ProcessingDomain.ShouldBlockForUpstream([v], cand));
    }

    [Fact]
    public void Tracked_download_status_fallback()
    {
        var row = Row("""{"trackedDownloadStatus":"Downloading","outputPath":"/tmp/z.mkv","movie":{"title":"Z","year":2001}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect, candidatePath: "/tmp/z.mkv");
        Assert.True(v.IsUpstreamActive);
    }

    [Fact]
    public void Movie_dialect_ignores_series_block()
    {
        var row = Row("""{"status":"completed","movie":{"title":"Correct Movie","year":2020},"series":{"title":"Wrong Series","year":1999}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect);
        Assert.Equal("Correct Movie", v.QueueTitle);
        Assert.Equal(2020, v.QueueYear);
    }

    // --- tv scope (the shape Sonarr sends) ---------------------------------------

    [Fact]
    public void Tv_active_paused_row_series_id_owns_and_blocks()
    {
        var row = Row("""{"status":"paused","seriesId":9001,"series":{"title":"Sample Show","year":2020}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.TvDialect, candidateEntityId: 9001);
        Assert.True(v.AppliesToFile);
        Assert.Equal("Sample Show", v.QueueTitle);
        Assert.True(v.IsUpstreamActive);
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v]));
        Assert.True(ProcessingDomain.ShouldBlockForUpstream([v]));
    }

    [Fact]
    public void Tv_sparse_missing_series_uses_top_level_title_for_anchor()
    {
        var row = Row("""{"status":"failed","title":"Limited.Series.2024.1080p"}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.TvDialect);
        Assert.False(v.AppliesToFile);
        Assert.Equal("Limited.Series.2024.1080p", v.QueueTitle);
        Assert.Null(v.QueueYear);
        var cand = new FileAnchorCandidate("Limited Series 2024");
        Assert.True(ProcessingDomain.FileIsOwnedByQueue([v], cand));
    }

    [Fact]
    public void Tv_dialect_ignores_movie_block()
    {
        var row = Row("""{"status":"completed","movie":{"title":"Should Ignore","year":2001},"series":{"title":"Real Series","year":2018}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.TvDialect);
        Assert.Equal("Real Series", v.QueueTitle);
        Assert.Equal(2018, v.QueueYear);
    }

    [Fact]
    public void Mixed_scope_mapped_rows_domain_aggregation()
    {
        var movieBusy = Row("""{"status":"downloading","outputPath":"C:/q/a.mkv","title":"Alien.1979"}""");
        var tvSparse = Row("""{"status":"completed","title":"Alien 1979 1080p"}""");
        var cBusy = QueueRowMapping.MapQueueRowToProcessingView(movieBusy, QueueRowMapping.MovieDialect, candidatePath: "c:/q/a.mkv");
        var cSparse = QueueRowMapping.MapQueueRowToProcessingView(tvSparse, QueueRowMapping.TvDialect);
        var cand = new FileAnchorCandidate("Alien 1979");
        var rows = new[] { cBusy, cSparse };
        Assert.True(ProcessingDomain.FileIsOwnedByQueue(rows, cand));
        Assert.True(ProcessingDomain.ShouldBlockForUpstream(rows, cand));
    }

    // --- neutral keys, for managers that are neither Radarr nor Sonarr -----------

    [Fact]
    public void Neutral_media_block_and_entity_id_drive_a_movie_row()
    {
        var row = Row("""{"status":"downloading","entityId":7,"media":{"title":"Prospect","year":2018}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect, candidateEntityId: 7);
        Assert.True(v.AppliesToFile);
        Assert.Equal("Prospect", v.QueueTitle);
        Assert.Equal(2018, v.QueueYear);
        Assert.True(v.IsUpstreamActive);
    }

    [Fact]
    public void Neutral_media_block_drives_a_tv_row()
    {
        var row = Row("""{"status":"queued","entity_id":11,"media":{"title":"Slow Horses","year":2022}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.TvDialect, candidateEntityId: 11);
        Assert.True(v.AppliesToFile);
        Assert.Equal("Slow Horses", v.QueueTitle);
    }

    [Fact]
    public void Vendor_key_wins_over_neutral_key_when_both_present()
    {
        var row = Row("""{"status":"completed","movie":{"title":"Specific","year":1999},"media":{"title":"Generic","year":2000}}""");
        var v = QueueRowMapping.MapQueueRowToProcessingView(row, QueueRowMapping.MovieDialect);
        Assert.Equal("Specific", v.QueueTitle);
        Assert.Equal(1999, v.QueueYear);
    }

    [Theory]
    [InlineData("movie")]
    [InlineData("movies")]
    [InlineData("MOVIE")]
    public void Queue_dialect_for_scope_accepts_common_movie_spellings(string scope) =>
        Assert.Same(QueueRowMapping.MovieDialect, QueueRowMapping.DialectForScope(scope));

    [Theory]
    [InlineData("tv")]
    [InlineData("series")]
    [InlineData(" TV ")]
    public void Queue_dialect_for_scope_accepts_common_tv_spellings(string scope) =>
        Assert.Same(QueueRowMapping.TvDialect, QueueRowMapping.DialectForScope(scope));

    [Fact]
    public void Queue_dialect_for_scope_rejects_unknown_scope() =>
        Assert.Throws<ArgumentException>(() => QueueRowMapping.DialectForScope("music"));
}

/// <summary>Ported from <c>apps/backend/tests/test_processing_candidate_gate_evaluate.py</c> (domain evaluation, no HTTP).</summary>
public sealed class CandidateGateEvaluateTests
{
    private static PyDict Row(string json) => (PyDict)PyJsonParser.Parse(json);

    private static ManagerConnection Connection(string kind = "radarr", string name = "Main", long connectionId = 1) =>
        new(kind, name, "http://manager.local", "key", connectionId);

    private static ManagerQueueSignal Reported(IEnumerable<PyDict> rows, string scope = "movie", string kind = "radarr", string name = "Main", long connectionId = 1) =>
        new(Connection(kind, name, connectionId), SignalStatus.Reported, [.. rows.Select(r => new ManagerQueueRow(scope, r))]);

    private static ManagerQueueSignal Unreachable(string kind = "radarr", string name = "Main", long connectionId = 1, string detail = "Weir could not reach this manager.") =>
        new(Connection(kind, name, connectionId), SignalStatus.Unreachable, [], detail);

    private static ManagerQueueSignal NoQueueSignal(string kind = "native", string name = "Main", long connectionId = 1, string detail = "This manager cannot report a queue.") =>
        new(Connection(kind, name, connectionId), SignalStatus.NoSignal, [], detail);

    private static CandidateGateOutcome Evaluate(
        IReadOnlyList<ManagerQueueSignal> signals, string mediaScope = "movie", string releaseTitle = "Anything", int? releaseYear = null,
        string? outputPath = null, long? entityId = null)
    {
        var report = ManagerQueueSignals.ReportForSignals(signals);
        var rows = ManagerQueueSignals.AttributedQueueRows(signals, mediaScope, outputPath, entityId);
        var candidate = new FileAnchorCandidate(releaseTitle, releaseYear);
        return CandidateGate.Evaluate(mediaScope, report, rows, candidate);
    }

    [Fact]
    public void Wait_upstream_when_path_match_and_downloading()
    {
        var rows = new[] { Row("""{"status":"downloading","outputPath":"D:\\Media\\Film.mkv","movie":{"title":"Solaris","year":1972}}""") };
        var outcome = Evaluate([Reported(rows, name: "4K")], releaseTitle: "Solaris 1972", releaseYear: 1972, outputPath: "D:/media/film.mkv");
        Assert.Equal(CandidateGateVerdict.WaitUpstream, outcome.Verdict);
        Assert.True(outcome.Owned);
        Assert.True(outcome.BlockedUpstream);
        Assert.Equal(1, outcome.QueueRowCount);
    }

    [Fact]
    public void Proceed_import_pending_with_suppression()
    {
        var rows = new[] { Row("""{"status":"importPending","outputPath":"/data/complete/movie.mkv","blockingSuppressedForImportWait":true,"movie":{"title":"Nashville","year":1975}}""") };
        var outcome = Evaluate([Reported(rows)], releaseTitle: "Nashville", releaseYear: 1975, outputPath: "/data/complete/movie.mkv");
        Assert.Equal(CandidateGateVerdict.Proceed, outcome.Verdict);
        Assert.True(outcome.Owned);
        Assert.False(outcome.BlockedUpstream);
    }

    [Fact]
    public void Not_held_when_every_manager_reports_an_empty_queue()
    {
        var outcome = Evaluate([Reported([])]);
        Assert.Equal(CandidateGateVerdict.NotHeld, outcome.Verdict);
        Assert.False(outcome.Owned);
        Assert.Equal(0, outcome.QueueRowCount);
        Assert.Equal(1, outcome.ManagersReporting);
    }

    [Fact]
    public void Not_held_when_anchor_no_match()
    {
        var rows = new[] { Row("""{"status":"completed","movie":{"title":"Other Movie","year":1999}}""") };
        var outcome = Evaluate([Reported(rows)], releaseTitle: "Unrelated Release 2020");
        Assert.Equal(CandidateGateVerdict.NotHeld, outcome.Verdict);
        Assert.False(outcome.Owned);
    }

    [Fact]
    public void No_manager_configured_is_not_an_empty_queue()
    {
        var outcome = Evaluate([]);
        Assert.Equal(CandidateGateVerdict.NoUpstreamSignal, outcome.Verdict);
        Assert.Equal(0, outcome.ManagersConsulted);
        Assert.Contains("No media manager is connected for Movies", outcome.Reasons[0], StringComparison.Ordinal);
    }

    [Fact]
    public void Manager_with_no_queue_signal_never_reads_as_safe()
    {
        var outcome = Evaluate([NoQueueSignal(name: "Main")]);
        Assert.Equal(CandidateGateVerdict.NoUpstreamSignal, outcome.Verdict);
        Assert.Equal(0, outcome.ManagersReporting);
        Assert.Equal(["Media manager (Main)"], outcome.ManagersWithoutQueueSignal);
    }

    [Fact]
    public void Unreachable_manager_is_reported_not_treated_as_clear()
    {
        var outcome = Evaluate([Unreachable(name: "4K", detail: "Connection refused.")]);
        Assert.Equal(CandidateGateVerdict.NoUpstreamSignal, outcome.Verdict);
        Assert.Equal(["Radarr (4K)"], outcome.ManagersWithoutQueueSignal);
    }

    [Fact]
    public void Two_connections_and_only_one_blocks_still_blocks_the_file()
    {
        var quiet = Reported([], name: "1080p", connectionId: 1);
        var busy = Reported(
            [Row("""{"status":"downloading","outputPath":"/media/movies/Solaris.mkv","movie":{"title":"Solaris","year":1972}}""")],
            name: "4K", connectionId: 2);
        var outcome = Evaluate([quiet, busy], releaseTitle: "Solaris 1972", releaseYear: 1972, outputPath: "/media/movies/Solaris.mkv");
        Assert.Equal(CandidateGateVerdict.WaitUpstream, outcome.Verdict);
        Assert.Equal("Radarr (4K)", outcome.BlockedByConnection);
        Assert.Contains("Radarr (4K) is still importing this file", outcome.Reasons[0], StringComparison.Ordinal);
    }

    [Fact]
    public void Partial_answer_still_reports_the_manager_that_stayed_silent()
    {
        var outcome = Evaluate([Reported([], name: "1080p", connectionId: 1), Unreachable(name: "4K", connectionId: 2)], releaseTitle: "Solaris 1972");
        Assert.Equal(CandidateGateVerdict.NotHeld, outcome.Verdict);
        Assert.Equal(["Radarr (4K)"], outcome.ManagersWithoutQueueSignal);
        Assert.Contains(outcome.Reasons, reason => reason.Contains("could not get an import check from Radarr (4K)", StringComparison.Ordinal));
    }

    [Fact]
    public void A_manager_serving_both_scopes_answers_a_tv_candidate()
    {
        var rows = new[] { Row("""{"status":"downloading","outputPath":"/tv/Show/S01E01.mkv","media":{"title":"Show","year":2001}}""") };
        var outcome = Evaluate([Reported(rows, scope: "tv", kind: "deluno", name: "Main")], mediaScope: "tv", releaseTitle: "Show 2001", releaseYear: 2001, outputPath: "/tv/Show/S01E01.mkv");
        Assert.Equal(CandidateGateVerdict.WaitUpstream, outcome.Verdict);
        Assert.Equal("Deluno (Main)", outcome.BlockedByConnection);
    }
}
