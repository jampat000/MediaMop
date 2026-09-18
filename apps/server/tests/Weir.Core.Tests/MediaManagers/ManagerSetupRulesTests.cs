using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Core.Tests.MediaManagers;

/// <summary>
/// <see cref="ManagerSetupRules"/> and <see cref="ArrOsPath"/>: a remote path mapping judged exactly the way Sonarr/Radarr
/// apply it (see the types' remarks for the source lines each rule mirrors), and what Deluno's manifest can tell a library.
/// </summary>
public sealed class ManagerSetupRulesTests
{
    /// <summary>A qBittorrent and a disabled SABnzbd, as Sonarr's <c>GET /api/v3/downloadclient</c> returns them (fields trimmed).</summary>
    private const string SonarrClients = """
        [
          {"enable":true,"protocol":"torrent","priority":1,"removeCompletedDownloads":true,"removeFailedDownloads":true,"name":"qBittorrent",
           "fields":[
             {"order":0,"name":"host","label":"Host","value":"qbittorrent","type":"textbox","advanced":false,"privacy":"normal","isFloat":false},
             {"order":1,"name":"port","label":"Port","value":8080,"type":"textbox","advanced":false,"privacy":"normal","isFloat":false},
             {"order":2,"name":"useSsl","label":"Use SSL","value":false,"type":"checkbox","advanced":false,"privacy":"normal","isFloat":false},
             {"order":5,"name":"password","label":"Password","value":"********","type":"password","advanced":false,"privacy":"password","isFloat":false},
             {"order":6,"name":"tvCategory","label":"Category","value":"tv-sonarr","type":"textbox","advanced":false,"privacy":"normal","isFloat":false},
             {"order":7,"name":"tvImportedCategory","label":"Post-Import Category","type":"textbox","advanced":true,"privacy":"normal","isFloat":false}
           ],
           "implementationName":"qBittorrent","implementation":"QBittorrent","configContract":"QBittorrentSettings",
           "infoLink":"https://wiki.servarr.com/sonarr/supported#qbittorrent","tags":[],"id":1},
          {"enable":false,"protocol":"usenet","priority":1,"removeCompletedDownloads":true,"removeFailedDownloads":true,"name":"SABnzbd",
           "fields":[{"order":0,"name":"host","label":"Host","value":"sabnzbd","type":"textbox"},{"order":7,"name":"tvCategory","label":"Category","value":"tv","type":"textbox"}],
           "implementationName":"SABnzbd","implementation":"Sabnzbd","configContract":"SabnzbdSettings","tags":[],"id":2}
        ]
        """;

    private static List<ArrDownloadClientEntry> Clients(string json = SonarrClients, string scope = MediaManagerKinds.Tv) =>
        ManagerSetupRules.ParseDownloadClients(PyJsonParser.Parse(json), scope);

    private static List<RemotePathMappingEntry> Mappings(string json) => ManagerSetupRules.ParseMappings(PyJsonParser.Parse(json));

    private static ArrSetupResult Sonarr(string watched, string output, string mappingsJson, bool? cdh = true, List<ArrDownloadClientEntry>? clients = null) =>
        ManagerSetupRules.EvaluateArr("Sonarr", MediaManagerKinds.Tv, watched, output, Mappings(mappingsJson), clients ?? Clients(), cdh);

    private static string Single(ArrSetupResult result, string state) =>
        Assert.Single(result.Lines, line => line.State == state && !line.Text.StartsWith("Completed Download Handling", StringComparison.Ordinal)).Text;

    // --- OsPath, as Sonarr/Radarr compare paths ------------------------------------------------------

    [Theory]
    [InlineData("/media/downloads/complete", "/media/downloads/complete/", true)]
    [InlineData("/media/downloads/complete/", "/media/downloads/complete//tv", true)]
    [InlineData("/media/downloads/complete", "/media/downloads/complete2", false)]
    [InlineData("/Media/downloads/complete", "/media/downloads/complete", false)]
    [InlineData(@"D:\Downloads\Complete", @"d:\downloads\complete\TV", true)]
    [InlineData(@"D:\Downloads\Complete", "d:/downloads/complete", true)]
    [InlineData(@"\\nas\media\complete", @"\\NAS\media\complete\x", true)]
    [InlineData("media/downloads", "media/downloads/x", false)]
    [InlineData("/media/downloads/complete/tv", "/media/downloads/complete", false)]
    public void Contains_is_folder_by_folder_and_ignores_case_only_for_windows_paths(string parent, string child, bool expected) =>
        Assert.Equal(expected, new ArrOsPath(parent).Contains(new ArrOsPath(child)));

