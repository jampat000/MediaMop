using Weir.Core.Json;
using Weir.Core.Processing;

namespace Weir.Core.Tests.Processing;

/// <summary>Ported behavior from <c>processing_file_story.py</c> (#468): narrate a stored pass record in
/// plain language, never raising on a partial or malformed one.</summary>
public sealed class FileStoryTests
{
    [Fact]
    public void An_empty_record_with_no_library_name_produces_no_steps() => Assert.Empty(FileStory.NarratePass(new PyDict(), string.Empty));

    [Fact]
    public void An_empty_record_still_reports_where_the_file_was_picked_up_when_a_library_name_is_known()
    {
        // _picked_up runs regardless of "ok" and needs only a library name or a media scope to say something.
        var step = Assert.Single(FileStory.NarratePass(new PyDict(), "Movies"));
        Assert.Equal("Picked up", step.Heading);
        Assert.Equal("Weir took this file in the Movies library.", step.Sentence);
    }

    [Fact]
    public void A_successful_pass_reports_picked_up_and_worked_steps()
    {
        var detail = new PyDict()
            .Set("ok", true)
            .Set("media_scope", "movie")
            .Set("elapsed_seconds", 12.0)
            .Set("source_size_bytes", 2000.0)
            .Set("output_size_bytes", 1000.0);

        var steps = FileStory.NarratePass(detail, "Movies");

        var pickedUp = Assert.Single(steps, s => s.Heading == "Picked up");
        Assert.Contains("Movies", pickedUp.Sentence, StringComparison.Ordinal);
        Assert.Contains("film", pickedUp.Sentence, StringComparison.Ordinal);

        var worked = Assert.Single(steps, s => s.Heading == "Worked");
        Assert.Equal(StoryTone.Good, worked.Tone);
        Assert.Contains("saving", worked.Sentence, StringComparison.Ordinal);
    }

    [Fact]
    public void A_failed_pass_reports_the_reason_with_a_bad_tone()
    {
        // No library name: _picked_up has nothing to say, so the failure is the only step.
        var detail = new PyDict().Set("ok", false).Set("reason", "No retainable audio track.");

        var steps = FileStory.NarratePass(detail, string.Empty);

        var failed = Assert.Single(steps);
        Assert.Equal("Could not finish", failed.Heading);
        Assert.Equal("No retainable audio track.", failed.Sentence);
        Assert.Equal(StoryTone.Bad, failed.Tone);
    }

    [Fact]
    public void A_failed_pass_with_no_reason_gets_a_generic_sentence_rather_than_a_blank_one()
    {
        var steps = FileStory.NarratePass(new PyDict().Set("ok", false), string.Empty);

        var failed = Assert.Single(steps);
        Assert.Equal("Weir could not process this file, and the record does not say why.", failed.Sentence);
    }

    [Fact]
    public void A_pass_that_needed_no_changes_is_reported_as_good_news()
    {
        var detail = new PyDict().Set("ok", true).Set("remux_required", false);

        var planned = Assert.Single(FileStory.NarratePass(detail, "Movies"), s => s.Heading == "Planned");
        Assert.Equal(StoryTone.Good, planned.Tone);
        Assert.Contains("nothing to change", planned.Sentence, StringComparison.Ordinal);
    }

    [Fact]
    public void Stream_copy_is_only_claimed_when_the_argv_proves_it()
    {
        var detailWithCopy = new PyDict()
            .Set("ok", true)
            .Set("remux_required", true)
            .Set("removed_audio", new PyList([PyJson.Of("commentary")]))
            .Set("ffmpeg_argv", new PyList([PyJson.Of("-c:v"), PyJson.Of("copy")]));
        var planned = Assert.Single(FileStory.NarratePass(detailWithCopy, "Movies"), s => s.Heading == "Planned");
        Assert.Contains("not re-encoded", planned.Sentence, StringComparison.Ordinal);

        var detailWithoutArgv = new PyDict()
            .Set("ok", true)
            .Set("remux_required", true)
            .Set("removed_audio", new PyList([PyJson.Of("commentary")]));
        var plannedNoProof = Assert.Single(FileStory.NarratePass(detailWithoutArgv, "Movies"), s => s.Heading == "Planned");
        Assert.DoesNotContain("not re-encoded", plannedNoProof.Sentence, StringComparison.Ordinal);
    }

    [Fact]
    public void An_unparseable_field_is_skipped_rather_than_throwing()
    {
        // narrate_pass never raises on a partial record: garbage in a numeric-looking field is ignored.
        var detail = new PyDict().Set("ok", true).Set("elapsed_seconds", "not-a-number");
        var steps = FileStory.NarratePass(detail, "Movies");
        Assert.DoesNotContain(steps, s => s.Heading == "Worked");
    }
}
