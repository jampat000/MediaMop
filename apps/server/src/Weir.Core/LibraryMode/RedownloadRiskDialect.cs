using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Core.LibraryMode;

/// <summary>
/// The phrasing half of the re-download-risk manager calls (issue #508 step 2), in the same split as
/// <see cref="ManagerDialectRules"/>: reading Sonarr/Radarr JSON into the neutral shapes
/// <see cref="RedownloadRiskEvaluator"/> works with. The HTTP half lives in
/// <c>Weir.Infrastructure.LibraryMode.ArrRedownloadRiskGateway</c>.
/// </summary>
public static class RedownloadRiskDialect
{
    /// <summary>
    /// A file resource's <c>customFormats</c>/<c>customFormatScore</c>/<c>languages</c>
    /// (Sonarr <c>EpisodeFileResource</c>, openapi.json:8498 at v5-develop; Radarr <c>MovieFileResource</c>,
    /// openapi.json:10819 at develop).
    /// </summary>
    public static FileFormatSnapshot ParseFileFormatSnapshot(PyJson? payload, string managerKind)
    {
        if (payload is not PyDict file)
        {
            return new FileFormatSnapshot([], [], 0);
        }

        var languages = PyValues.Dicts(file.Get("languages"))
            .Select(language => PyValues.FirstNumber(language, "id"))
            .OfType<System.Numerics.BigInteger>()
            .Select(id => ArrLanguageCatalog.CanonicalCodeFor(managerKind, (int)id))
            .OfType<string>()
            .ToList();

        var customFormats = PyValues.Dicts(file.Get("customFormats"))
            .Select(format => ParseCustomFormat(format, managerKind))
            .ToList();

        var score = (int)(PyValues.WholeNumber(file.Get("customFormatScore")) ?? 0);
        return new FileFormatSnapshot(languages, customFormats, score);
    }

    private static CustomFormatSnapshot ParseCustomFormat(PyDict format, string managerKind)
    {
        var id = PyValues.WholeNumber(format.Get("id")) ?? 0;
        var name = PyValues.Text(format.Get("name")) ?? string.Empty;
        var specifications = PyValues.Dicts(format.Get("specifications"))
            .Select(specification => ParseSpecification(specification, managerKind))
            .ToList();
        return new CustomFormatSnapshot((long)id, name, specifications);
    }

    private static FormatSpecificationSnapshot ParseSpecification(PyDict specification, string managerKind)
    {
        var implementation = PyValues.Text(specification.Get("implementation")) ?? string.Empty;
        var negate = specification.Get("negate")?.IsTruthy ?? false;
        if (implementation != RedownloadRiskEvaluator.LanguageImplementation)
        {
            return new FormatSpecificationSnapshot(implementation, negate, LanguageCode: null, ExceptLanguage: false);
        }

        var fields = PyValues.Dicts(specification.Get("fields"));
        var valueField = fields.FirstOrDefault(field => string.Equals(PyValues.Text(field.Get("name")), "value", StringComparison.OrdinalIgnoreCase));
        var exceptLanguageField = fields.FirstOrDefault(field =>
            string.Equals(PyValues.Text(field.Get("name")), "exceptLanguage", StringComparison.OrdinalIgnoreCase));

        var languageCode = valueField is not null && PyValues.WholeNumber(valueField.Get("value")) is { } languageId
            ? ArrLanguageCatalog.CanonicalCodeFor(managerKind, (int)languageId)
            : null;
        var exceptLanguage = exceptLanguageField?.Get("value")?.IsTruthy ?? false;
        return new FormatSpecificationSnapshot(implementation, negate, languageCode, exceptLanguage);
    }

    /// <summary>
    /// A quality profile's <c>upgradeAllowed</c>/<c>cutoffFormatScore</c>/<c>formatItems</c>
    /// (<c>QualityProfileResource</c>, openapi.json:10800 at v5-develop; :11665 at develop). <c>formatItems</c>'
    /// <c>format</c> field is the custom format id the score applies to (<c>ProfileFormatItemResource</c>,
    /// openapi.json:10616 / :11493).
    /// </summary>
    public static QualityProfileSnapshot ParseQualityProfile(PyJson? payload)
    {
        if (payload is not PyDict profile)
        {
            return new QualityProfileSnapshot(UpgradeAllowed: false, CutoffFormatScore: 0, FormatScores: new Dictionary<long, int>());
        }

        var upgradeAllowed = profile.Get("upgradeAllowed")?.IsTruthy ?? false;
        var cutoff = (int)(PyValues.WholeNumber(profile.Get("cutoffFormatScore")) ?? 0);
        var scores = new Dictionary<long, int>();
        foreach (var item in PyValues.Dicts(profile.Get("formatItems")))
        {
            if (PyValues.WholeNumber(item.Get("format")) is not { } formatId)
            {
                continue;
            }

            var score = (int)(PyValues.WholeNumber(item.Get("score")) ?? 0);
            scores[(long)formatId] = score;
        }

        return new QualityProfileSnapshot(upgradeAllowed, cutoff, scores);
    }
}