    [Fact]
    public void A_mapping_rewrites_only_the_leading_part_of_a_path()
    {
        var mapped = new ArrOsPath("/media/downloads/complete/tv/Show.S01E01").Remap(new ArrOsPath("/media/downloads/complete/"), new ArrOsPath("/media/downloads/weir/"));

        Assert.Equal("/media/downloads/weir/tv/Show.S01E01", mapped.ToString());
    }

    // --- the download clients ----------------------------------------------------------------------

    [Fact]
    public void Download_clients_are_read_from_their_fields_by_name()
    {
        var clients = Clients();

        Assert.Equal(new ArrDownloadClientEntry("qBittorrent", "QBittorrent", true, "qbittorrent", "tv-sonarr", null, "torrent"), clients[0]);
        Assert.Equal(new ArrDownloadClientEntry("SABnzbd", "Sabnzbd", false, "sabnzbd", "tv", null, "usenet"), clients[1]);
        Assert.Equal("movies-radarr", Clients("""[{"enable":true,"name":"q","fields":[{"name":"host","value":"q"},{"name":"movieCategory","value":"movies-radarr"}]}]""", MediaManagerKinds.Movie)[0].Category);
        Assert.Equal("/downloads/tv", Clients("""[{"enable":true,"name":"t","fields":[{"name":"host","value":"t"},{"name":"tvDirectory","value":"/downloads/tv"}]}]""")[0].Directory);
    }

    // --- Sonarr/Radarr ------------------------------------------------------------------------------

    [Fact]
    public void A_mapping_from_the_watched_folder_to_the_output_folder_is_right_and_its_trailing_slash_is_irrelevant()
    {
        var result = Sonarr(
            "/media/downloads/complete",
            "/media/downloads/weir",
            """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""");

        Assert.Equal(["qbittorrent"], result.Hosts);
        Assert.DoesNotContain(result.Lines, line => line.State == SetupCheckLine.Problem);
        Assert.Equal(
            "Sonarr maps /media/downloads/complete/ to /media/downloads/weir/ for \"qbittorrent\", so it looks for these downloads in Weir's output folder.",
            Single(result, SetupCheckLine.Ok));
        Assert.Contains(result.Lines, line => line.Text == "Completed Download Handling is on in Sonarr.");
    }

    [Fact]
    public void A_mapping_one_level_up_covers_a_category_library_when_the_output_mirrors_it()
    {
        var result = Sonarr(
            "/media/downloads/complete/tv",
            "/media/downloads/weir/tv",
            """[{"host":"QBITTORRENT","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""");

        Assert.DoesNotContain(result.Lines, line => line.State == SetupCheckLine.Problem);
    }

    [Fact]
    public void A_mapping_for_a_folder_inside_the_watched_folder_is_checked_against_the_matching_output_folder()
    {
        var right = Sonarr("/media/downloads/complete", "/media/downloads/weir", """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/tv/","localPath":"/media/downloads/weir/tv/","id":1}]""");
        var wrong = Sonarr("/media/downloads/complete", "/media/downloads/weir", """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/tv/","localPath":"/media/downloads/weir/","id":1}]""");

        Assert.DoesNotContain(right.Lines, line => line.State == SetupCheckLine.Problem);
        Assert.Equal(
            "Sonarr maps /media/downloads/complete/tv/ to /media/downloads/weir/, so it will look for these downloads in /media/downloads/weir, " +
            "not in Weir's output folder /media/downloads/weir/tv. Change that mapping's Local Path to match the one above.",
            Single(wrong, SetupCheckLine.Problem));
    }

    [Fact]
    public void A_mapping_that_points_somewhere_else_says_where_sonarr_will_look()
    {
        var result = Sonarr(
            "/media/downloads/complete/tv",
            "/media/downloads/weir/tv",
            """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/data/downloads/","id":1}]""");

        Assert.Equal(
            "Sonarr maps /media/downloads/complete/ to /data/downloads/, so it will look for these downloads in /data/downloads/tv, " +
            "not in Weir's output folder /media/downloads/weir/tv. Change that mapping's Local Path to match the one above.",
            Single(result, SetupCheckLine.Problem));
    }

    [Fact]
    public void No_mapping_says_so_plainly()
    {
        var result = Sonarr("/media/downloads/complete", "/media/downloads/weir", "[]");

        Assert.Equal("Sonarr has no remote path mapping for /media/downloads/complete yet — add the one above.", Single(result, SetupCheckLine.Problem));
    }

