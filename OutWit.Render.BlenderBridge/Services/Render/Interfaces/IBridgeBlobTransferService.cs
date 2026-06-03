using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns bridge-side blob upload and download operations for Blender-facing workflows.
    /// </summary>
    public interface IBridgeBlobTransferService
    {
        /// <summary>
        /// Uploads a local Blender scene file into cloud blob storage.
        /// </summary>
        Task<UploadBlendResponse> UploadBlendAsync(string filePath, CancellationToken cancellationToken = default);

        /// <summary>
        /// Uploads one local dependency artifact into cloud blob storage.
        /// </summary>
        Task<UploadBlendResponse> UploadFileAsync(string filePath, CancellationToken cancellationToken = default);
    }
}
