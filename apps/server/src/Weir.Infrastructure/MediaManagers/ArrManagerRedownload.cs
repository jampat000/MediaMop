using System.Globalization;
using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>
/// <see cref="IManagerRedownload"/> for Sonarr/Radarr (issue #509's only verified managers). Verified against
/// the sources named below rather than assumed:
///
/// <list type="bullet">
/// <item>
/// <b>Delete removes the file from disk, through the recycle bin when one is configured.</b>
/// <c>DELETE /api/v3/moviefile/{id}</c> / <c>episodefile/{id}</c> reach
/// <c>MediaFileDeletionService.DeleteMovieFile</c>/<c>DeleteEpisodeFile</c>
/// (Radarr <c>src/NzbDrone.Core/MediaFiles/MediaFileDeletionService.cs</c>, develop; Sonarr's file of the
/// same name on <c>v5-develop</c> is structurally identical), which calls
/// <c>IRecycleBinProvider.DeleteFile</c> before removing the DB row. <c>RecycleBinProvider.DeleteFolder</c>
/// (same repo, <c>RecycleBinProvider.cs</c>) shows the branch: <c>ConfigService.RecycleBin</c> empty means
/// <c>_diskProvider.DeleteFolder(path, true)</c> — permanent — otherwise the item is moved into that
/// folder. Either way the manager's own listing (and <c>ListLibraryFilesAsync</c>, #507) no longer shows the
/// file once this call returns: <b>this is the destructive step the issue requires flagging.</b>
/// </item>
/// <item>
/// <b>A same-quality search normally will not replace the file ("not an upgrade").</b>
/// <c>UpgradableSpecification.IsUpgradable</c> (Radarr <c>src/NzbDrone.Core/DecisionEngine/Specifications
/// /UpgradableSpecification.cs</c>, develop) rejects a candidate release whose quality is equal to what is
/// already imported unless its custom-format score is strictly higher (<c>UpgradeableRejectReason
/// .CustomFormatScore</c>/<c>QualityCutoff</c>); Sonarr's file of the same name is the same shape. This is
/// exactly why deleting the file record first is required before searching: without it, a release matching
/// the file Weir just narrowed down (same container/quality, different audio tracks) is routinely rejected
/// as not an upgrade and nothing is ever downloaded.
/// </item>
/// <item>
/// <b>Search command shapes.</b> <c>MoviesSearchCommand</c> (Radarr <c>src/NzbDrone.Core/IndexerSearch
/// /MoviesSearchCommand.cs</c>): <c>MovieIds: List&lt;int&gt;</c>. <c>SeriesSearchCommand</c> (Sonarr
/// <c>src/NzbDrone.Core/IndexerSearch/SeriesSearchCommand.cs</c>): <c>SeriesId: int</c>. Posted the same way
/// <see cref="HttpMediaManagerPort.FileChangedAsync"/> already posts <c>RescanMovie</c>/<c>RescanSeries</c>:
/// <c>POST /api/v3/command</c> with the class name minus "Command", camelCased properties.
/// </item>
/// </list>
///
/// <para><b>TV granularity.</b> #507's <c>ListLibraryFilesAsync</c> matches a Sonarr episode file to its
/// <i>series</i> id, not an episode id (Sonarr has no "every episode file" endpoint — see
/// <see cref="HttpMediaManagerPort.ListLibraryFilesAsync"/>'s remarks), so a redownload request here only
/// ever names a series id and a file path. Deleting the one matching <c>episodefile</c> is still precise;
/// searching afterwards uses <c>SeriesSearchCommand</c> for the whole series rather than
/// <c>EpisodeSearchCommand</c>, which the issue names as an explicit alternative and which this port would
/// otherwise need an extra <c>/api/v3/episode?episodeFileId=</c> call to resolve into episode ids. Once #507
/// or a later issue tracks individual episode ids, narrowing this to <c>EpisodeSearchCommand</c> is a small
/// change here, not a redesign.</para>
/// </summary>
public sealed class ArrManagerRedownload : IManagerRedownload
{
    private readonly IManagerHttpHandlerFactory _handlers;

    public ArrManagerRedownload(IManagerHttpHandlerFactory handlers)
    {
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
    }

    public bool SupportsRedownload(string? kind) => ManagerRedownloadRules.KindSupportsRedownload(kind);