    [Fact]
    public void On_linux_a_mapping_that_differs_only_in_case_is_not_a_mapping_for_this_folder()
    {
        var result = Sonarr(
            "/media/Downloads/complete",
            "/media/downloads/weir",
            """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""");

        Assert.Equal("Sonarr has no remote path mapping for /media/Downloads/complete yet — add the one above.", Single(result, SetupCheckLine.Problem));
    }

    [Fact]
    public void A_mapping_for_another_host_names_the_host_it_should_have()
    {
        var result = Sonarr(
            "/media/downloads/complete",
            "/media/downloads/weir",
            """[{"host":"192.168.1.20","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""");

        Assert.Equal(
            "Sonarr maps /media/downloads/complete/ for the host \"192.168.1.20\", but its download client's Host is \"qbittorrent\". " +
            "The mapping's Host has to match it exactly — change it to \"qbittorrent\".",
            Single(result, SetupCheckLine.Problem));
    }

    [Fact]
    public void Completed_download_handling_off_is_a_problem_because_nothing_would_import()
    {
        var result = Sonarr(
            "/media/downloads/complete",
            "/media/downloads/weir",
            """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""",
            cdh: false);

        Assert.Contains(result.Lines, line => line.State == SetupCheckLine.Problem &&
            line.Text == "Completed Download Handling is off in Sonarr, so it will never import from Weir's output. Turn it on under Settings → Download Clients.");
    }

    [Fact]
    public void Without_an_enabled_download_client_there_is_nothing_to_map()
    {
        var result = Sonarr("/media/downloads/complete", "/media/downloads/weir", "[]", clients: [.. Clients().Select(client => client with { Enabled = false })]);

        Assert.Equal("Sonarr has no enabled download client, so it has no downloads to import.", Single(result, SetupCheckLine.Problem));
        Assert.Empty(result.Hosts);
    }

    [Fact]
    public void Missing_folders_are_asked_for_before_anything_else()
    {
        var result = Sonarr("", "/media/downloads/weir", "[]");

        Assert.Equal("Set this library's watched and output folders first; the mapping is built from them.", Assert.Single(result.Lines).Text);
    }

    [Fact]
    public void A_category_the_watched_folder_does_not_name_is_a_note_not_a_problem()
    {
        var mapped = """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""";

        var elsewhere = Sonarr("/media/downloads/complete", "/media/downloads/weir", mapped);
        var named = Sonarr("/media/downloads/complete/tv-sonarr", "/media/downloads/weir/tv-sonarr", mapped);

        Assert.Equal(
            "qBittorrent files Sonarr's downloads under the category \"tv-sonarr\". Sonarr does not say where that category saves, " +
            "so make sure its folder is /media/downloads/complete or inside it.",
            Single(elsewhere, SetupCheckLine.Note));
        Assert.DoesNotContain(named.Lines, line => line.State == SetupCheckLine.Note);
    }

    [Fact]
    public void A_client_directory_outside_the_watched_folder_is_a_problem()
    {
        var transmission = Clients("""[{"enable":true,"name":"Transmission","fields":[{"name":"host","value":"transmission"},{"name":"tvDirectory","value":"/downloads/tv"}]}]""");

        var result = Sonarr(
            "/media/downloads/complete",
            "/media/downloads/weir",
            """[{"host":"transmission","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""",
            clients: transmission);

        Assert.Equal(
            "Transmission saves Sonarr's downloads to /downloads/tv, which is not inside Weir's watched folder /media/downloads/complete. " +
            "Point one at the other, or Weir will never see them.",
            Single(result, SetupCheckLine.Problem));
    }

    [Fact]
    public void Queued_downloads_show_whether_the_mapping_is_being_applied()
    {
        var mapped = """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""";
        var clients = Clients();

        var working = ManagerSetupRules.EvaluateArr(
            "Sonarr", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", Mappings(mapped), clients, true,
            ["/media/downloads/weir/Show.S01E01-GRP", "/media/downloads/weir/Show.S01E02-GRP", ""]);
        var broken = ManagerSetupRules.EvaluateArr(
            "Sonarr", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", Mappings(mapped), clients, true,
            ["/media/downloads/complete/Show.S01E03-GRP"]);

        Assert.Contains(working.Lines, line => line.State == SetupCheckLine.Ok && line.Text == "2 downloads in Sonarr's queue already point at Weir's output folder.");
        Assert.Contains(broken.Lines, line => line.State == SetupCheckLine.Problem &&
            line.Text == "Sonarr is still looking for a download in /media/downloads/complete/Show.S01E03-GRP, inside the watched folder rather than Weir's output, so no mapping is being applied to it.");
    }

    private const string Mapped = """[{"host":"qbittorrent","remotePath":"/media/downloads/complete/","localPath":"/media/downloads/weir/","id":1}]""";

