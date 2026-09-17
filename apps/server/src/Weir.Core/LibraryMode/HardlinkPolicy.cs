namespace Weir.Core.LibraryMode;

/// <summary>Whether a library file should be skipped because another name shares its data (issue #508 step 1).</summary>
public sealed record HardlinkDecision(bool Skip, string? Reason)
{
    public static readonly HardlinkDecision Allow = new(false, null);
}

/// <summary>
/// The hardlink half of library-mode preflight (issue #508). A link count above one means another directory
/// entry — almost always a download client's still-seeding copy — points at the same data on disk. An in-place
/// swap there does not free anything: the original bytes stay allocated under the other name, so cleaning doubles
/// disk use instead of reducing it. Pure decision logic; the link count itself comes from the filesystem
/// (<c>Weir.Infrastructure.LibraryMode.IHardlinkInspector</c>, which forwards to the crash-safe swap's own
/// <c>ISwapFileSystem.LinkCount</c> — see that type's remarks for the two platform reads this uses).
/// </summary>
public static class HardlinkPolicy
{
    /// <summary>The default skip reason (issue #508 step 1's exact wording).</summary>
    public const string SeedingReason = "still shared with a download (seeding)";

    /// <param name="linkCount">
    /// Hard links to the file, or <see langword="null"/> when the platform or filesystem cannot say (an
    /// unsupported volume, or a failed probe). Unknown is treated the same as a link count of one: Weir does not
    /// block a clean it cannot justify with actual evidence of sharing.
    /// </param>
    /// <param name="cleanHardlinkedFiles">
    /// The per-library <c>clean_hardlinked_files</c> setting (issue #508 step 1; default <see langword="false"/>).
    /// Persisting this setting is issue #505's job — it is a plain parameter here.
    /// </param>
    public static HardlinkDecision Evaluate(int? linkCount, bool cleanHardlinkedFiles)
    {
        var sharedWithAnotherName = linkCount is > 1;
        return sharedWithAnotherName && !cleanHardlinkedFiles
            ? new HardlinkDecision(Skip: true, Reason: SeedingReason)
            : HardlinkDecision.Allow;
    }
}
