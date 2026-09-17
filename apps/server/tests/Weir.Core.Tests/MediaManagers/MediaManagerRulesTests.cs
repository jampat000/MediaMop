using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Core.Tests.MediaManagers;

/// <summary>
/// Ports of <c>test_media_manager_handoff_paths.py</c>, the dialect assertions of <c>test_media_manager_port_dialects.py</c>,
/// the body assertions of <c>test_media_manager_completion_callback.py</c>, and the pure intake and ledger rules.
/// </summary>
public sealed class MediaManagerRulesTests
{
    private static PyDict Dict(string json) => (PyDict)PyJsonParser.Parse(json);

    // --- handoff_paths -------------------------------------------------------------------------

    [Theory]
    [InlineData("/srv/handoff", "/srv/handoff/Film/film.mkv", "Film/film.mkv")]
    [InlineData("/srv/handoff/", "/srv/handoff/film.mkv", "film.mkv")]
    [InlineData("D:\\Handoff", "D:\\Handoff\\Film\\film.mkv", "Film/film.mkv")]
    [InlineData("D:/Handoff", "D:\\Handoff\\Film\\film.mkv", "Film/film.mkv")]
    [InlineData("D:\\handoff", "D:\\HANDOFF\\Film\\film.mkv", "Film/film.mkv")]
    [InlineData(@"\\storage-city\Data\Media\Handoff", @"\\storage-city\data\media\handoff\a\b.mkv", "a/b.mkv")]
    [InlineData("/w", "/w/a/b/c/d.mkv", "a/b/c/d.mkv")]
    public void Paths_inside_the_watched_folder_resolve(string watched, string file, string expected)
    {
        var result = HandoffPaths.RelativeMediaPathForHandoff(watched, file);
        Assert.True(result.Ok);
        Assert.Equal(expected, result.RelativeMediaPath);
        Assert.Null(result.Problem);
    }

    [Fact]
    public void The_original_case_is_preserved_in_the_relative_path() =>
        Assert.Equal("Blade.Runner.2049/Film.MKV", HandoffPaths.RelativeMediaPathForHandoff("/srv/handoff", "/SRV/HANDOFF/Blade.Runner.2049/Film.MKV").RelativeMediaPath);

    [Theory]
    [InlineData("/srv/handoff", "/somewhere/else/film.mkv")]
    [InlineData("/srv/handoff", "/srv/handoff-other/film.mkv")]
    [InlineData("/srv/handoff", "/srv/handoff")]
    [InlineData("/srv/handoff", "/srv")]
    [InlineData("/srv/handoff", "/srv/handoff/../../etc/passwd")]
    public void Paths_outside_the_watched_folder_are_refused(string watched, string file)
    {
        var result = HandoffPaths.RelativeMediaPathForHandoff(watched, file);
        Assert.False(result.Ok);
        Assert.Contains("watched folder", result.Problem, StringComparison.Ordinal);
    }

    [Fact]
    public void A_missing_folder_or_file_is_named_as_the_problem()
    {
        foreach (var empty in new[] { null, string.Empty, "   " })
        {
            Assert.Contains("watched folder is not set", HandoffPaths.RelativeMediaPathForHandoff(empty, "/a/b.mkv").Problem, StringComparison.Ordinal);
        }

        Assert.Contains("did not name a file path", HandoffPaths.RelativeMediaPathForHandoff("/srv/handoff", "  ").Problem, StringComparison.Ordinal);
        Assert.Equal(
            "The hand-off names '/x/y.mkv', which is not inside Weir's watched folder '/srv'. Point the media manager and Weir at the same folder — both hosts have to see it at that path.",
            HandoffPaths.RelativeMediaPathForHandoff("/srv", "/x/y.mkv").Problem);
    }

    // --- import_events -------------------------------------------------------------------------