    private const string SeedingProblem =
        "Your download client seeds torrents. Turn off \"After cleaning, remove the original download\" so seeding keeps working and Sonarr can import.";

    [Fact]
    public void A_torrent_client_with_originals_removed_is_a_problem_because_the_import_would_never_happen()
    {
        var removing = ManagerSetupRules.EvaluateArr(
            "Sonarr", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", Mappings(Mapped), Clients(), true, removesOriginals: true);
        var keeping = ManagerSetupRules.EvaluateArr(
            "Sonarr", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", Mappings(Mapped), Clients(), true, removesOriginals: false);

        Assert.Contains(removing.Lines, line => line.State == SetupCheckLine.Problem && line.Text == SeedingProblem);
        Assert.DoesNotContain(keeping.Lines, line => line.State == SetupCheckLine.Problem);
    }

    [Fact]
    public void A_usenet_only_setup_is_not_warned_about_seeding()
    {
        var usenet = Clients("""[{"enable":true,"protocol":"usenet","name":"SABnzbd","fields":[{"name":"host","value":"qbittorrent"},{"name":"tvCategory","value":"tv"}]}]""");
        var disabledTorrent = Clients() is var both ? [both[0] with { Enabled = false }, both[1] with { Enabled = true, Host = "qbittorrent" }] : both;

        var usenetOnly = ManagerSetupRules.EvaluateArr(
            "Sonarr", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", Mappings(Mapped), usenet, true, removesOriginals: true);
        var torrentDisabled = ManagerSetupRules.EvaluateArr(
            "Sonarr", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", Mappings(Mapped), disabledTorrent, true, removesOriginals: true);

        Assert.DoesNotContain(usenetOnly.Lines, line => line.Text == SeedingProblem);
        Assert.DoesNotContain(torrentDisabled.Lines, line => line.Text == SeedingProblem);
    }

    // --- Deluno ---------------------------------------------------------------------------------------

    private static readonly ManagerLibraryDescriptor RefiningTv =
        new("tv-1", "TV", MediaManagerKinds.Tv, "/media/tv", "/media/downloads/weir/tv", true, "/media/downloads/complete/tv");

    [Fact]
    public void A_deluno_library_that_hands_files_over_is_right_when_its_folders_match_and_suggests_them_either_way()
    {
        var right = ManagerSetupRules.EvaluateDeluno("Deluno", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir/tv", [RefiningTv]);
        var wrong = ManagerSetupRules.EvaluateDeluno("Deluno", MediaManagerKinds.Tv, "/media/tv", "/elsewhere", [RefiningTv]);

        Assert.Equal(("/media/downloads/complete/tv", "/media/downloads/weir/tv"), (right.WatchedFolder, right.OutputFolder));
        Assert.All(right.Lines, line => Assert.Equal(SetupCheckLine.Ok, line.State));
        Assert.Equal(
            [
                "TV's downloads arrive in /media/downloads/complete/tv, which is not inside the watched folder, so Weir would refuse its hand-offs. Use Deluno's folders.",
                "Deluno picks up cleaned files from /media/downloads/weir/tv, but this library writes to /elsewhere. Unless both are the same folder seen from two machines, use the same folder.",
            ],
            wrong.Lines.Select(line => line.Text));
    }

    [Fact]
    public void A_deluno_without_a_library_set_to_refine_before_import_will_never_hand_files_over()
    {
        var result = ManagerSetupRules.EvaluateDeluno(
            "Deluno", MediaManagerKinds.Tv, "/media/downloads/complete", "/media/downloads/weir", [RefiningTv with { ProcessesBeforeImport = false }, RefiningTv with { MediaScope = MediaManagerKinds.Movie }]);

        Assert.Equal(
            "No Deluno TV library is set to Refine before import, so Deluno will not hand TV downloads to Weir. Choose Refine before import for that library in Deluno.",
            Assert.Single(result.Lines).Text);
        Assert.Null(result.WatchedFolder);
    }

    [Fact]
    public void Deluno_manifests_carry_the_downloads_folder_beside_the_library_root()
    {
        var descriptor = ManagerDialectRules.ManifestLibraryDescriptor((PyDict)PyJsonParser.Parse(
            """{"id":"lib-1","name":"TV","mediaType":"tv","rootPath":"/media/tv","downloadsPath":"/media/downloads/complete/tv","importWorkflow":"refine-before-import","processorOutputPath":"/media/downloads/weir/tv"}"""));

        Assert.Equal(RefiningTv with { Key = "lib-1" }, descriptor);
    }
}
