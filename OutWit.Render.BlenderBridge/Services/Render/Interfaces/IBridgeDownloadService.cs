using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns bridge-side result download operations. Downloads run as background transfers keyed by
    /// job id so callers poll cheap status snapshots instead of holding a request open for the
    /// whole (possibly multi-minute) pull.
    /// </summary>
    public interface IBridgeDownloadService
    {
        /// <summary>
        /// Downloads the final result of one bridge-launched job into the local bridge download
        /// cache and returns only when the transfer finishes. The token cancels this caller's wait,
        /// not the shared background transfer.
        /// </summary>
        /// <exception cref="InvalidOperationException">Thrown when the transfer fails or is cancelled.</exception>
        Task<DownloadResultResponse> DownloadResultAsync(Guid jobId, CancellationToken cancellationToken = default);

        /// <summary>
        /// Starts (or joins) the background download of one job's result and returns the current
        /// status snapshot immediately. A completed transfer whose files are still on disk is
        /// returned as-is; a failed or cancelled one starts over.
        /// </summary>
        Task<DownloadStatusResponse> StartDownloadResultAsync(Guid jobId);

        /// <summary>
        /// Returns the current status snapshot of one job's result download, or
        /// <see cref="DownloadStatusResponse.STATUS_NOT_FOUND"/> when none was started.
        /// </summary>
        Task<DownloadStatusResponse> GetDownloadResultStatusAsync(Guid jobId);

        /// <summary>
        /// Requests cancellation of one job's in-progress result download. Returns true when an
        /// active transfer was told to cancel.
        /// </summary>
        Task<bool> CancelDownloadResultAsync(Guid jobId);
    }
}
