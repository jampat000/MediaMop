using Weir.Core.LibraryMode;
using Weir.Core.Refiner;

namespace Weir.Core.Tests.LibraryMode;

public sealed class LibraryModeSettingsTests
{
    private static RefinerLibraryRecord Library() => new()
    {
        Name = "Movies",
        WatchedFolder = "/data/watched",
        WorkFolder = "/data/work",
        OutputFolder = "/data/output",
    };

    [Fact]
    public void A_library_folder_that_overlaps_the_watched_folder_is_refused()
    {
        var exception = Assert.Throws<LibraryModeException>(() => LibraryFolderRules.Validate(["/data/watched/sub"], Library()));
        Assert.Contains("watched", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_library_folder_that_overlaps_the_output_folder_is_refused()
    {
        Assert.Throws<LibraryModeException>(() => LibraryFolderRules.Validate(["/data/output"], Library()));
    }

    [Fact]
    public void Separate_folders_are_accepted_deduplicated_and_trimmed()
    {
        var result = LibraryFolderRules.Validate([" /data/library-a ", "/data/library-b", "/data/library-a"], Library());
        Assert.Equal(["/data/library-a", "/data/library-b"], result);
    }

    [Fact]
    public void Library_folders_may_be_the_same_folder_a_manager_uses_or_another_library_uses()
    {
        // #505: "These may be the same folders a manager uses, or not" — only overlap with THIS library's own
        // watched/work/output folders is refused; nothing here checks other libraries or managers.
        var result = LibraryFolderRules.Validate(["/data/shared-with-radarr"], Library());
        Assert.Equal(["/data/shared-with-radarr"], result);
    }

    [Fact]
    public void Settings_round_trip_through_json()
    {
        var settings = new LibrarySettings(["/data/library-a", "/data/library-b"], ScheduleEnabled: true);
        var payload = settings.ToPayload(libraryId: 7);
        var restored = LibrarySettings.FromPayload(payload);
        Assert.Equal(settings.Folders, restored.Folders);
        Assert.Equal(settings.ScheduleEnabled, restored.ScheduleEnabled);
    }

    [Fact]
    public void Empty_settings_come_back_from_a_missing_payload()
    {
        var restored = LibrarySettings.FromPayload(null);
        Assert.Empty(restored.Folders);
        Assert.False(restored.ScheduleEnabled);
    }

    [Fact]
    public void Library_jobs_always_sort_behind_a_freshly_enqueued_download_job()
    {
        // refiner_jobs is claimed ORDER BY priority DESC, id ASC, and a retried download job's priority is only ever
        // bumped up (to max(pending) + 1), so this very low, fixed priority can never be overtaken from below.
        Assert.True(LibraryModePriority.Low < 0);
    }
}
