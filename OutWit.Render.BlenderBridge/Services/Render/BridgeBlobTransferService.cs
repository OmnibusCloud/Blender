using Microsoft.Extensions.Logging;
using OutWit.Cloud.SDK;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Bridge-side blob transfer operations for local Blender files. Upload chunking is handled
    /// by the SDK (<c>client.Blobs.UploadBlobFromFileAsync</c>).
    /// </summary>
    [InjectableHost]
    public partial class BridgeBlobTransferService : IBridgeBlobTransferService
    {
        #region IBridgeBlobTransferService

        public Task<UploadBlendResponse> UploadBlendAsync(string filePath, CancellationToken cancellationToken = default)
        {
            return UploadFileInternalAsync(filePath, "Blend uploaded successfully.", cancellationToken);
        }

        public Task<UploadBlendResponse> UploadFileAsync(string filePath, CancellationToken cancellationToken = default)
        {
            return UploadFileInternalAsync(filePath, "File uploaded successfully.", cancellationToken);
        }

        #endregion

        #region Tools

        private async Task<UploadBlendResponse> UploadFileInternalAsync(string filePath, string successMessage, CancellationToken cancellationToken)
        {
            if (string.IsNullOrWhiteSpace(filePath))
                throw new InvalidOperationException("File path is required.");

            if (!File.Exists(filePath))
                throw new FileNotFoundException($"File was not found: '{filePath}'.", filePath);

            var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                         ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

            var fileInfo = new FileInfo(filePath);
            var fileName = Path.GetFileName(filePath);

            var blobId = await client.Blobs.UploadBlobFromFileAsync(filePath, ct: cancellationToken);

            Logger.LogInformation("Bridge uploaded local file {FileName} ({FileSize} bytes) to blob {BlobId}",
                fileName,
                fileInfo.Length,
                blobId);

            return new UploadBlendResponse
            {
                Uploaded = true,
                BlobId = blobId,
                FileName = fileName,
                FileSize = fileInfo.Length,
                Message = successMessage
            };
        }

        #endregion

        #region Properties

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeBlobTransferService> Logger { get; set; } = null!;

        #endregion
    }
}
