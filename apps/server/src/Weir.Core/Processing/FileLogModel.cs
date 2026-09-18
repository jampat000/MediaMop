using Weir.Core.Time;

namespace Weir.Core.Processing;

/// <summary>One <c>file_logs</c> row: one completed Processing pass over one file.</summary>
public sealed record ProcessingFileLogRecord
{
    public long Id { get; init; }
    public long? FileId { get; init; }
    public long? LibraryId { get; init; }
    public required string RelativePath { get; init; }
    public string LibraryName { get; init; } = string.Empty;
    public string Outcome { get; init; } = string.Empty;
    public string Title { get; init; } = string.Empty;
    public string DetailJson { get; init; } = "{}";
    public PyDateTime RecordedAt { get; init; }
}