    [Fact]
    public void Dialects_unwrap_each_managers_phrasing()
    {
        Assert.Null(ImportEvents.DialectForSource("sonarr")!.Normalize(Dict("""{"eventType":"Grab","episodes":[{"id":1}]}""")));
        var sonarr = ImportEvents.DialectForSource(" SONARR ")!.Normalize(Dict(
            """{"eventType":"Download","series":{"title":"Test Show"},"episodes":[{"id":9,"seasonNumber":1,"episodeNumber":2.0,"title":"Hello"}],"episodeFile":{"path":"/media/t/x.mkv"}}"""))!;
        Assert.Equal(("imported", "tv", "/media/t/x.mkv", "Test Show", 2), (sonarr.EventKind, sonarr.MediaScope, sonarr.FilePath, sonarr.ShowTitle, (int)sonarr.EpisodeNumber!.Value));

        var deluno = ImportEvents.DialectForSource("deluno")!.Normalize(Dict(
            """{"eventType":"deluno.processor-handoff","handoffId":"h1","libraryId":"lib-1","mediaType":"movies","sourcePath":" /w/f.mkv ","releaseName":"R","callbackPath":"/cb"}"""))!;
        Assert.Equal(("handoff", "movie", "/w/f.mkv", "h1", "lib-1", "/cb", "R"), (deluno.EventKind, deluno.MediaScope, deluno.FilePath, deluno.HandoffId, deluno.LibraryId, deluno.CallbackPath, deluno.ReleaseName));
        Assert.Null(ImportEvents.DialectForSource("deluno")!.Normalize(Dict("""{"eventType":"deluno.processor-handoff","mediaType":"music","sourcePath":"/x"}""")));

        var native = ImportEvents.DialectForSource("native")!.Normalize(Dict("""{"event":"HANDOFF","media_scope":"series","file_path":"/x.mkv","handoff_id":"n1","seasonNumber":0,"season_number":3}"""))!;
        Assert.Equal(("handoff", "tv", "n1", 3), (native.EventKind, native.MediaScope, native.HandoffId, (int)native.SeasonNumber!.Value));
        Assert.Null(ImportEvents.DialectForSource("native")!.Normalize(Dict("""{"event":"imported","title":"no path"}""")));
        Assert.Null(ImportEvents.DialectForSource("native")!.Normalize(Dict("""{"event":"deleted","filePath":"/x","mediaScope":"movie"}""")));
        Assert.Null(ImportEvents.DialectForSource("plex"));
        Assert.Equal(["deluno", "native", "radarr", "sonarr"], ImportEvents.KnownSourceKeys());
    }

    // --- manager_port / manager_dialects -------------------------------------------------------

    [Fact]
    public void The_label_names_the_connection_not_just_the_vendor()
    {
        Assert.Equal("Deluno (Main)", MediaManagerKinds.LabelForConnection("deluno", "Main"));
        Assert.Equal("Radarr (4K)", MediaManagerKinds.LabelForConnection("radarr", "4K"));
        Assert.Equal("Deluno", MediaManagerKinds.LabelForConnection("deluno", "Deluno"));
        Assert.Equal("Media manager (Home)", MediaManagerKinds.LabelForConnection("native", "Home"));
    }

    [Fact]
    public void Scope_capabilities_are_static_so_binding_costs_no_requests()
    {
        Assert.Equal(["deluno", "native", "radarr"], ManagerKindProfiles.KindsServingScope("movie"));
        Assert.Equal(["deluno", "native", "sonarr"], ManagerKindProfiles.KindsServingScope("tv"));
        var deluno = ManagerKindProfiles.CapabilitiesForKind("deluno")!;
        Assert.Equal(["movie", "tv"], deluno.Scopes);
        Assert.True(deluno.ReportsQueue);
        Assert.False(deluno.ReportsLibraryTruth);
        Assert.False(deluno.RemovesQueueItems);
        Assert.True(ManagerKindProfiles.CapabilitiesForKind("sonarr")!.RemovesQueueItems);
    }

    [Theory]
    [InlineData("running", "downloading")]
    [InlineData("queued", "downloading")]
    [InlineData("importing", "importpending")]
    [InlineData("Import Pending", "importpending")]
    [InlineData("failed", "failed")]
    [InlineData("something Weir has never heard of", "downloading")]
    public void An_unrecognised_deluno_state_reads_as_still_in_progress(string reported, string expected) =>
        Assert.Equal(expected, ManagerDialectRules.ExternalQueueStatus(Dict($$"""{"status":"{{reported}}"}""")));

