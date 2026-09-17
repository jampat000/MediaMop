using Weir.Core.Refiner;

namespace Weir.Core.Tests.Refiner;

/// <summary>
/// Fixes #530: <c>passed_through</c> and <c>rejected</c> must be valid Refiner file statuses in both
/// responses and filters, matching Python's <c>RefinerFileStatus</c> enum in full. The Python response and
/// query schemas (<c>RefinerFileStatusName</c>) omitted them, which 500'd a file at either status and
/// 422'd a filter naming one — this is the assertion that the .NET port does not reproduce that gap.
/// </summary>
public sealed class FileStatusesTests
{
    [Fact]
    public void All_eleven_python_statuses_are_present()
    {
        Assert.Equal(
            [
                "unprocessed", "processing", "processed", "processing_failed", "skipped", "disabled",
                "on_hold", "out_of_schedule", "blocked_upstream", "passed_through", "rejected",
            ],
            RefinerFileStatuses.All);
    }

    [Theory]
    [InlineData(RefinerFileStatuses.PassedThrough)]
    [InlineData(RefinerFileStatuses.Rejected)]
    public void Terminal_bug_530_statuses_are_valid_status_values(string status) => Assert.Contains(status, RefinerFileStatuses.All);

    [Fact]
    public void Withheld_statuses_do_not_include_the_two_terminal_ones()
    {
        // passed_through and rejected are terminal outcomes, not "Weir decided not to act yet" states.
        Assert.DoesNotContain(RefinerFileStatuses.PassedThrough, RefinerFileStatuses.Withheld);
        Assert.DoesNotContain(RefinerFileStatuses.Rejected, RefinerFileStatuses.Withheld);
    }
}
