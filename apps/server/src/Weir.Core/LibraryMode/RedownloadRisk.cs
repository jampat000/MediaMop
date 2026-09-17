using System.Globalization;
using Weir.Core.Rules;

namespace Weir.Core.LibraryMode;

/// <summary>
/// One specification inside a matched custom format's <c>specifications</c> array
/// (Sonarr <c>components.schemas.CustomFormatSpecificationSchema</c>, openapi.json:8192 at v5-develop; Radarr
/// same shape at openapi.json:9006, develop). <see cref="LanguageCode"/> is Weir's canonical form
/// (<see cref="OriginalLanguage.CanonicalLanguage"/>) of the specification's language <c>Value</c> field, resolved
/// by the caller through <see cref="ArrLanguageCatalog"/>; it is <see langword="null"/> for a non-language
/// specification, and also for a language specification whose <c>Value</c> this port cannot confidently place
/// (an id outside the curated table, or the dynamic "Original" / "Unknown" / "Any" entries, which depend on the
/// title's own metadata rather than a fixed language).
/// </summary>
public sealed record FormatSpecificationSnapshot(string Implementation, bool Negate, string? LanguageCode, bool ExceptLanguage);

/// <summary>
/// One custom format matched on the file today (Sonarr/Radarr <c>CustomFormatResource</c>,
/// openapi.json:8167 / :8981). <see cref="Id"/> joins against <see cref="QualityProfileSnapshot.FormatScores"/>
/// (the profile's own <c>formatItems</c>, which is where the score actually lives — the file's embedded
/// <c>CustomFormatResource</c> carries no score of its own).
/// </summary>
public sealed record CustomFormatSnapshot(long Id, string Name, IReadOnlyList<FormatSpecificationSnapshot> Specifications);

/// <summary>
/// What Weir read from the manager about one library file before a clean (issue #508 step 2): its current audio
/// languages, the custom formats matched against it today, and the total score the manager already computed for
/// it (Sonarr <c>EpisodeFileResource</c>/<c>customFormatScore</c>, openapi.json:8498; Radarr
/// <c>MovieFileResource</c>/<c>customFormatScore</c>, openapi.json:10819). <see cref="AudioLanguages"/> are Weir's
/// canonical codes for the file resource's own <c>languages</c> array.
/// </summary>
public sealed record FileFormatSnapshot(IReadOnlyList<string> AudioLanguages, IReadOnlyList<CustomFormatSnapshot> CustomFormats, int CustomFormatScore);

/// <summary>
/// The title's quality profile (Sonarr/Radarr <c>QualityProfileResource</c>, openapi.json:10800 / :11665):
/// whether an upgrade search can ever fire, the score a file must clear to avoid one, and each matched format's
/// point value (<c>formatItems[].format</c> -&gt; <c>formatItems[].score</c>, <c>ProfileFormatItemResource</c>,
/// openapi.json:10616 / :11493).
/// </summary>
public sealed record QualityProfileSnapshot(bool UpgradeAllowed, int CutoffFormatScore, IReadOnlyDictionary<long, int> FormatScores);

/// <summary>One format the manager would stop matching, in the exact wording issue #508 specifies.</summary>
public sealed record RedownloadRiskWarning(string ManagerLabel, string TitleName, string FormatName, int FormatScore)
{
    /// <summary>e.g. "Radarr may download Blade Runner 2049 again: its 'Multi-Audio' format (+50) would no longer match."</summary>
    public string Message
    {
        get
        {
            var points = FormatScore >= 0
                ? "+" + FormatScore.ToString(CultureInfo.InvariantCulture)
                : FormatScore.ToString(CultureInfo.InvariantCulture);
            return $"{ManagerLabel} may download {TitleName} again: its '{FormatName}' format ({points}) would no longer match.";
        }
    }
}

/// <summary>The outcome of one redownload-risk check (issue #508 step 2 / step 3's per-file result).</summary>
public sealed record RedownloadRiskAssessment
{
    /// <summary>The predicted score would drop below the profile's cutoff, with upgrades allowed.</summary>
    public bool RiskDetected { get; init; }

    /// <summary><see cref="RiskDetected"/> and the library's <c>skip_if_manager_would_redownload</c> is on.</summary>
    public bool SkipRecommended { get; init; }

    public IReadOnlyList<RedownloadRiskWarning> Warnings { get; init; } = [];

    /// <summary>Plain-language notes that are not warnings: "couldn't check" and per-format "can't tell" lines.</summary>
    public IReadOnlyList<string> Notes { get; init; } = [];

    public int? PredictedScore { get; init; }