    [Fact]
    public void The_deluno_queue_covers_jobs_and_recent_dispatches_and_drops_rows_without_a_scope()
    {
        var rows = ManagerDialectRules.ExternalQueueEntries(PyJsonParser.Parse(
            """{"jobs":[{"mediaType":"movie","status":"downloading","targetPath":"/media/movies/Solaris.mkv","title":"Solaris","year":1972},{"status":"running","path":"/x.mkv"}],"dispatches":[{"mediaType":"series","state":"completed","path":"/tv/Show/S01E01.mkv","id":7}]}"""))
            .Select(ManagerDialectRules.ExternalQueueRow).OfType<ManagerQueueRow>().ToList();
        Assert.Equal(["movie", "tv"], rows.Select(row => row.Scope));
        Assert.Equal(
            """{"status":"downloading","outputPath":"/media/movies/Solaris.mkv","title":"Solaris","media":{"title":"Solaris","year":1972},"entityId":null}""",
            PyJsonWriter.Dumps(rows[0].Payload, PyJsonFormat.Compact));
        Assert.Equal("completed", ((PyStr)rows[1].Payload["status"]).Value);
        Assert.Equal("7", rows[1].Payload["entityId"].ToString());
    }

    [Fact]
    public void A_deluno_manifest_narrows_scopes_and_reads_the_confirmed_library_contract()
    {
        var connection = new ManagerConnection("deluno", "Main", "http://manager.local", "k", 1);
        var description = ManagerDialectRules.ExternalDescription(connection, ManagerKindProfiles.CapabilitiesForKind("deluno")!, PyJsonParser.Parse(
            """{"libraries":[{"id":"abc","name":"Films","mediaType":"movie","path":"/media/movies","rootPath":"/media/movies","importWorkflow":"Refine-Before-Import","processorOutputPath":"/data/refined"},{"mediaType":"movie","path":"/nokey"}],"capabilities":[" Handoff-Status ",5,""]}"""));
        Assert.Equal(["movie"], description.Capabilities.Scopes);
        Assert.Equal(["/media/movies", "/nokey"], description.LibraryRoots);
        var library = Assert.Single(description.Libraries);
        Assert.Equal(new ManagerLibraryDescriptor("abc", "Films", "movie", "/media/movies", "/data/refined", true), library);
        Assert.Equal(["handoff-status"], description.AdvertisedCapabilities!);
    }

    [Fact]
    public void Arr_answers_read_records_roots_and_nested_files()
    {
        Assert.Equal(["movie"], ManagerDialectRules.ArrQueueRows(PyJsonParser.Parse("""{"records":[{"status":"downloading"},"junk"]}"""), "movie").Select(r => r.Scope));
        Assert.Equal(["/media/Solaris/f.mkv"], ManagerDialectRules.ArrLibraryFilePaths(PyJsonParser.Parse("""[{"movieFile":{"path":"/media/Solaris/f.mkv"}},{"movieFile":null},{}]"""), "movieFile"));
        Assert.Equal(["/tv/Show/S01/e.mkv"], ManagerDialectRules.ArrLibraryFilePaths(PyJsonParser.Parse("""[{"path":"/tv/Show/S01/e.mkv"}]"""), null));
        // #544 item 4: a root folder with a null path is skipped, not reported as a root literally called "None"
        // (`str(row.get("path", ""))` in Python turns a JSON null into the text "None" — the `dict.get` default
        // only applies when the key is missing, never when it is present and null).
        var (roots, libraries) = ManagerDialectRules.ArrRootFolders(PyJsonParser.Parse("""[{"id":3,"path":"/m"},{"id":0,"path":"/z"},{"path":null}]"""), "movie");
        Assert.Equal(["/m", "/z"], roots);
        Assert.Equal(["3", "/z"], libraries.Select(l => l.Key));
    }

