namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// Caps the "Try on a file" rules preview (#502) at one run at a time. A preview does real ffprobe
/// work (and, when original-language is enabled, a metadata-provider lookup), and the rules editor
/// panel that calls it re-runs on every debounced edit; without a cap, a burst of edits could pile up
/// concurrent ffprobe processes. A second request while one is running gets a plain 409 rather than
/// being queued: queueing would need the job infrastructure, and this endpoint is deliberately
/// read-only (no job row, no file row, no Activity entry beyond debug logs) — the caller's own
/// debounce already keeps requests rare, so the web panel simply retries.
/// </summary>
public sealed class RulesPreviewGate
{
    private int _busy;

    /// <summary>True when this call claimed the single slot; the caller must <see cref="Release"/> it
    /// exactly once, in a <c>finally</c>, when (and only when) this returned true.</summary>
    public bool TryEnter() => Interlocked.CompareExchange(ref _busy, 1, 0) == 0;

    public void Release() => Interlocked.Exchange(ref _busy, 0);
}
