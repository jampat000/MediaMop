using System.Text.RegularExpressions;

namespace Weir.Core.Refiner;

/// <summary>File-side strings for anchor ownership (port of <c>weir.refiner.domain.FileAnchorCandidate</c>).</summary>
public sealed record FileAnchorCandidate(string Title, int? Year = null);

/// <summary>Order-independent title anchor plus a single release year (<c>TitleYearAnchor</c>).</summary>
public sealed record TitleYearAnchor(IReadOnlySet<string> TitleTokens, int? Year)
{
    public bool IsUsableForMatch => TitleTokens.Count > 0 && Year is not null;
}

/// <summary>One upstream queue row after the caller has mapped *arr data (<c>RefinerQueueRowView</c>).</summary>
public sealed record RefinerQueueRowView(
    bool AppliesToFile,
    bool IsUpstreamActive,
    bool IsImportPending,
    bool BlockingSuppressedForImportWait = false,
    string? QueueTitle = null,
    int? QueueYear = null);

/// <summary>
/// Refiner domain: pure ownership vs. upstream blocking (port of <c>weir.refiner.domain</c>). No manager
/// HTTP, no orchestration — see <see cref="CandidateGate"/> for the layer that attributes rows to a
/// reporting connection, which needs the (not yet ported) media-manager queue signal infrastructure.
/// </summary>
public static partial class RefinerDomain
{
    private const int YearMin = 1888;
    private const int YearMax = 2035;

    private static readonly HashSet<string> PackagingTokens = new(StringComparer.Ordinal)
    {
        "480p", "576p", "720p", "900p", "1080p", "1080i", "1440p", "2160p", "4320p", "4k", "8k", "5k",
        "uhd", "fhd", "hq", "sd", "full", "hdr", "hdr10", "hdr10plus", "dolby", "vision",
        "x264", "x265", "h264", "h265", "hevc", "av1", "avc", "divx", "xvidx", "mpeg2", "mpeg4",
        "aac", "opus", "ac3", "eac3", "dts", "truehd", "atmos", "flac",
        "bluray", "bdrip", "brrip", "dvdrip", "dvd", "webdl", "webrip", "hdtv", "pdtv", "sdtv",
        "dsrip", "cam", "telesync", "telecine", "workprint", "remux", "hybrid",
        "repack", "proper", "internal", "retail", "extended", "unrated", "remastered", "multi",
        "dual", "dubbed", "subbed", "subs", "readnfo", "nfofix",
        "yts", "yify", "rarbg", "ettv", "eztv", "sparks", "geckos", "megusta", "ethd", "ntb", "fgt",
        "amzn", "nf", "hulu", "dsnp", "atvp",
    };

    [GeneratedRegex(@"\byts[\s.\-]+am\b")]
    private static partial Regex YtsAmToken();

    [GeneratedRegex(@"[^a-z0-9]+")]
    private static partial Regex NonAlphanumeric();

    [GeneratedRegex(@"\s+")]
    private static partial Regex Whitespace();

    /// <summary><c>normalize_titleish</c>.</summary>
    public static string NormalizeTitleish(string raw)
    {
        var s = raw.ToLowerInvariant().Trim();
        s = s.Replace("blu-ray", "bluray", StringComparison.Ordinal).Replace("web-dl", "webdl", StringComparison.Ordinal);
        s = YtsAmToken().Replace(s, " ");
        s = NonAlphanumeric().Replace(s, " ");
        return Whitespace().Replace(s, " ").Trim();
    }

    public static IReadOnlyList<string> TokenizeNormalized(string normalized) =>
        normalized.Length == 0 ? [] : [.. normalized.Split(' ', StringSplitOptions.RemoveEmptyEntries)];

    public static IReadOnlyList<string> StripPackagingTokens(IEnumerable<string> tokens) =>
        [.. tokens.Where(t => !PackagingTokens.Contains(t))];