    [Fact]
    public void Unreachable_sentences_name_the_connection_and_what_to_fix()
    {
        var connection = new ManagerConnection("radarr", "4K", "http://m", "k");
        Assert.Contains("Radarr (4K)", ManagerDialectRules.Unreachable(connection, new MediaManagerUnreachableException("refused"), "what it is importing"), StringComparison.Ordinal);
        Assert.Contains("refused Weir's API key", ManagerDialectRules.Unreachable(connection, new MediaManagerHttpException("HTTP 401: nope"), "x"), StringComparison.Ordinal);
        var limited = ManagerDialectRules.Unreachable(new ManagerConnection("deluno", "Main", "http://m", "k"), new MediaManagerRateLimitedException("HTTP 429", 30.9), "what it is importing");
        Assert.Contains("rate limiting Weir", limited, StringComparison.Ordinal);
        Assert.Contains("about 30s", limited, StringComparison.Ordinal);
        Assert.Contains("backed off rather than retrying straight away", limited, StringComparison.Ordinal);
    }

    [Fact]
    public void Filtering_rows_to_the_asked_scope_leaves_a_silent_manager_silent()
    {
        var connection = new ManagerConnection("deluno", "Main", "http://m", "k");
        var reported = new ManagerQueueSignal(connection, SignalStatus.Reported, [new("movie", new PyDict().Set("title", "a film")), new("tv", new PyDict().Set("title", "an episode"))]);
        Assert.Equal(["movie"], ManagerDialectRules.OnlyRowsForScope(reported, "movie").Rows.Select(r => r.Scope));
        var silent = new ManagerQueueSignal(connection, SignalStatus.Unreachable, [], "down");
        Assert.Same(silent, ManagerDialectRules.OnlyRowsForScope(silent, "movie"));
    }

    // --- completion_callback -------------------------------------------------------------------

    private static readonly HandoffOrigin Origin = new("deluno", "handoff-1", "/api/integrations/processors/events", "Blade.Runner.2049");
    private static readonly HandoffOrigin DelunoOrigin = new("deluno", "handoff-1", "/api/integrations/processors/events", null, "lib-movies");

    [Fact]
    public void A_written_output_is_reported_as_completed_with_its_path()
    {
        var body = CompletionReports.BuildCompletionBody(Origin, Dict("""{"ok":true,"outcome":"live_output_written","output_file":"D:\\Refined\\Blade.Runner.2049\\film.mkv","removed_audio":["fre","deu"],"removed_subtitles":["spa"]}"""));
        Assert.Equal(
            """{"handoffId":"handoff-1","status":"completed","processorName":"Weir","releaseName":"Blade.Runner.2049","outputPath":"D:\\Refined\\Blade.Runner.2049\\film.mkv","message":"Removed 2 audio track(s) and 1 subtitle track(s)."}""",
            PyJsonWriter.Dumps(body, PyJsonFormat.Compact));
    }

    [Fact]
    public void Success_wording_covers_no_remux_pass_through_and_pass_through_after_failure()
    {
        Assert.Contains("No remux was needed", ((PyStr)CompletionReports.BuildCompletionBody(Origin, Dict("""{"ok":true,"outcome":"live_skipped_not_required","output_file":"/out/film.mkv"}"""))["message"]).Value, StringComparison.Ordinal);
        Assert.Contains("passed this file through unchanged", ((PyStr)CompletionReports.BuildCompletionBody(Origin, Dict("""{"ok":true,"outcome":"live_skipped_not_required","pass_through_unchanged":true}"""))["message"]).Value, StringComparison.Ordinal);
        Assert.StartsWith("Weir could not process this file, so it handed the original back", ((PyStr)CompletionReports.BuildCompletionBody(DelunoOrigin, Dict("""{"ok":true,"outcome":"live_output_written","passed_through_after_failure":true}"""))["message"]).Value, StringComparison.Ordinal);
        Assert.Equal("/data/refined/film.mkv", ((PyStr)CompletionReports.BuildCompletionBody(DelunoOrigin, Dict("""{"ok":true,"outcome":"live_output_written","output_file":"/local/out/film.mkv"}"""), "/data/refined/film.mkv")["outputPath"]).Value);
    }

