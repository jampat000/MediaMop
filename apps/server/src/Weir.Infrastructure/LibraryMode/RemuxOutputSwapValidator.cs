using Microsoft.Extensions.Logging;
using Weir.Core.Media;
using Weir.Infrastructure.Media;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// The safe swap's <see cref="ISwapOutputValidator"/> (#506) until the dedicated #500 output-check pipeline lands in this
/// codebase: it runs the same full-read integrity check the download pipeline already has
/// (<see cref="MediaTools.ValidateMediaIntegrityAsync"/> — demuxes the whole cleaned copy and rejects a truncated or
/// otherwise incomplete file), cross-checked against the original's probed duration when that can be read. #500's richer
/// checks (track-by-track comparison against the plan) can replace this in place without SafeSwap or its callers changing,
/// since they only ever see <see cref="ISwapOutputValidator"/>.
/// </summary>
public sealed class RemuxOutputSwapValidator : ISwapOutputValidator
{
    private readonly MediaTools _tools;
    private readonly ILogger<RemuxOutputSwapValidator> _logger;

    public RemuxOutputSwapValidator(MediaTools tools, ILogger<RemuxOutputSwapValidator> logger)
    {
        _tools = tools ?? throw new ArgumentNullException(nameof(tools));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public async Task<SwapValidation> ValidateAsync(string originalPath, string outputPath, CancellationToken cancellationToken)
    {
        double? expectedDuration = null;
        try
        {
            var probe = await _tools.FfprobeJsonAsync(originalPath, cancellationToken: cancellationToken).ConfigureAwait(false);
            if (probe.TryGetProperty("format", out var format) && format.TryGetProperty("duration", out var durationValue) &&
                durationValue.ValueKind == System.Text.Json.JsonValueKind.String &&
                double.TryParse(durationValue.GetString(), System.Globalization.CultureInfo.InvariantCulture, out var parsed))
            {
                expectedDuration = parsed;
            }
        }
        catch (Exception exception) when (exception is MediaToolException or MediaToolTimeoutException)
        {
            // The original's duration is only a cross-check; the integrity read below still runs without it.
            _logger.LogDebug(exception, "Library swap validator could not re-read the original's duration; checking without it.");
        }

        try
        {
            await _tools.ValidateMediaIntegrityAsync(outputPath, expectedDuration, cancellationToken).ConfigureAwait(false);
            return SwapValidation.Pass;
        }
        catch (Exception exception) when (exception is MediaToolException or MediaToolTimeoutException)
        {
            return SwapValidation.Fail(exception.Message);
        }
    }
}