    private static bool IsYearToken(string t)
    {
        if (t.Length != 4 || !t.All(char.IsAsciiDigit))
        {
            return false;
        }

        var y = int.Parse(t, System.Globalization.CultureInfo.InvariantCulture);
        return y is >= YearMin and <= YearMax;
    }

    /// <summary><c>extract_title_tokens_and_year</c>.</summary>
    public static (IReadOnlyList<string> Title, int? Year) ExtractTitleTokensAndYear(IReadOnlyList<string> tokens, int? explicitYear)
    {
        if (explicitYear is { } year)
        {
            var ys = year.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return ([.. tokens.Where(t => t != ys)], year);
        }

        var yearIndices = tokens.Select((t, i) => (t, i)).Where(pair => IsYearToken(pair.t)).Select(pair => pair.i).ToList();
        if (yearIndices.Count == 0)
        {
            return (tokens, null);
        }

        var idx = yearIndices[^1];
        var foundYear = int.Parse(tokens[idx], System.Globalization.CultureInfo.InvariantCulture);
        return ([.. tokens.Where((_, i) => i != idx)], foundYear);
    }

    /// <summary><c>extract_title_year_anchor</c>. Null when there is no non-empty raw string.</summary>
    public static TitleYearAnchor? ExtractTitleYearAnchor(string? raw, int? explicitYear = null)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        var normalized = NormalizeTitleish(raw);
        var tokens = TokenizeNormalized(normalized);
        var stripped = StripPackagingTokens(tokens);
        var (titleTokens, year) = ExtractTitleTokensAndYear(stripped, explicitYear);
        return new TitleYearAnchor(new HashSet<string>(titleTokens, StringComparer.Ordinal), year);
    }

    /// <summary><c>title_year_anchors_match</c>.</summary>
    public static bool AnchorsMatch(TitleYearAnchor a, TitleYearAnchor b) =>
        a.IsUsableForMatch && b.IsUsableForMatch && a.TitleTokens.SetEquals(b.TitleTokens) && a.Year == b.Year;

    private static TitleYearAnchor? RowAnchor(RefinerQueueRowView row) =>
        string.IsNullOrWhiteSpace(row.QueueTitle) ? null : ExtractTitleYearAnchor(row.QueueTitle, row.QueueYear);

    private static TitleYearAnchor? FileAnchor(FileAnchorCandidate candidate) => ExtractTitleYearAnchor(candidate.Title, candidate.Year);

    /// <summary><c>row_owns_by_title_year_anchor</c>.</summary>
    public static bool RowOwnsByTitleYearAnchor(RefinerQueueRowView row, FileAnchorCandidate candidate)
    {
        var qa = RowAnchor(row);
        var fa = FileAnchor(candidate);
        return qa is not null && fa is not null && AnchorsMatch(qa, fa);
    }

    private static bool RowAppliesToCandidate(RefinerQueueRowView row, FileAnchorCandidate? candidate) =>
        row.AppliesToFile || (candidate is not null && RowOwnsByTitleYearAnchor(row, candidate));

    /// <summary><c>file_is_owned_by_queue</c>.</summary>
    public static bool FileIsOwnedByQueue(IReadOnlyList<RefinerQueueRowView> rows, FileAnchorCandidate? candidate = null) =>
        rows.Any(r => RowAppliesToCandidate(r, candidate));

    /// <summary><c>should_block_for_upstream</c>.</summary>
    public static bool ShouldBlockForUpstream(IReadOnlyList<RefinerQueueRowView> rows, FileAnchorCandidate? candidate = null) =>
        rows.Any(r => RowAppliesToCandidate(r, candidate) && r.IsUpstreamActive && !r.BlockingSuppressedForImportWait);
}

/// <summary>Which managers were asked, and which could not answer (<c>QueueSignalReport</c>).</summary>
public sealed record QueueSignalReport(int Consulted, int Reported, IReadOnlyList<string> SilentLabels)
{
    public bool AllReported => SilentLabels.Count == 0;

    public bool HasAnySignal => Reported > 0;