    public async Task<RedownloadResult> RequestRedownloadAsync(
        ManagerConnection connection,
        string mediaScope,
        string titleId,
        string filePath,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(mediaScope);
        ArgumentNullException.ThrowIfNull(filePath);
        var profile = ManagerKindProfiles.ForKind(connection.Kind);
        if (profile is not { IsArr: true } || profile.ArrScope != mediaScope)
        {
            return Unsupported(connection);
        }

        if (!long.TryParse(titleId, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
        {
            throw new MediaManagerHttpException($"{connection.Label} needs a matched title id to redownload {filePath}, and none was given.");
        }

        var client = new MediaManagerHttpClient(connection.BaseUrl, connection.ApiKey, _handlers, ManagerDialectRules.LibraryTimeout);
        return mediaScope == MediaManagerKinds.Movie
            ? await RequestMovieRedownloadAsync(connection, client, id, cancellationToken).ConfigureAwait(false)
            : await RequestSeriesRedownloadAsync(connection, client, id, filePath, cancellationToken).ConfigureAwait(false);
    }

    private static async Task<RedownloadResult> RequestMovieRedownloadAsync(
        ManagerConnection connection, MediaManagerHttpClient client, long movieId, CancellationToken cancellationToken)
    {
        var idText = movieId.ToString(CultureInfo.InvariantCulture);
        var payload = await client.GetJsonAsync($"/api/v3/movie/{idText}", cancellationToken: cancellationToken).ConfigureAwait(false);
        if (payload is not PyDict movie)
        {
            throw new MediaManagerHttpException($"{connection.Label} did not return a movie for id {idText}.");
        }

        var file = movie.Get("movieFile") as PyDict;
        var fileId = file is null ? null : PyValues.FirstNumber(file, "id");
        var sizeBytes = file is null ? null : (long?)PyValues.FirstNumber(file, "size");

        return await DeleteThenSearchAsync(
            connection,
            client,
            existingFileId: fileId is { } n ? (long)n : null,
            existingFileSizeBytes: sizeBytes,
            deletePath: existingId => $"/api/v3/moviefile/{existingId.ToString(CultureInfo.InvariantCulture)}",
            searchBody: new PyDict().Set("name", "MoviesSearch").Set("movieIds", new PyList([PyJson.Of(movieId)])),
            cancellationToken).ConfigureAwait(false);
    }

    private static async Task<RedownloadResult> RequestSeriesRedownloadAsync(
        ManagerConnection connection, MediaManagerHttpClient client, long seriesId, string filePath, CancellationToken cancellationToken)
    {
        var payload = await client.GetJsonAsync(
            "/api/v3/episodefile",
            [new("seriesId", seriesId)],
            cancellationToken).ConfigureAwait(false);
        var match = PyValues.Dicts(payload).FirstOrDefault(row => LibraryFileChangeRules.PathsEqual(PyValues.Text(row.Get("path")), filePath));
        var fileId = match is null ? null : PyValues.FirstNumber(match, "id");
        var sizeBytes = match is null ? null : (long?)PyValues.FirstNumber(match, "size");

        return await DeleteThenSearchAsync(
            connection,
            client,
            existingFileId: fileId is { } n ? (long)n : null,
            existingFileSizeBytes: sizeBytes,
            deletePath: existingId => $"/api/v3/episodefile/{existingId.ToString(CultureInfo.InvariantCulture)}",
            searchBody: new PyDict().Set("name", "SeriesSearch").Set("seriesId", seriesId),
            cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// The shared shape: delete the existing file when there is one (the destructive step), then dispatch a
    /// search. A search failure is only ever swallowed into <see cref="RedownloadOutcome.DeletedButSearchFailed"/>
    /// when the delete already happened — otherwise it propagates, since nothing destructive occurred yet.
    /// </summary>
    private static async Task<RedownloadResult> DeleteThenSearchAsync(
        ManagerConnection connection,
        MediaManagerHttpClient client,
        long? existingFileId,
        long? existingFileSizeBytes,
        Func<long, string> deletePath,
        PyDict searchBody,
        CancellationToken cancellationToken)
    {
        var deleted = false;
        if (existingFileId is { } id)
        {
            await client.DeleteAsync(deletePath(id), cancellationToken: cancellationToken).ConfigureAwait(false);
            deleted = true;
        }

        try
        {
            await client.PostJsonAsync("/api/v3/command", searchBody, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (deleted && exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return new RedownloadResult(
                connection,
                RedownloadOutcome.DeletedButSearchFailed,
                DeletedExistingFile: true,
                existingFileSizeBytes,
                $"{connection.Label} deleted the existing file, but Weir could not ask it to search for a replacement " +
                $"({exception.Message}). This title now has no file until one is searched for again — try Download " +
                $"again, or search for it manually in {connection.Label}.",
                exception.Message);
        }

        return new RedownloadResult(
            connection,
            RedownloadOutcome.Requested,
            DeletedExistingFile: deleted,
            existingFileSizeBytes,
            deleted
                ? $"{connection.Label} deleted the existing file and is searching for a replacement."
                : $"{connection.Label} is searching for this title; it had no existing file for Weir to delete first.");
    }

    private static RedownloadResult Unsupported(ManagerConnection connection) => new(
        connection,
        RedownloadOutcome.Unsupported,
        DeletedExistingFile: false,
        ExistingFileSizeBytes: null,
        $"{connection.Label} cannot be asked to redownload a title (#509 only verifies this for Sonarr and Radarr).");
}
