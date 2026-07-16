using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns bridge-side blob upload operations for Blender-facing workflows. Uploads run as
    /// background transfers keyed by a bridge-generated transfer id so callers poll cheap status
    /// snapshots instead of holding a request open for the whole (possibly multi-minute) push.
    /// </summary>
    public interface IBridgeBlobTransferService
    {
        /// <summary>
        /// Uploads a local Blender scene file into cloud blob storage and returns only when the
        /// transfer finishes. The token cancels this caller's wait, not the background transfer.
        /// </summary>
        /// <exception cref="InvalidOperationException">Thrown when the transfer fails or is cancelled.</exception>
        Task<UploadBlendResponse> UploadBlendAsync(string filePath, CancellationToken cancellationToken = default);

        /// <summary>
        /// Uploads one local dependency artifact into cloud blob storage and returns only when the
        /// transfer finishes. The token cancels this caller's wait, not the background transfer.
        /// </summary>
        /// <exception cref="InvalidOperationException">Thrown when the transfer fails or is cancelled.</exception>
        Task<UploadBlendResponse> UploadFileAsync(string filePath, CancellationToken cancellationToken = default);

        /// <summary>
        /// Starts the background upload of a local Blender scene file and returns the transfer's
        /// status snapshot (with its transfer id) immediately. Missing/blank paths fail this call.
        /// </summary>
        Task<UploadStatusResponse> StartUploadBlendAsync(string filePath);

        /// <summary>
        /// Starts the background upload of one local dependency artifact and returns the transfer's
        /// status snapshot (with its transfer id) immediately. Missing/blank paths fail this call.
        /// </summary>
        Task<UploadStatusResponse> StartUploadFileAsync(string filePath);

        /// <summary>
        /// Returns the current status snapshot of one background upload, or
        /// <see cref="UploadStatusResponse.STATUS_NOT_FOUND"/> when the transfer id is unknown.
        /// </summary>
        Task<UploadStatusResponse> GetUploadStatusAsync(Guid transferId);

        /// <summary>
        /// Requests cancellation of one in-progress background upload. Returns true when an active
        /// transfer was told to cancel.
        /// </summary>
        Task<bool> CancelUploadAsync(Guid transferId);
    }
}
