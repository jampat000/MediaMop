using Weir.Core.Refiner;

namespace Weir.Core.Tests.Refiner;

/// <summary>Ported assertions from <c>refiner_library_crud.py</c>'s <c>_validate_folders</c>,
/// <c>_validate_name</c> and <c>_validate_scope</c> (#460, ADR-0014).</summary>
public sealed class LibraryRulesTests
{
    [Fact]
    public void A_library_named_after_an_existing_one_is_refused()
    {
        var exception = Assert.Throws<RefinerLibraryException>(() => LibraryRules.ValidateName("Movies", ["Movies", "TV"]));
        Assert.Contains("already exists", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_blank_name_is_refused() =>
        Assert.Throws<RefinerLibraryException>(() => LibraryRules.ValidateName("   ", []));

    [Fact]
    public void An_unknown_media_type_is_refused() =>
        Assert.Throws<RefinerLibraryException>(() => LibraryRules.ValidateScope("anime"));

    [Theory]
    [InlineData("movie")]
    [InlineData("MOVIE")]
    [InlineData("tv")]
    [InlineData(" TV ")]
    public void A_known_media_type_normalizes_to_lowercase(string raw) =>
        Assert.Contains(LibraryRules.ValidateScope(raw), RefinerMediaScopes.All);

    [Fact]
    public void A_watched_folder_with_no_output_folder_is_refused()
    {
        var exception = Assert.Throws<RefinerLibraryException>(() =>
            LibraryRules.ValidateFolders(@"C:\media\watched", null, null, []));
        Assert.Contains("output folder", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_librarys_own_watched_and_output_folders_may_not_overlap()
    {
        var exception = Assert.Throws<RefinerLibraryException>(() =>
            LibraryRules.ValidateFolders(@"C:\media\shared", null, @"C:\media\shared\output", []));
        Assert.Contains("overlap", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Nested_folders_are_reported_as_overlapping_either_direction()
    {
        Assert.True(LibraryRules.FoldersOverlap("c:/media/a", "c:/media/a/b"));
        Assert.True(LibraryRules.FoldersOverlap("c:/media/a/b", "c:/media/a"));
        Assert.True(LibraryRules.FoldersOverlap("c:/media/a", "c:/media/a"));
        Assert.False(LibraryRules.FoldersOverlap("c:/media/a", "c:/media/b"));
    }

    [Fact]
    public void A_second_librarys_watched_folder_may_not_overlap_the_first()
    {
        var others = new[] { new OtherLibraryFolders(1, "Movies", @"C:\media\movies", @"C:\media\movies-out") };
        var exception = Assert.Throws<RefinerLibraryException>(() =>
            LibraryRules.ValidateFolders(@"C:\media\movies\extras", @"C:\work", @"C:\media\tv-out", others));
        Assert.Contains("Movies", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Unrelated_folders_across_libraries_are_accepted()
    {
        var others = new[] { new OtherLibraryFolders(1, "Movies", @"C:\media\movies", @"C:\media\movies-out") };
        LibraryRules.ValidateFolders(@"C:\media\tv", @"C:\work", @"C:\media\tv-out", others);
    }

    [Fact]
    public void Empty_folders_never_overlap_anything()
    {
        var others = new[] { new OtherLibraryFolders(1, "Movies", string.Empty, string.Empty) };
        LibraryRules.ValidateFolders(string.Empty, string.Empty, string.Empty, others);
    }

    [Theory]
    [InlineData(@"C:\Media\Watched", @"c:/media/watched")]
    [InlineData(@"C:\Media\Watched\", @"c:/media/watched")]
    public void Folder_normalization_is_case_insensitive_and_trims_trailing_separators(string raw, string expected) =>
        Assert.Equal(expected, LibraryRules.NormalizeFolder(raw));

    [Fact]
    public void Manager_connections_are_deduplicated_and_sorted()
    {
        var result = LibraryRules.ValidateManagerConnections([3, 1, 3, 2], new HashSet<long> { 1, 2, 3 });
        Assert.Equal([1L, 2L, 3L], result);
    }

    [Fact]
    public void An_unknown_manager_connection_is_refused()
    {
        var exception = Assert.Throws<RefinerLibraryException>(() =>
            LibraryRules.ValidateManagerConnections([5], new HashSet<long> { 1, 2 }));
        Assert.Contains("5", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void An_empty_manager_connection_list_needs_no_lookup() =>
        Assert.Empty(LibraryRules.ValidateManagerConnections([], new HashSet<long>()));

    [Fact]
    public void A_rule_set_id_that_does_not_exist_is_refused() =>
        Assert.Throws<RefinerLibraryException>(() => LibraryRules.ValidateRuleSet(99, exists: false));

    [Fact]
    public void A_null_rule_set_id_is_always_accepted() =>
        Assert.Null(LibraryRules.ValidateRuleSet(null, exists: false));
}
