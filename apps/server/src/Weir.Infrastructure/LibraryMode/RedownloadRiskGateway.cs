using Weir.Core.LibraryMode;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>The manager calls issue #508 step 2 needs before it can predict anything: one title's file, and its quality profile.</summary>
public interface IRedownloadRiskGateway
{
    /// <summary>
    /// <c>GET /api/v3/moviefile/{id}</c> or <c>/api/v3/episodefile/{id}</c>, depending on <paramref name="mediaScope"/>
    /// (<see cref="MediaManagerKinds.Movie"/> / <see cref="MediaManagerKinds.Tv"/>).
    /// </summary>
    Task<FileFormatSnapshot> GetFileFormatSnapshotAsync(ManagerConnection connection, string mediaScope, long fileId, CancellationToken cancellationToken = default);

    /// <summary><c>GET /api/v3/qualityprofile/{id}</c>, the same path for both products.</summary>
    Task<QualityProfileSnapshot> GetQualityProfileAsync(ManagerConnection connection, long qualityProfileId, CancellationToken cancellationToken = default);
}

/// <summary>
/// The re-download-risk manager calls over Sonarr/Radarr's arr v3 API. The caller already knows the file id and
/// quality profile id from #505's title matching (it already listed the manager's files to map paths to titles),
/// so this makes only the two calls issue #508 step 2 actually needs.
/// </summary>
public sealed class ArrRedownloadRiskGateway : IRedownloadRiskGateway
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(30);

    private readonly IManagerHttpHandlerFactory _handlers;

    public ArrRedownloadRiskGateway(IManagerHttpHandlerFactory handlers)
    {
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
    }

    public async Task<FileFormatSnapshot> GetFileFormatSnapshotAsync(ManagerConnection connection, string mediaScope, long fileId, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        var path = mediaScope == MediaManagerKinds.Movie ? $"/api/v3/moviefile/{fileId}" : $"/api/v3/episodefile/{fileId}";
        var payload = await Client(connection).GetJsonAsync(path, cancellationToken: cancellationToken).ConfigureAwait(false);
        return RedownloadRiskDialect.ParseFileFormatSnapshot(payload, connection.Kind);
    }

    public async Task<QualityProfileSnapshot> GetQualityProfileAsync(ManagerConnection connection, long qualityProfileId, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        var payload = await Client(connection).GetJsonAsync($"/api/v3/qualityprofile/{qualityProfileId}", cancellationToken: cancellationToken).ConfigureAwait(false);
        return RedownloadRiskDialect.ParseQualityProfile(payload);
    }

    private MediaManagerHttpClient Client(ManagerConnection connection) => new(connection.BaseUrl, connection.ApiKey, _handlers, Timeout);
}

/// <summary>
/// Ties <see cref="IRedownloadRiskGateway"/> to the pure <see cref="RedownloadRiskEvaluator"/>, turning any
/// manager-reachability failure into issue #508's "couldn't check" note instead of blocking the clean, and
/// skipping the check entirely for a manager kind with no equivalent data.
/// </summary>
public sealed class RedownloadRiskChecker
{
    private readonly IRedownloadRiskGateway _gateway;

    public RedownloadRiskChecker(IRedownloadRiskGateway gateway)
    {
        _gateway = gateway ?? throw new ArgumentNullException(nameof(gateway));
    }

    /// <param name="connection">The manager that owns this title. Only "sonarr" and "radarr" expose the needed data.</param>
    /// <param name="mediaScope"><see cref="MediaManagerKinds.Movie"/> or <see cref="MediaManagerKinds.Tv"/>.</param>
    /// <param name="fileId">The manager's own movie/episode file id.</param>
    /// <param name="qualityProfileId">The title's quality profile id (already known from #505's title matching).</param>
    /// <param name="titleName">The title as the manager names it, e.g. "Blade Runner 2049".</param>
    /// <param name="removedAudioLanguages">The languages of the audio tracks the plan would remove.</param>
    /// <param name="skipIfManagerWouldRedownload">The library's <c>skip_if_manager_would_redownload</c> setting (default true).</param>
    /// <param name="cancellationToken"></param>
    public async Task<RedownloadRiskAssessment> CheckAsync(
        ManagerConnection connection,
        string mediaScope,
        long fileId,
        long qualityProfileId,
        string titleName,
        IReadOnlyCollection<string> removedAudioLanguages,
        bool skipIfManagerWouldRedownload,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(titleName);
        ArgumentNullException.ThrowIfNull(removedAudioLanguages);

        if (connection.Kind is not ("sonarr" or "radarr"))
        {
            // Deluno's external integration API (docs/external-integration-api.md: manifest, health, queue,
            // activity, import-preview, trigger-refresh, file-changed, processor events) has no endpoint
            // resembling a quality profile's cutoffFormatScore/upgradeAllowed or a file's customFormatScore.
            // Issue #508: "Deluno: only if it exposes equivalent data, otherwise no check" — so this reports
            // no risk rather than guessing, for Deluno and for "native".
            return RedownloadRiskAssessment.NoRisk;
        }

        try
        {
            var snapshot = await _gateway.GetFileFormatSnapshotAsync(connection, mediaScope, fileId, cancellationToken).ConfigureAwait(false);
            var profile = await _gateway.GetQualityProfileAsync(connection, qualityProfileId, cancellationToken).ConfigureAwait(false);
            return RedownloadRiskEvaluator.Evaluate(connection.Label, titleName, snapshot, profile, removedAudioLanguages, skipIfManagerWouldRedownload);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return RedownloadRiskAssessment.CouldNotCheck(connection.Label);
        }
    }
}
