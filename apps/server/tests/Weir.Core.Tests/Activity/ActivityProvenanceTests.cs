using Weir.Core.Activity;
using Weir.Core.Json;

namespace Weir.Core.Tests.Activity;

/// <summary>Ports of the provenance and notifier tests in <c>test_activity_triggers.py</c> and <c>test_activity_stream.py</c>.</summary>
public sealed class ActivityProvenanceTests
{
    [Fact]
    public void Only_a_known_trigger_and_a_real_run_are_carried()
    {
        Assert.Equal(
            "{\"trigger\":\"webhook\",\"run_id\":\"scan-4\"}",
            Dump(ActivityProvenance.JobProvenance(PyJsonParser.Parse("{\"trigger\": \"Webhook\", \"run_id\": \"scan-4\"}"))));
        Assert.Equal("{}", Dump(ActivityProvenance.JobProvenance(PyJsonParser.Parse("{\"trigger\": \"because\", \"run_id\": true}"))));
        Assert.Equal("{}", Dump(ActivityProvenance.JobProvenance(new PyStr("not a payload"))));
        Assert.Equal("{}", Dump(ActivityProvenance.JobProvenance(PyJsonParser.Parse("{\"run_id\": \"  \"}"))));
        Assert.Equal("{\"run_id\":0}", Dump(ActivityProvenance.JobProvenance(PyJsonParser.Parse("{\"run_id\": 0}"))));
    }

    [Fact]
    public void A_detail_keeps_what_it_already_says()
    {
        var detail = (PyDict)PyJsonParser.Parse("{\"trigger\": \"worker\", \"x\": 1}");
        Assert.Equal(
            "{\"trigger\":\"worker\",\"run_id\":7,\"x\":1}",
            Dump(ActivityProvenance.WithProvenance(detail, PyJsonParser.Parse("{\"trigger\": \"manual\", \"run_id\": 7}"))));
    }

    [Fact]
    public void A_scans_own_words_map_onto_the_shared_ones()
    {
        Assert.Equal(
            new Dictionary<string, string> { ["manual"] = "manual", ["periodic"] = "scheduled", ["filesystem_event"] = "folder_change" },
            ActivityProvenance.ScanTriggerToTrigger);
    }

    [Fact]
    public async Task The_notifier_wakes_all_active_stream_subscribers()
    {
        var notifier = new ActivityLatestNotifier();
        var first = notifier.WaitForChangeAsync(0, TimeSpan.FromSeconds(5), TimeProvider.System);
        var second = notifier.WaitForChangeAsync(0, TimeSpan.FromSeconds(5), TimeProvider.System);
        Assert.Equal(2, notifier.WaiterCount);

        notifier.Notify(99);

        Assert.Equal(new ActivityLatest(99, 1), await first);
        Assert.Equal(new ActivityLatest(99, 1), await second);
        Assert.Equal(0, notifier.WaiterCount);
    }

    [Fact]
    public async Task The_notifier_removes_timed_out_subscribers_and_answers_at_once_when_behind()
    {
        var notifier = new ActivityLatestNotifier();
        Assert.Null(await notifier.WaitForChangeAsync(0, TimeSpan.FromMilliseconds(1), TimeProvider.System));
        Assert.Equal(0, notifier.WaiterCount);
        Assert.Equal(new ActivityLatest(null, 0), notifier.Snapshot());

        notifier.Notify(5);
        notifier.Notify(4);
        Assert.Equal(new ActivityLatest(4, 2), await notifier.WaitForChangeAsync(1, TimeSpan.FromSeconds(5), TimeProvider.System));
    }

    private static string Dump(PyJson value) => PyJsonWriter.Dumps(value, PyJsonFormat.Response);
}