    /// <summary><c>note</c>: one sentence for an operator, or null when every manager answered.</summary>
    public string? Note() => SilentLabels.Count == 0
        ? null
        : $"Weir could not get an import check from {string.Join(", ", SilentLabels)}, so it did not treat that as 'nothing is importing'.";
}

/// <summary>The verdict the "why held" diagnostic reports (<c>candidate_gate_evaluate.Verdict</c>).</summary>
public enum CandidateGateVerdict
{
    Proceed,
    WaitUpstream,
    NotHeld,
    NoUpstreamSignal,
}

/// <summary>Structured result for operators (<c>RefinerCandidateGateOutcome</c>).</summary>
public sealed record CandidateGateOutcome(
    CandidateGateVerdict Verdict,
    bool Owned,
    bool BlockedUpstream,
    int QueueRowCount,
    string MediaScope,
    int ManagersConsulted,
    int ManagersReporting,
    IReadOnlyList<string> ManagersWithoutQueueSignal,
    string? BlockedByConnection,
    IReadOnlyList<string> Reasons);

/// <summary>
/// Evaluate a file/release candidate against every media manager covering its scope (port of
/// <c>refiner_candidate_gate_evaluate.py</c> and the pure parts of <c>manager_queue_signals.py</c>).
/// </summary>
public static class CandidateGate
{
    /// <summary><c>no_manager_configured_note</c>.</summary>
    public static string NoManagerConfiguredNote(string mediaScope)
    {
        var scopeWord = mediaScope == "tv" ? "TV episodes" : "Movies";
        return $"No media manager is connected for {scopeWord}, so Weir had no import check to make. " +
               "Add one on the Media managers settings page if you want that safety check.";
    }

    /// <summary>
    /// <c>evaluate_refiner_candidate_gate_from_manager_signals</c>, given the attributed rows and the
    /// consulted/reported/silent report directly (the row-mapping step needs the media-manager dialect
    /// adapters, ported separately in #520; see <c>HoldDiagnosticStore</c> for how this is called today).
    /// </summary>
    public static CandidateGateOutcome Evaluate(
        string mediaScope,
        QueueSignalReport report,
        IReadOnlyList<RefinerQueueRowView> attributedRows,
        FileAnchorCandidate candidate)
    {
        var owned = RefinerDomain.FileIsOwnedByQueue(attributedRows, candidate);
        var blockedBy = attributedRows.FirstOrDefault(row => RefinerDomain.ShouldBlockForUpstream([row], candidate));
        var rowCount = attributedRows.Count;

        CandidateGateOutcome Outcome(CandidateGateVerdict verdict, params string[] reasons)
        {
            var collected = new List<string>(reasons);
            var note = report.Note();
            if (note is not null)
            {
                collected.Add(note);
            }

            return new CandidateGateOutcome(
                verdict, owned, blockedBy is not null, rowCount, mediaScope, report.Consulted, report.Reported,
                report.SilentLabels, null, collected);
        }

        if (report.Consulted == 0)
        {
            return Outcome(CandidateGateVerdict.NoUpstreamSignal, NoManagerConfiguredNote(mediaScope));
        }

        if (!report.HasAnySignal)
        {
            return Outcome(
                CandidateGateVerdict.NoUpstreamSignal,
                "No connected media manager could say what it is importing, so Weir has no upstream check for this candidate. " +
                "That is not the same as an empty queue.");
        }

        if (rowCount == 0)
        {
            return Outcome(CandidateGateVerdict.NotHeld, "Every media manager that answered reported an empty queue, so nothing upstream holds this candidate.");
        }

        if (!owned)
        {
            return Outcome(CandidateGateVerdict.NotHeld, "No queue row applies to this candidate by path, id, or title/year anchor rules.");
        }

        if (blockedBy is not null)
        {
            return Outcome(CandidateGateVerdict.WaitUpstream, "Weir treats this candidate as held upstream.");
        }

        return Outcome(
            CandidateGateVerdict.Proceed,
            "A media manager holds this candidate, but no manager reports it in an active upstream or download state, so it is not waiting on an import.");
    }
}
