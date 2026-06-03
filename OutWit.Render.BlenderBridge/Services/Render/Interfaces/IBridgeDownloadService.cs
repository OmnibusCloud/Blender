using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns bridge-side result download operations.
    /// </summary>
    public interface IBridgeDownloadService
    {
        /// <summary>
        /// Downloads the final result of one bridge-launched job into the local bridge download cache.
        /// </summary>
        Task<DownloadResultResponse> DownloadResultAsync(Guid jobId, CancellationToken cancellationToken = default);
    }
}