    [Fact]
    public void Failures_carry_the_reason_and_what_happened_to_the_source()
    {
        var failed = CompletionReports.BuildCompletionBody(Origin, Dict("""{"ok":false,"outcome":"failed_before_execution","reason":"relative_media_path is required"}"""));
        Assert.Equal("relative_media_path is required", ((PyStr)failed["message"]).Value);
        Assert.False(failed.ContainsKey("outputPath"));

        var guardrail = CompletionReports.BuildCompletionBody(Origin, Dict("""{"ok":true,"outcome":"skipped_guardrail","source_folder_skip_reason":"File is too small."}"""));
        Assert.Equal(("failed", "File is too small."), (((PyStr)guardrail["status"]).Value, ((PyStr)guardrail["message"]).Value));

        Assert.Equal(
            """{"handoffId":"handoff-1","status":"failed","processorName":"Weir","libraryId":"lib-movies","message":"ffmpeg failed","disposition":"held","sourceRemoved":false,"failureClass":"execution"}""",
            PyJsonWriter.Dumps(CompletionReports.BuildCompletionBody(DelunoOrigin, Dict("""{"ok":false,"outcome":"failed_execution","reason":"ffmpeg failed","failure_class":"execution"}""")), PyJsonFormat.Compact));

        var deleted = CompletionReports.BuildCompletionBody(DelunoOrigin, Dict("""{"ok":false,"outcome":"skipped_rejected","reason":"No wanted audio language.","rejected_cleanup_status":"deleted"}"""));
        Assert.True(((PyBool)deleted["sourceRemoved"]).Value);
        Assert.False(deleted.ContainsKey("disposition"));

        var rejected = CompletionReports.BuildCompletionBody(DelunoOrigin, Dict("""{"ok":false,"outcome":"failed","reason":"No usable audio.","failure_class":"preflight"}"""), rejected: true);
        Assert.Equal(("rejected", true, "preflight"), (((PyStr)rejected["disposition"]).Value, ((PyBool)rejected["sourceRemoved"]).Value, ((PyStr)rejected["failureClass"]).Value));
        Assert.False(CompletionReports.BuildCompletionBody(DelunoOrigin, Dict("""{"ok":true,"outcome":"live_output_written"}""")).ContainsKey("disposition"));
    }

    [Fact]
    public void The_origin_is_read_from_the_job_payload()
    {
        Assert.Null(HandoffOrigin.FromPayload(Dict("""{"relative_media_path":"a/b.mkv"}""")));
        Assert.Null(HandoffOrigin.FromPayload(null));
        Assert.Null(HandoffOrigin.FromPayload(Dict("""{"origin":{}}""")));
        Assert.Equal(new HandoffOrigin("deluno", "h1", "/cb", "R"), HandoffOrigin.FromPayload(Dict("""{"origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"/cb","release_name":"R"}}""")));
        Assert.Equal("lib-movies", HandoffOrigin.FromPayload(Dict("""{"origin":{"source_key":"deluno","library_id":"lib-movies"}}"""))!.LibraryId);
        Assert.Equal("5", HandoffOrigin.FromPayload(Dict("""{"origin":{"source_key":" deluno ","handoff_id":5,"callback_path":""}}"""))!.HandoffId);
    }

    [Theory]
    [InlineData("/data/refined", "/data/refined/Blade.Runner.2049/film.mkv")]
    [InlineData(@"E:\Deluno\Refined", @"E:\Deluno\Refined\Blade.Runner.2049\film.mkv")]
    [InlineData("E:/Deluno/Refined/", "E:/Deluno/Refined/Blade.Runner.2049/film.mkv")]
    [InlineData(@"\\nas\share\out", @"\\nas\share\out\Blade.Runner.2049\film.mkv")]
    public void Output_paths_are_rebuilt_in_the_managers_own_style(string folder, string expected)
    {
        var joined = CompletionReports.ManagerPathJoin(folder, ["Blade.Runner.2049", "film.mkv"]);
        // "E:/..." has a drive letter, so it is a Windows path and Python writes it with backslashes.
        Assert.Equal(folder.StartsWith("E:/", StringComparison.Ordinal) ? expected.Replace('/', '\\') : expected, joined);
    }

    // --- handoff_ledger ------------------------------------------------------------------------

