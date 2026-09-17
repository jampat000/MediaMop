namespace Weir.Core.LibraryMode;

/// <summary>
/// The combined per-file result issue #508 step 3 shows on the #505 confirmation dialog: whether the file is
/// skipped, why, and any re-download warnings, whether or not they caused the skip.
/// </summary>
public sealed record LibraryFilePreflightResult
{
    public required string FilePath { get; init; }

    public bool Skip { get; init; }

    /// <summary>Every reason this file is skipped (seeding, and/or a re-download risk with the skip setting on).</summary>
    public IReadOnlyList<string> SkipReasons { get; init; } = [];

    /// <summary>Re-download warnings, shown whether or not they caused a skip (the library may allow them through).</summary>
    public IReadOnlyList<RedownloadRiskWarning> RedownloadWarnings { get; init; } = [];

    /// <summary>"Couldn't check" / "can't tell" notes: not warnings, but worth showing next to the file.</summary>
    public IReadOnlyList<string> Notes { get; init; } = [];

    /// <summary>Another name still shares this file's data (#508 step 1), whether or not that caused the skip.</summary>
    public bool Seeding { get; init; }

    /// <summary>Cleaning it would put the title below its quality profile's cutoff (#508 step 2), skip or not.</summary>
    public bool RedownloadRisk { get; init; }

    /// <summary>
    /// The one kind the #568 Problems view files this under, or <see langword="null"/> when nothing is wrong.
    /// Seeding wins when both apply: it is the concrete, local fact, and the one an operator can act on first.
    /// </summary>
    public LibraryProblemKind? ProblemKind => Seeding
        ? LibraryProblemKind.Seeding
        : RedownloadRisk ? LibraryProblemKind.ManagerRedownload : null;
}

/// <summary>
/// Combines the hardlink and re-download checks (issue #508 steps 1-2) into the one preflight result issue #508
/// step 3 asks for, per file. Purely a merge of two already-computed decisions; gathering the link count and the
/// manager data that feed them is issue #505's job.
/// </summary>
public static class LibraryCleanPreflight
{
    public static LibraryFilePreflightResult Evaluate(string filePath, HardlinkDecision hardlink, RedownloadRiskAssessment? redownloadRisk)
    {
        ArgumentNullException.ThrowIfNull(filePath);
        ArgumentNullException.ThrowIfNull(hardlink);

        var reasons = new List<string>();
        if (hardlink.Skip && hardlink.Reason is { } hardlinkReason)
        {
            reasons.Add(hardlinkReason);
        }

        var risk = redownloadRisk ?? RedownloadRiskAssessment.NoRisk;
        if (risk.SkipRecommended)
        {
            reasons.AddRange(risk.Warnings.Select(warning => warning.Message));
        }

        return new LibraryFilePreflightResult
        {
            FilePath = filePath,
            Skip = reasons.Count > 0,
            SkipReasons = reasons,
            RedownloadWarnings = risk.Warnings,
            Notes = risk.Notes,
            Seeding = hardlink.Skip,
            RedownloadRisk = risk.RiskDetected,
        };
    }
}
