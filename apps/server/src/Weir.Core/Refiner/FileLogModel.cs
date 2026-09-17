using Weir.Core.Time;

namespace Weir.Core.Refiner;

/// <summary>One <c>refiner_file_logs</c> row: one completed Refiner pass over one file.</summary>
public sealed record RefinerFileLogRecord
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