    [Theory]
    [InlineData("processed", "completed")]
    [InlineData("passed_through", "passed-through")]
    [InlineData("rejected", "rejected")]
    [InlineData("processing_failed", "failed")]
    [InlineData("out_of_schedule", "scheduled")]
    [InlineData("processing", "working")]
    [InlineData("skipped", "failed")]
    [InlineData("blocked_upstream", "queued")]
    [InlineData("unprocessed", "queued")]
    public void File_states_map_to_the_agreed_vocabulary(string status, string state) =>
        Assert.Equal(state, HandoffLedgerRules.FileState(status, null, 0).State);

    [Fact]
    public void A_file_held_after_repeated_failures_is_failed_and_one_held_briefly_is_queued()
    {
        Assert.Equal("failed", HandoffLedgerRules.FileState("on_hold", null, 3).State);
        Assert.Equal("queued", HandoffLedgerRules.FileState("on_hold", null, 2).State);
    }

    [Fact]
    public void Issue_531_a_failure_with_a_retry_owed_is_scheduled_even_after_the_backoff_ends()
    {
        var future = new DateTimeOffset(2026, 9, 17, 12, 0, 0, TimeSpan.Zero);
        Assert.Equal(("scheduled", future), HandoffLedgerRules.FileState("processing_failed", future, 1));
        var past = future.AddHours(-3);
        Assert.Equal(("scheduled", past), HandoffLedgerRules.FileState("processing_failed", past, 2));
        Assert.Equal(("failed", (DateTimeOffset?)null), HandoffLedgerRules.FileState("processing_failed", null, 2));
    }

    [Fact]
    public void A_hand_off_is_as_far_along_as_its_least_finished_file()
    {
        Assert.Equal("working", HandoffLedgerRules.Combine(["completed", "queued", "working"]));
        Assert.Equal("scheduled", HandoffLedgerRules.Combine(["completed", "scheduled"]));
        Assert.Equal("failed", HandoffLedgerRules.Combine(["passed-through", "failed", "rejected"]));
        Assert.Equal("passed-through", HandoffLedgerRules.Combine(["completed", "passed-through"]));
        Assert.Equal("completed", HandoffLedgerRules.Combine(["completed"]));
    }

    [Fact]
    public void Status_json_writes_utc_with_a_z_and_drops_zero_microseconds()
    {
        var status = new HandoffStatus("h1", "queued", new DateTimeOffset(2026, 9, 17, 10, 0, 0, TimeSpan.Zero), 1, null, null, null);
        Assert.Equal(
            """{"handoffId":"h1","state":"queued","queuePosition":1,"scheduledFor":null,"lastChangedUtc":"2026-09-17T10:00:00Z","outputPath":null,"message":null}""",
            PyJsonWriter.Dumps(status.AsJson(), PyJsonFormat.Response));
        Assert.Equal("2026-09-17T10:00:00.000500Z", ((PyStr)(status with { LastChangedAt = status.LastChangedAt.AddTicks(5000) }).AsJson()["lastChangedUtc"]).Value);
    }

    // --- intake --------------------------------------------------------------------------------

    private static MediaManagerImportEvent Handoff(string path, string? handoffId = "handoff-1", string scope = "movie") => new()
    {
        SourceKey = "deluno",
        EventKind = "handoff",
        MediaScope = scope,
        FilePath = path,
        HandoffId = handoffId,
        CallbackPath = handoffId is null ? null : "/api/integrations/processors/events",
        ReleaseName = "Blade.Runner.2049",
        LibraryId = "lib-1",
    };

    [Fact]
    public void The_job_payload_is_written_as_python_writes_it()
    {
        var importEvent = Handoff("/w/Blade.Runner.2049/film.mkv");
        var payload = IntakeRules.Payload(importEvent, new IntakeLibrary(4, "movie", "/w"), "Blade.Runner.2049", "Blade.Runner.2049/film é.mkv");
        Assert.Equal(
            """{"relative_media_path":"Blade.Runner.2049/film \u00e9.mkv","media_scope":"movie","trigger":"webhook","library_id":4,"origin":{"source_key":"deluno","handoff_id":"handoff-1","callback_path":"/api/integrations/processors/events","release_name":"Blade.Runner.2049","library_id":"lib-1"}}""",
            IntakeRules.PayloadJson(payload));
        Assert.Equal(
            """{"relative_media_path":"a.mkv","media_scope":"tv","trigger":"webhook"}""",
            IntakeRules.PayloadJson(IntakeRules.Payload(Handoff("/x/a.mkv", null, "tv") with { CallbackPath = null }, null, "a.mkv", "a.mkv")));
    }

