using System.Globalization;

namespace Weir.Core.Text;

/// <summary>
/// Counted nouns for sentences people read: "1 file", "2 files", "0 files" — never "file(s)". Every
/// message the server writes for a person (API messages, Activity, readiness and status details,
/// failure reasons) counts things through here.
/// </summary>
public static class Plural
{
    /// <summary>
    /// The count and its noun: "1 file", "2 files", "0 files". Pass <paramref name="plural"/> for a noun
    /// that does not just take an "s" ("library", "libraries").
    /// </summary>
    public static string Of(long count, string singular, string? plural = null) =>
        count.ToString(CultureInfo.InvariantCulture) + " " + Noun(count, singular, plural);

    /// <summary>
    /// The noun (or verb) alone, for a sentence that prints the count itself or puts words between the
    /// two: <c>Noun(n, "was", "were")</c>.
    /// </summary>
    public static string Noun(long count, string singular, string? plural = null) =>
        count == 1 ? singular : plural ?? singular + "s";
}
