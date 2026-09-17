using System.Globalization;

namespace Weir.Core.Refiner.RemuxPass;

/// <summary>
/// The title and year a metadata lookup should ask about, read from a release or file name
/// (<c>The.Terror.1963.1080p.WEB-DL.DDP5.1.H.264-DELUNO</c> is "the terror", 1963). New for #537 item 4: the reference never
/// looked a title up during a pass.
/// </summary>
public static class ReleaseTitle
{
    /// <summary>
    /// The words before the release year, or, with no year, the words before the first packaging token; null when nothing
    /// usable remains.
    /// </summary>
    public static (string Title, int? Year)? Parse(string? name)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            return null;
        }

        var tokens = RefinerDomain.TokenizeNormalized(RefinerDomain.NormalizeTitleish(name));
        var packaging = new HashSet<string>(tokens.Except(RefinerDomain.StripPackagingTokens(tokens)), StringComparer.Ordinal);
        int? yearIndex = null;
        for (var i = tokens.Count - 1; i > 0; i--)
        {
            if (IsYear(tokens[i]))
            {
                yearIndex = i;
                break;
            }
        }

        List<string> title;
        int? year = null;
        if (yearIndex is { } index)
        {
            title = [.. tokens.Take(index).Where(token => !packaging.Contains(token))];
            year = int.Parse(tokens[index], CultureInfo.InvariantCulture);
        }
        else
        {
            title = [.. tokens.TakeWhile(token => !packaging.Contains(token))];
        }

        return title.Count == 0 ? null : (string.Join(' ', title), year);
    }

    private static bool IsYear(string token) =>
        token.Length == 4 && token.All(char.IsAsciiDigit) && int.Parse(token, CultureInfo.InvariantCulture) is >= 1888 and <= 2035;
}
