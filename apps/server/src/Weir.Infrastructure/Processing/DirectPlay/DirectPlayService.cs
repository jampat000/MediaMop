using Weir.Core.Processing;
using Weir.Infrastructure.Settings;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Processing.DirectPlay;

/// <summary>One device's answer for the Files-screen badge (<c>DirectPlayOut</c>).</summary>
public sealed record DirectPlayBadge(string DeviceId, string DeviceName, string Verdict, IReadOnlyList<string> Reasons);

/// <summary>Port of <c>processing/direct_play/service.py</c>: the operator's chosen devices, read-only per file.</summary>
public static class DirectPlayService
{
    /// <summary><c>selected_device_ids</c>.</summary>
    public static async Task<List<string>> SelectedDeviceIdsAsync(UnitOfWork uow)
    {
        var row = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        return [.. row.DirectPlayDevices.Split(',').Select(p => p.Trim()).Where(p => p.Length > 0)];
    }

    /// <summary><c>save_selected_device_ids</c>: keeps only ids the current device list knows, in its own order.</summary>
    public static async Task<List<string>> SaveSelectedDeviceIdsAsync(UnitOfWork uow, IReadOnlyList<DeviceProfile> knownDevices, IReadOnlyList<string> selected)
    {
        var wanted = new HashSet<string>(selected, StringComparer.Ordinal);
        var kept = knownDevices.Select(p => p.Id).Where(wanted.Contains).ToList();
        var before = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        await SuiteSettingsStore.UpdateAsync(uow, before, before with { DirectPlayDevices = string.Join(",", kept) }).ConfigureAwait(false);
        return kept;
    }

    /// <summary><c>selected_device_profiles</c>.</summary>
    public static async Task<IReadOnlyList<DeviceProfile>> SelectedProfilesAsync(UnitOfWork uow, IReadOnlyList<DeviceProfile> knownDevices)
    {
        var chosen = new HashSet<string>(await SelectedDeviceIdsAsync(uow).ConfigureAwait(false), StringComparer.Ordinal);
        return chosen.Count == 0 ? [] : [.. knownDevices.Where(p => chosen.Contains(p.Id))];
    }

    /// <summary><c>device_list_is_customised</c>.</summary>
    public static bool IsCustomised(string? weirHome) =>
        !string.IsNullOrEmpty(weirHome) && File.Exists(Path.Combine(weirHome, DirectPlayEvaluation.OverrideFileName));

    /// <summary><c>facts_for_row</c>.</summary>
    public static MediaFacts FactsForRow(ProcessingFileRecord row) => new(
        DirectPlayEvaluation.ContainerForPath(row.RelativePath),
        row.VideoCodec,
        row.VideoHeight,
        row.VideoBitDepth,
        row.AudioCodecs is { } codecs ? [.. codecs.Split(',').Where(c => c.Length > 0)] : null);

    /// <summary><c>direct_play_for_row</c>.</summary>
    public static List<DirectPlayBadge> ForRow(ProcessingFileRecord row, IReadOnlyList<DeviceProfile> devices)
    {
        if (devices.Count == 0)
        {
            return [];
        }

        var facts = FactsForRow(row);
        return [.. devices.Select(profile => DirectPlayEvaluation.Evaluate(profile, facts))
            .Select(verdict => new DirectPlayBadge(verdict.DeviceId, verdict.DeviceName, verdict.Verdict, verdict.Reasons))];
    }
}