    [Fact]
    public void Dedupe_keys_match_the_python_keys()
    {
        var baseKey = IntakeRules.BaseDedupeKey(Handoff("/w/x.mkv"), () => Guid.Empty);
        Assert.Equal("refiner.file.remux_pass.v1:deluno:handoff:handoff-1", baseKey);
        Assert.Equal("refiner.file.remux_pass.v1:00000000000000000000000000000000", IntakeRules.BaseDedupeKey(Handoff("/w/x.mkv", null), () => Guid.Empty));
        Assert.Equal(baseKey, IntakeRules.DedupeKeyFor(baseKey, ["Film/film.mkv"], "Film/film.mkv", "Film/film.mkv"));
        Assert.Equal(baseKey + ":Film/film.mkv", IntakeRules.DedupeKeyFor(baseKey, ["Film/film.mkv"], "Film/film.mkv", "Film"));
    }

    [Fact]
    public void The_library_is_chosen_by_the_deepest_watched_folder_preferring_the_hand_offs_media_type()
    {
        IntakeLibrary[] libraries = [new(1, "movie", "/media"), new(2, "movie", "/media/films"), new(3, "tv", "/media/films/4k"), new(4, "movie", "/media/films")];
        Assert.Equal(2, IntakeRules.ChooseLibrary(libraries, Handoff("/media/films/4k/x/film.mkv"))!.Value.Library.Id);
        Assert.Equal(3, IntakeRules.ChooseLibrary(libraries, Handoff("/media/films/4k/x/ep.mkv", scope: "tv"))!.Value.Library.Id);
        Assert.Equal("x/film.mkv", IntakeRules.ChooseLibrary(libraries, Handoff("/media/films/x/film.mkv"))!.Value.Resolved.RelativeMediaPath);
        Assert.Null(IntakeRules.ChooseLibrary(libraries, Handoff("/elsewhere/film.mkv")));
    }

    [Fact]
    public void A_folder_means_its_videos_without_the_samples()
    {
        List<IReadOnlyList<string>> videos = [["Sample", "sample.mkv"], ["Film.mkv"], ["extras", "film-sample.mp4"], ["b.MKV"]];
        Assert.Equal(["b.MKV", "Film.mkv"], IntakeRules.ChooseFolderVideos(videos, windows: true).Select(parts => string.Join('/', parts)));
        Assert.Equal(["Film.mkv", "b.MKV"], IntakeRules.ChooseFolderVideos(videos, windows: false).Select(parts => string.Join('/', parts)));
        List<IReadOnlyList<string>> onlySamples = [["sample.mkv"]];
        Assert.Single(IntakeRules.ChooseFolderVideos(onlySamples, windows: false));
        Assert.True(IntakeRules.IsMediaCandidateName("Film.MKV"));
        Assert.False(IntakeRules.IsMediaCandidateName(".mkv"));
        Assert.False(IntakeRules.IsMediaCandidateName("movie.nfo"));
    }

    [Fact]
    public void Schedule_fields_are_validated_with_plain_sentences()
    {
        Assert.Equal("Mon,Tue", ScheduleCsv.ValidateScheduleDaysCsv(" Mon , ,Tue"));
        Assert.Equal(string.Empty, ScheduleCsv.ValidateScheduleDaysCsv("  "));
        Assert.Equal("Days must be written like Mon, Tue, Wed with commas between them.", Assert.Throws<PyValueErrorException>(() => ScheduleCsv.ValidateScheduleDaysCsv("monday")).Message);
        Assert.Equal("09:05", ScheduleCsv.NormalizeHhmm("9:5", "00:00"));
        Assert.Equal("23:59", ScheduleCsv.NormalizeHhmm("", "23:59"));
        Assert.Throws<PyValueErrorException>(() => ScheduleCsv.NormalizeHhmm("25:00", "00:00"));
        Assert.Throws<PyValueErrorException>(() => ScheduleCsv.NormalizeHhmm("9", "00:00"));
    }

