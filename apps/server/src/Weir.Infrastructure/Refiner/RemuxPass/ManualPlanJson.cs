using Weir.Core.Json;
using Weir.Core.Refiner;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// JSON (de)serialization for a manual track plan and the source fingerprint recorded when it was chosen (issue #501),
/// both stored on the enqueued <c>refiner.file.remux_pass.v1</c> job payload as <c>manual_plan</c> and
/// <c>source_fingerprint</c>.
/// </summary>
public static class ManualPlanJson
{
    public static PyDict ToPyDict(ManualPlanChoice choice)
    {
        ArgumentNullException.ThrowIfNull(choice);
        return new PyDict()
            .Set("keep", new PyList(choice.Keep.Select(e => (PyJson)new PyDict()
                .Set("index", e.Index)
                .Set("default", e.Default)
                .Set("forced", e.Forced))))
            .Set("order", new PyList(choice.Order.Select(i => (PyJson)new PyInt(i))));
    }

    /// <summary>Null when the payload's <c>manual_plan</c> is missing or not shaped as expected.</summary>
    public static ManualPlanChoice? FromPyJson(PyJson? value)
    {
        if (value is not PyDict dict || dict.Get("keep") is not PyList keepList)
        {
            return null;
        }

        var keep = new List<ManualKeepEntry>();
        foreach (var item in keepList.Items)
        {
            if (item is not PyDict entry || entry.Get("index") is not PyInt index)
            {
                return null;
            }

            var isDefault = entry.Get("default") is PyBool { Value: true };
            var forced = entry.Get("forced") is PyBool { Value: true };
            keep.Add(new ManualKeepEntry((int)index.Value, isDefault, forced));
        }

        var order = new List<int>();
        if (dict.Get("order") is PyList orderList)
        {
            foreach (var item in orderList.Items)
            {
                if (item is PyInt orderIndex)
                {
                    order.Add((int)orderIndex.Value);
                }
            }
        }

        return new ManualPlanChoice(keep, order);
    }

    public static PyDict ToPyDict(SourceFingerprint fingerprint) => new PyDict()
        .Set("device", new PyInt(fingerprint.Device))
        .Set("inode", new PyInt(fingerprint.Inode))
        .Set("size_bytes", fingerprint.SizeBytes)
        .Set("modified_time_ns", fingerprint.ModifiedTimeNs);

    /// <summary>Null when the payload's <c>source_fingerprint</c> is missing or not shaped as expected.</summary>
    public static SourceFingerprint? FingerprintFromPyJson(PyJson? value)
    {
        if (value is not PyDict dict
            || dict.Get("device") is not PyInt device
            || dict.Get("inode") is not PyInt inode
            || dict.Get("size_bytes") is not PyInt sizeBytes
            || dict.Get("modified_time_ns") is not PyInt modifiedTimeNs)
        {
            return null;
        }

        return new SourceFingerprint((ulong)device.Value, (ulong)inode.Value, (long)sizeBytes.Value, (long)modifiedTimeNs.Value);
    }
}
