using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Infrastructure.Refiner;

/// <summary>
/// Worker handler for a Pass 4 failure-cleanup sweep job (port of <c>make_refiner_failure_cleanup_handler</c>). One
/// subclass is registered per scope (<see cref="MovieFailureCleanupSweepHandler"/>, <see cref="TvFailureCleanupSweepHandler"/>),
/// since <c>refiner.movie_failure_cleanup_sweep.v1</c> and <c>refiner.tv_failure_cleanup_sweep.v1</c> are distinct job
/// kinds with a fixed default scope each — kept as distinct types (rather than one class parameterized by string) so
/// dependency injection can tell the two registrations apart.
/// </summary>
public abstract class RefinerFailureCleanupSweepHandler : IJobHandler
{
    private readonly RefinerFailureCleanupSweep _sweep;
    private readonly string _defaultScope;

    protected RefinerFailureCleanupSweepHandler(RefinerFailureCleanupSweep sweep, string jobKind, string defaultScope)
    {
        _sweep = sweep ?? throw new ArgumentNullException(nameof(sweep));
        JobKind = jobKind ?? throw new ArgumentNullException(nameof(jobKind));
        _defaultScope = defaultScope ?? throw new ArgumentNullException(nameof(defaultScope));
    }

    public string JobKind { get; }

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var (mediaScope, trigger) = ParsePayload(context.PayloadJson, _defaultScope);

        var database = _sweep.Database;
        var startedDetail = new PyDict().Set("job_id", context.Id).Set("media_scope", mediaScope).Set("cleanup_run_status", "started");
        await LockedWrites.RunAsync(
            database,
            uow => RefinerFailureCleanupActivity.RecordSweepStartedAsync(uow, mediaScope, startedDetail, trigger),
            _sweep.Logger,
            "failure cleanup sweep started",
            cancellationToken).ConfigureAwait(false);

        var result = await _sweep.RunForScopeAsync(mediaScope, cancellationToken).ConfigureAwait(false);
        result.Set("job_id", context.Id);

        await LockedWrites.RunAsync(
            database,
            uow => RefinerFailureCleanupActivity.RecordSweepCompletedAsync(uow, mediaScope, result, trigger),
            _sweep.Logger,
            "failure cleanup sweep completed",
            cancellationToken).ConfigureAwait(false);
    }

    /// <summary><c>_parse_payload</c>: the scope and provenance trigger, tolerant of a missing or malformed payload.</summary>
    private static (string MediaScope, string? Trigger) ParsePayload(string? payloadJson, string defaultScope)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return (defaultScope, null);
        }

        PyJson parsed;
        try
        {
            parsed = PyJsonParser.Parse(payloadJson);
        }
        catch (PyJsonDecodeException)
        {
            return (defaultScope, null);
        }

        if (parsed is not PyDict data)
        {
            return (defaultScope, null);
        }

        var scope = data.Get("media_scope") is PyStr scopeValue && string.Equals(PyStrings.Strip(scopeValue.Value), "tv", StringComparison.OrdinalIgnoreCase)
            ? "tv"
            : "movie";
        var trigger = data.Get("trigger") is PyStr triggerValue ? triggerValue.Value : null;
        return (scope, trigger);
    }
}

/// <summary>Handles <c>refiner.movie_failure_cleanup_sweep.v1</c>.</summary>
public sealed class MovieFailureCleanupSweepHandler : RefinerFailureCleanupSweepHandler
{
    public MovieFailureCleanupSweepHandler(RefinerFailureCleanupSweep sweep)
        : base(sweep, Weir.Infrastructure.Jobs.PeriodicJobKinds.MovieFailureCleanupSweep, "movie")
    {
    }
}

/// <summary>Handles <c>refiner.tv_failure_cleanup_sweep.v1</c>.</summary>
public sealed class TvFailureCleanupSweepHandler : RefinerFailureCleanupSweepHandler
{
    public TvFailureCleanupSweepHandler(RefinerFailureCleanupSweep sweep)
        : base(sweep, Weir.Infrastructure.Jobs.PeriodicJobKinds.TvFailureCleanupSweep, "tv")
    {
    }
}
