using System.Net;
using Weir.Core.LibraryMode;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Tests.MediaManagers;

namespace Weir.Infrastructure.Tests.LibraryMode;

public sealed class RedownloadRiskGatewayTests
{
    private static ManagerConnection Radarr() => new("radarr", "Radarr", "http://localhost:7878", "key");

    private const string MovieFileJson = """
        {
          "id": 42,
          "languages": [{"id": 1, "name": "English"}, {"id": 8, "name": "Japanese"}],
          "customFormats": [
            {
              "id": 9,
              "name": "Multi-Audio",
              "specifications": [
                {
                  "implementation": "LanguageSpecification",
                  "implementationName": "Language",
                  "negate": false,
                  "fields": [{"name": "value", "value": 1}, {"name": "exceptLanguage", "value": true}]
                }
              ]
            }
          ],
          "customFormatScore": 50
        }
        """;

    private const string QualityProfileJson = """
        {
          "id": 4,
          "upgradeAllowed": true,
          "cutoffFormatScore": 60,
          "formatItems": [{"id": 1, "format": 9, "name": "Multi-Audio", "score": 50}]
        }
        """;

    [Fact]
    public async Task Gets_the_moviefile_by_id_for_the_movie_scope()
    {
        var fake = new FakeManagerHttp().Json(HttpMethod.Get, "/api/v3/moviefile/42", MovieFileJson);
        var gateway = new ArrRedownloadRiskGateway(fake);

        var snapshot = await gateway.GetFileFormatSnapshotAsync(Radarr(), MediaManagerKinds.Movie, 42);

        Assert.Equal(["eng", "jpn"], snapshot.AudioLanguages);
        Assert.Equal(50, snapshot.CustomFormatScore);
        Assert.Single(fake.RequestsTo(HttpMethod.Get, "/api/v3/moviefile/42"));
    }

    [Fact]
    public async Task Gets_the_episodefile_by_id_for_the_tv_scope()
    {
        var fake = new FakeManagerHttp().Json(HttpMethod.Get, "/api/v3/episodefile/7", MovieFileJson);
        var gateway = new ArrRedownloadRiskGateway(fake);

        var connection = new ManagerConnection("sonarr", "Sonarr", "http://localhost:8989", "key");
        var snapshot = await gateway.GetFileFormatSnapshotAsync(connection, MediaManagerKinds.Tv, 7);

        Assert.Equal(50, snapshot.CustomFormatScore);
        Assert.Single(fake.RequestsTo(HttpMethod.Get, "/api/v3/episodefile/7"));
    }

    [Fact]
    public async Task Gets_the_quality_profile_by_id()
    {
        var fake = new FakeManagerHttp().Json(HttpMethod.Get, "/api/v3/qualityprofile/4", QualityProfileJson);
        var gateway = new ArrRedownloadRiskGateway(fake);

        var profile = await gateway.GetQualityProfileAsync(Radarr(), 4);

        Assert.True(profile.UpgradeAllowed);
        Assert.Equal(60, profile.CutoffFormatScore);
        Assert.Equal(50, profile.FormatScores[9]);
    }

    [Fact]
    public async Task The_checker_combines_both_calls_into_a_risk_assessment()
    {
        var fake = new FakeManagerHttp()
            .Json(HttpMethod.Get, "/api/v3/moviefile/42", MovieFileJson)
            .Json(HttpMethod.Get, "/api/v3/qualityprofile/4", QualityProfileJson);
        var checker = new RedownloadRiskChecker(new ArrRedownloadRiskGateway(fake));

        var result = await checker.CheckAsync(Radarr(), MediaManagerKinds.Movie, 42, 4, "Blade Runner 2049", ["jpn"], skipIfManagerWouldRedownload: true);

        Assert.True(result.RiskDetected);
        Assert.Equal(
            "Radarr may download Blade Runner 2049 again: its 'Multi-Audio' format (+50) would no longer match.",
            Assert.Single(result.Warnings).Message);
    }

    [Fact]
    public async Task An_unreachable_manager_could_not_be_checked_rather_than_blocking()
    {
        var fake = new FakeManagerHttp().Throw(HttpMethod.Get, "/api/v3/moviefile/42", new HttpRequestException("refused"));
        var checker = new RedownloadRiskChecker(new ArrRedownloadRiskGateway(fake));

        var result = await checker.CheckAsync(Radarr(), MediaManagerKinds.Movie, 42, 4, "Blade Runner 2049", ["jpn"], true);

        Assert.False(result.RiskDetected);
        Assert.False(result.SkipRecommended);
        Assert.Empty(result.Warnings);
        Assert.Single(result.Notes);
    }

    [Fact]
    public async Task A_manager_http_error_is_also_could_not_check()
    {
        var fake = new FakeManagerHttp().Route(HttpMethod.Get, "/api/v3/moviefile/42", _ => FakeManagerHttp.Response(HttpStatusCode.InternalServerError, "oops"));
        var checker = new RedownloadRiskChecker(new ArrRedownloadRiskGateway(fake));

        var result = await checker.CheckAsync(Radarr(), MediaManagerKinds.Movie, 42, 4, "Blade Runner 2049", ["jpn"], true);

        Assert.Empty(result.Warnings);
        Assert.Single(result.Notes);
    }

    [Fact]
    public async Task Deluno_has_no_check_because_its_external_api_exposes_no_equivalent_data()
    {
        // Verified: Deluno's docs/external-integration-api.md lists the whole external surface (manifest, health,
        // queue, activity, import-preview, trigger-refresh, file-changed, processor events) and none of it
        // resembles a quality profile's cutoffFormatScore/upgradeAllowed or a file's customFormatScore.
        var fake = new FakeManagerHttp();
        var checker = new RedownloadRiskChecker(new ArrRedownloadRiskGateway(fake));
        var deluno = new ManagerConnection("deluno", "Deluno", "http://localhost:5000", "key");

        var result = await checker.CheckAsync(deluno, MediaManagerKinds.Movie, 42, 4, "Blade Runner 2049", ["jpn"], true);

        Assert.Same(RedownloadRiskAssessment.NoRisk, result);
        Assert.Empty(fake.Requests);
    }
}
