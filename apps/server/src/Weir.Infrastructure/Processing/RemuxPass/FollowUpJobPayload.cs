using Weir.Core.Json;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>Shared payload parsing for the two failure-policy follow-up jobs (pass-through and reject).</summary>
internal static class FollowUpJobPayload
{
    /// <summary><c>json.loads(ctx.payload_json or "{}")</c>, tolerant of malformed or non-object JSON.</summary>
    public static PyDict Parse(string? payloadJson)
    {
        if (string.IsNullOrEmpty(payloadJson))
        {
            return new PyDict();
        }

        try
        {
            return PyJsonParser.Parse(payloadJson) is PyDict dict ? dict : new PyDict();
        }
        catch (PyJsonDecodeException)
        {
            return new PyDict();
        }
    }

    public static string RelativeMediaPath(PyDict payload) =>
        PyStrings.Strip(payload.Get("relative_media_path") is PyStr text ? text.Value : string.Empty);

    public static long? LibraryId(PyDict payload) =>
        payload.Get("library_id") is PyInt number ? (long)number.Value : null;

    public static PyDict? Origin(PyDict payload) => payload.Get("origin") as PyDict;
}