    [Fact]
    public void Tmdb_answers_are_read_into_lookup_results()
    {
        var matched = TmdbResponses.Parse("""{"results":[{"id":42,"title":"Film","original_language":"FR ","release_date":"2001-05-01"}]}"""u8.ToArray(), "Film (2001)");
        Assert.True(matched.Matched);
        Assert.Equal(("fr", 2001, "42", "Film"), (matched.Metadata!.OriginalLanguage, matched.Metadata.Year!.Value, matched.Metadata.ProviderId, matched.Metadata.Title));
        Assert.Equal("no_match", TmdbResponses.Parse("""{"results":[]}"""u8.ToArray(), "x").Status);
        var unreadable = TmdbResponses.Parse("not json"u8.ToArray(), "x");
        Assert.Equal("unreachable", unreadable.Status);
        Assert.Contains("unreadable", unreadable.Detail, StringComparison.Ordinal);
        Assert.Equal("api_key=k&query=Blade+Runner%C3%A9&year=1982", TmdbResponses.UrlEncode([new("api_key", "k"), new("query", "Blade Runneré"), new("year", "1982")]));
        Assert.StartsWith("https://", TmdbResponses.DefaultBaseUrl, StringComparison.Ordinal);
    }

    // --- list_library_files / file_changed (#507) -----------------------------------------------

    [Fact]
    public void Movie_library_files_carry_the_movies_own_id_and_title()
    {
        var files = ManagerDialectRules.ArrMovieLibraryFiles(PyJsonParser.Parse(
            """[{"id":7,"title":"Solaris","movieFile":{"path":"/media/Solaris/f.mkv"}},{"id":8,"title":"No File"},{"id":9,"movieFile":{"path":"/media/9/f.mkv"}}]"""));
        Assert.Equal(
            [new ManagerLibraryFile("7", "Solaris", "/media/Solaris/f.mkv"), new ManagerLibraryFile("9", "9", "/media/9/f.mkv")],
            files);
    }

    [Fact]
    public void Episode_library_files_are_tagged_with_the_series_already_looked_up()
    {
        var files = ManagerDialectRules.ArrEpisodeLibraryFiles(
            PyJsonParser.Parse("""[{"path":"/tv/Show/S01/e01.mkv"},{"path":"/tv/Show/S01/e02.mkv"},{"seasonNumber":1}]"""), "12", "Show");
        Assert.Equal(
            [new ManagerLibraryFile("12", "Show", "/tv/Show/S01/e01.mkv"), new ManagerLibraryFile("12", "Show", "/tv/Show/S01/e02.mkv")],
            files);
    }

    [Theory]
    [InlineData("movie", "RescanMovie", "movieId")]
    [InlineData("tv", "RescanSeries", "seriesId")]
    public void The_rescan_command_matches_each_products_own_class(string scope, string name, string idProperty) =>
        Assert.Equal((name, idProperty), ManagerDialectRules.ArrRescanCommand(scope));

    [Theory]
    [InlineData("/media/Movies/f.mkv", "/media/Movies/f.mkv", true)]
    [InlineData(@"D:\Media\Movies\f.mkv", "d:/media/movies/f.mkv", true)]
    [InlineData("/media/Movies/f.mkv", "/media/Movies/g.mkv", false)]
    [InlineData("", "", false)]
    public void Paths_compare_ignoring_case_and_separator_style(string left, string right, bool equal) =>
        Assert.Equal(equal, LibraryFileChangeRules.PathsEqual(left, right));

    [Fact]
    public void The_warning_names_the_manager_and_says_it_will_catch_up_on_its_own()
    {
        var warning = LibraryFileChangeRules.CouldNotTellWarning(new ManagerConnection("radarr", "4K", "http://m", "k"));
        Assert.Equal("Weir cleaned the file but couldn't tell Radarr (4K); it will catch up at its next disk scan.", warning);
    }
}