    /// <summary>The manager could not be asked; issue #508's "couldn't check", not blocking.</summary>
    public static RedownloadRiskAssessment CouldNotCheck(string managerLabel) => new()
    {
        Notes = [$"Weir couldn't check whether {managerLabel} would download this again."],
    };

    /// <summary>Nothing to evaluate against (no manager owns this file, or no tracks are being removed).</summary>
    public static readonly RedownloadRiskAssessment NoRisk = new();
}

/// <summary>
/// The re-download-risk half of library-mode preflight (issue #508 step 2): predicts whether removing audio
/// tracks would drop a Sonarr/Radarr file's custom-format score below its quality profile's cutoff, which (with
/// upgrades allowed) makes the manager search for and download the release again. Pure logic — the manager calls
/// that gather <see cref="FileFormatSnapshot"/> and <see cref="QualityProfileSnapshot"/> belong to
/// <c>Weir.Infrastructure.LibraryMode.IRedownloadRiskGateway</c>, whose failure (including "manager unreachable")
/// is <see cref="RedownloadRiskAssessment.CouldNotCheck"/>, produced there rather than here.
/// </summary>
public static class RedownloadRiskEvaluator
{
    /// <summary>
    /// The <c>specifications[].implementation</c> value for a language specification: the C# type name, not the
    /// display label. Verified from the resource mapper both products ship, which is identical apart from the
    /// namespace: <c>Implementation = model.GetType().Name</c>, <c>ImplementationName = model.ImplementationName</c>
    /// (Sonarr <c>src/Sonarr.Api.V3/CustomFormats/CustomFormatSpecificationSchema.cs:27-28</c> at v5-develop;
    /// Radarr same path under <c>Radarr.Api.V3</c>, line 27, at develop) — <c>LanguageSpecification</c>'s own
    /// <c>ImplementationName</c> override is the display label <c>"Language"</c>
    /// (<c>Specifications/LanguageSpecification.cs:28</c>), which is a different field on the wire.
    /// </summary>
    public const string LanguageImplementation = "LanguageSpecification";

    /// <summary>
    /// Every other specification implementation Sonarr and Radarr ship, by the same <c>GetType().Name</c> the wire
    /// carries (verified: both repos' <c>src/NzbDrone.Core/CustomFormats/Specifications</c> directory listings,
    /// v5-develop / develop — <c>ReleaseTypeSpecification</c> is Sonarr-only; <c>EditionSpecification</c>,
    /// <c>QualityModifierSpecification</c> and <c>YearSpecification</c> are Radarr-only). None of these read audio
    /// or subtitle tracks, so removing tracks cannot change whether they are satisfied. An implementation name
    /// outside this set (and not <see cref="LanguageImplementation"/>) is unrecognised — evaluation for that
    /// format stops at "can't tell" rather than assuming it is unaffected.
    /// </summary>
    private static readonly HashSet<string> KnownTrackIndependentSpecifications = new(StringComparer.Ordinal)
    {
        "ReleaseGroupSpecification", "ReleaseTitleSpecification", "ReleaseTypeSpecification", "ResolutionSpecification",
        "SizeSpecification", "SourceSpecification", "IndexerFlagSpecification", "EditionSpecification",
        "QualityModifierSpecification", "YearSpecification",
    };

    private enum FormatOutcome
    {
        StillMatches,
        Lost,
        CantTell,
    }

