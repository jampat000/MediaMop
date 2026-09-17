using Weir.Core.Json;
using Weir.Core.LibraryMode;

namespace Weir.Core.Tests.LibraryMode;

/// <summary>
/// Parses fixtures shaped exactly like the verified Sonarr/Radarr schemas (openapi.json's
/// <c>MovieFileResource</c>/<c>EpisodeFileResource</c>, <c>CustomFormatResource</c>,
/// <c>CustomFormatSpecificationSchema</c>, <c>Field</c>, <c>QualityProfileResource</c>,
/// <c>ProfileFormatItemResource</c> — see <see cref="RedownloadRiskDialect"/>'s citations).
/// </summary>
public sealed class RedownloadRiskDialectTests
{
    private const string MovieFileJson = """
        {
          "id": 42,
          "movieId": 7,
          "path": "/movies/Blade Runner 2049/Blade Runner 2049.mkv",
          "size": 12345,
          "languages": [{"id": 1, "name": "English"}, {"id": 8, "name": "Japanese"}],
          "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
          "customFormats": [
            {
              "id": 9,
              "name": "Multi-Audio",
              "specifications": [
                {
                  "id": 1,
                  "name": "not English",
                  "implementation": "LanguageSpecification",
                  "implementationName": "Language",
                  "negate": false,
                  "required": true,
                  "fields": [
                    {"order": 0, "name": "value", "label": "Language", "value": 1},
                    {"order": 1, "name": "exceptLanguage", "label": "Except Language", "value": true}
                  ]
                }
              ]
            }
          ],
          "customFormatScore": 50,
          "qualityCutoffNotMet": false
        }
        """;

    [Fact]
    public void A_moviefile_payload_reads_its_languages_formats_and_score()
    {
        var snapshot = RedownloadRiskDialect.ParseFileFormatSnapshot(PyJsonParser.Parse(MovieFileJson), "radarr");

        Assert.Equal(["eng", "jpn"], snapshot.AudioLanguages);
        Assert.Equal(50, snapshot.CustomFormatScore);
        var format = Assert.Single(snapshot.CustomFormats);
        Assert.Equal(9, format.Id);
        Assert.Equal("Multi-Audio", format.Name);
        var spec = Assert.Single(format.Specifications);
        Assert.Equal("LanguageSpecification", spec.Implementation);
        Assert.False(spec.Negate);
        Assert.True(spec.ExceptLanguage);
        Assert.Equal("eng", spec.LanguageCode);
    }

    [Fact]
    public void The_implementation_field_read_is_the_raw_implementation_name_not_implementationName()
    {
        // RedownloadRiskEvaluator.LanguageImplementation compares against the raw `implementation` value
        // ("LanguageSpecification", the .NET type name Sonarr/Radarr serialize), not `implementationName`
        // ("Language", the display label) — a fixture using the wrong one would silently stop matching anything.
        var snapshot = RedownloadRiskDialect.ParseFileFormatSnapshot(PyJsonParser.Parse(MovieFileJson), "radarr");
        Assert.Equal("LanguageSpecification", snapshot.CustomFormats[0].Specifications[0].Implementation);
    }

    [Fact]
    public void An_unknown_language_id_for_the_managers_kind_resolves_to_a_null_code()
    {
        const string json = """
            {"languages": [{"id": 999, "name": "Nonsense"}], "customFormats": [], "customFormatScore": 0}
            """;
        var snapshot = RedownloadRiskDialect.ParseFileFormatSnapshot(PyJsonParser.Parse(json), "radarr");
        Assert.Empty(snapshot.AudioLanguages);
    }

    [Fact]
    public void Sonarr_and_radarr_disagree_past_id_25_so_the_same_id_reads_a_different_language()
    {
        // Verified from source: both agree up to and including id 23 (Hebrew); Sonarr's id 26 is Arabic,
        // Radarr's id 26 is Hindi.
        Assert.Equal("heb", ArrLanguageCatalog.CanonicalCodeFor("sonarr", 23));
        Assert.Equal("heb", ArrLanguageCatalog.CanonicalCodeFor("radarr", 23));
        Assert.Equal("ara", ArrLanguageCatalog.CanonicalCodeFor("sonarr", 26));
        Assert.Equal("hin", ArrLanguageCatalog.CanonicalCodeFor("radarr", 26));
    }

    [Fact]
    public void Original_unknown_and_any_have_no_fixed_language()
    {
        Assert.Null(ArrLanguageCatalog.CanonicalCodeFor("sonarr", 0)); // Unknown
        Assert.Null(ArrLanguageCatalog.CanonicalCodeFor("sonarr", -2)); // Original
        Assert.Null(ArrLanguageCatalog.CanonicalCodeFor("radarr", -1)); // Any (Radarr only)
    }

    [Fact]
    public void A_quality_profile_payload_reads_cutoff_upgrade_allowed_and_per_format_scores()
    {
        const string json = """
            {
              "id": 4,
              "name": "HD-1080p",
              "upgradeAllowed": true,
              "cutoff": 7,
              "minFormatScore": 0,
              "cutoffFormatScore": 60,
              "minUpgradeFormatScore": 1,
              "formatItems": [
                {"id": 1, "format": 9, "name": "Multi-Audio", "score": 50},
                {"id": 2, "format": 10, "name": "x265", "score": -20}
              ]
            }
            """;

        var profile = RedownloadRiskDialect.ParseQualityProfile(PyJsonParser.Parse(json));

        Assert.True(profile.UpgradeAllowed);
        Assert.Equal(60, profile.CutoffFormatScore);
        Assert.Equal(50, profile.FormatScores[9]);
        Assert.Equal(-20, profile.FormatScores[10]);
    }

    [Fact]
    public void A_missing_payload_reads_as_empty_rather_than_throwing()
    {
        var snapshot = RedownloadRiskDialect.ParseFileFormatSnapshot(null, "radarr");
        Assert.Empty(snapshot.AudioLanguages);
        Assert.Empty(snapshot.CustomFormats);
        Assert.Equal(0, snapshot.CustomFormatScore);

        var profile = RedownloadRiskDialect.ParseQualityProfile(null);
        Assert.False(profile.UpgradeAllowed);
        Assert.Equal(0, profile.CutoffFormatScore);
        Assert.Empty(profile.FormatScores);
    }
}