    /// <param name="managerLabel">e.g. "Radarr" or "Radarr (4K)" (<c>MediaManagerKinds.LabelForConnection</c>).</param>
    /// <param name="titleName">The title as the manager names it, e.g. "Blade Runner 2049".</param>
    /// <param name="snapshot">The file's manager-reported languages, matched custom formats and current score.</param>
    /// <param name="profile">The title's quality profile: cutoff, whether upgrades are allowed, and format scores.</param>
    /// <param name="removedAudioLanguages">
    /// The languages of the audio tracks the plan would remove, in whatever form Weir's rules engine already
    /// carries them; canonicalised the same way <see cref="OriginalLanguage.CanonicalLanguage"/> canonicalises
    /// <paramref name="snapshot"/>'s languages, so "jpn", "ja" and "JPN" all compare equal.
    /// </param>
    /// <param name="skipIfManagerWouldRedownload">The library's <c>skip_if_manager_would_redownload</c> setting (default true).</param>
    public static RedownloadRiskAssessment Evaluate(
        string managerLabel,
        string titleName,
        FileFormatSnapshot snapshot,
        QualityProfileSnapshot profile,
        IReadOnlyCollection<string> removedAudioLanguages,
        bool skipIfManagerWouldRedownload)
    {
        ArgumentNullException.ThrowIfNull(managerLabel);
        ArgumentNullException.ThrowIfNull(titleName);
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(profile);
        ArgumentNullException.ThrowIfNull(removedAudioLanguages);

        if (removedAudioLanguages.Count == 0)
        {
            return RedownloadRiskAssessment.NoRisk;
        }

        var removed = new HashSet<string>(removedAudioLanguages.Select(OriginalLanguage.CanonicalLanguage), StringComparer.Ordinal);
        var remainingLanguages = snapshot.AudioLanguages
            .Select(OriginalLanguage.CanonicalLanguage)
            .Where(code => !removed.Contains(code))
            .ToList();

        var lostFormats = new List<(string Name, int Score)>();
        var notes = new List<string>();
        var predictedScore = snapshot.CustomFormatScore;

        foreach (var format in snapshot.CustomFormats)
        {
            var outcome = Predict(format, remainingLanguages);
            if (outcome == FormatOutcome.CantTell)
            {
                notes.Add($"Weir can't tell whether the '{format.Name}' format would still match after this clean.");
                continue;
            }

            if (outcome == FormatOutcome.Lost)
            {
                var score = profile.FormatScores.GetValueOrDefault(format.Id, 0);
                lostFormats.Add((format.Name, score));
                predictedScore -= score;
            }
        }

        var riskDetected = profile.UpgradeAllowed && lostFormats.Count > 0 && predictedScore < profile.CutoffFormatScore;
        var warnings = riskDetected
            ? lostFormats.Select(lost => new RedownloadRiskWarning(managerLabel, titleName, lost.Name, lost.Score)).ToList()
            : [];

        return new RedownloadRiskAssessment
        {
            RiskDetected = riskDetected,
            SkipRecommended = riskDetected && skipIfManagerWouldRedownload,
            Warnings = warnings,
            Notes = notes,
            PredictedScore = predictedScore,
        };
    }

    private static FormatOutcome Predict(CustomFormatSnapshot format, IReadOnlyList<string> remainingLanguages)
    {
        var languageSpecs = new List<FormatSpecificationSnapshot>();
        foreach (var spec in format.Specifications)
        {
            if (string.Equals(spec.Implementation, LanguageImplementation, StringComparison.Ordinal))
            {
                languageSpecs.Add(spec);
                continue;
            }

            if (!KnownTrackIndependentSpecifications.Contains(spec.Implementation))
            {
                return FormatOutcome.CantTell;
            }
        }

        if (languageSpecs.Count == 0)
        {
            // No specification here reads a track, so removing tracks cannot change whether this format matches.
            return FormatOutcome.StillMatches;
        }

        foreach (var spec in languageSpecs)
        {
            if (spec.LanguageCode is null)
            {
                // An id this port could not place (outside the curated table, or "Original"/"Unknown"/"Any",
                // which need title metadata this evaluator does not have).
                return FormatOutcome.CantTell;
            }

            // The format was matched today, so every specification (this one included) was satisfied before the
            // removal; a specification that would no longer be satisfied loses the whole format, since Sonarr and
            // Radarr require every specification to pass.
            if (!SatisfiedAfterRemoval(spec, remainingLanguages))
            {
                return FormatOutcome.Lost;
            }
        }

        return FormatOutcome.StillMatches;
    }

    /// <summary>
    /// <c>LanguageSpecification.IsSatisfiedByWithoutNegate</c> / <c>IsSatisfiedByWithNegate</c> (Sonarr
    /// src/NzbDrone.Core/CustomFormats/Specifications/LanguageSpecification.cs:46-70 at v5-develop; Radarr same
    /// path and lines at develop): without <c>ExceptLanguage</c>, satisfied when the compared language is one of
    /// the file's audio languages; with it, satisfied when some *other* language is present — the shape TRaSH's
    /// "Multi-Audio" formats use ("has audio that isn't English"). The two negated methods are exactly the
    /// negation of their non-negated counterparts, so applying <see cref="FormatSpecificationSnapshot.Negate"/>
    /// (the specification's own <c>negate</c> field, not <c>ExceptLanguage</c>) after computing the un-negated
    /// answer reproduces both without duplicating the branch.
    /// </summary>
    private static bool SatisfiedAfterRemoval(FormatSpecificationSnapshot spec, IReadOnlyList<string> remainingLanguages)
    {
        var satisfied = spec.ExceptLanguage
            ? remainingLanguages.Any(code => code != spec.LanguageCode)
            : remainingLanguages.Contains(spec.LanguageCode);
        return spec.Negate ? !satisfied : satisfied;
    }
}
