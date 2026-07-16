using Microsoft.Extensions.Logging;
using OutWit.Cloud.SDK;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Bridge-side blob upload operations for local Blender files. Uploads run as background
    /// transfers keyed by a bridge-generated transfer id: the addon starts one and polls its
    /// status, so no REST request ever blocks for the duration of a multi-hundred-MB push to the
    /// cloud (the old synchronous shape timed out the addon's HTTP client on large scenes).
    /// Chunking is handled by the SDK (<c>client.Blobs.UploadBlobFromFileAsync</c>).
    /// </summary>
    [InjectableHost]
    public partial class BridgeBlobTransferService : IBridgeBlobTransferService
    {
        #region Fields

        private readonly object m_lock = new();

        private readonly Dictionary<Guid, BridgeUploadTransfer> m_transfers = new();

        #endregion

        #region IBridgeBlobTransferService

        public Task<UploadBlendResponse> UploadBlendAsync(string filePath, CancellationToken cancellationToken = default)
        {
            return UploadAndWaitAsync(filePath, "Blend uploaded successfully.", cancellationToken);
        }

        public Task<UploadBlendResponse> UploadFileAsync(string filePath, CancellationToken cancellationToken = default)
        {
            return UploadAndWaitAsync(filePath, "File uploaded successfully.", cancellationToken);
        }

        public Task<UploadStatusResponse> StartUploadBlendAsync(string filePath)
        {
            var transfer = StartTransfer(filePath, "Blend uploaded successfully.");
            return Task.FromResult(transfer.ToStatus());
        }

        public Task<UploadStatusResponse> StartUploadFileAsync(string filePath)
        {
            var transfer = StartTransfer(filePath, "File uploaded successfully.");
            return Task.FromResult(transfer.ToStatus());
        }

        public Task<UploadStatusResponse> GetUploadStatusAsync(Guid transferId)
        {
            lock (m_lock)
            {
                if (m_transfers.TryGetValue(transferId, out var transfer))
                    return Task.FromResult(transfer.ToStatus());
            }

            return Task.FromResult(new UploadStatusResponse
            {
                TransferId = transferId,
                Status = UploadStatusResponse.STATUS_NOT_FOUND,
                Error = "No upload with this transfer id is known to the bridge."
            });
        }

        public Task<bool> CancelUploadAsync(Guid transferId)
        {
            BridgeUploadTransfer? transfer;
            lock (m_lock)
                m_transfers.TryGetValue(transferId, out transfer);

            if (transfer == null || !transfer.IsInProgress)
                return Task.FromResult(false);

            Logger.LogInformation("Bridge upload cancellation requested for transfer {TransferId} ({FileName})", transferId, transfer.FileName);
            transfer.Cancellation.Cancel();
            return Task.FromResult(true);
        }

        #endregion

        #region Functions

        private BridgeUploadTransfer StartTransfer(string filePath, string successMessage)
        {
            // Validate up front so a bad path fails the start call itself (fast, local disk) —
            // only the cloud push runs in the background.
            if (string.IsNullOrWhiteSpace(filePath))
                throw new InvalidOperationException("File path is required.");

            if (!File.Exists(filePath))
                throw new FileNotFoundException($"File was not found: '{filePath}'.", filePath);

            var fileInfo = new FileInfo(filePath);
            var transfer = new BridgeUploadTransfer(filePath, Path.GetFileName(filePath), fileInfo.Length);

            lock (m_lock)
                m_transfers[transfer.TransferId] = transfer;

            transfer.Completion = Task.Run(() => RunTransferAsync(transfer, successMessage));

            Logger.LogInformation(
                "Bridge upload started for {FileName} ({FileSize} bytes) as transfer {TransferId}",
                transfer.FileName,
                transfer.TotalBytes,
                transfer.TransferId);

            return transfer;
        }

        private async Task RunTransferAsync(BridgeUploadTransfer transfer, string successMessage)
        {
            var cancellationToken = transfer.Cancellation.Token;

            try
            {
                var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                             ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

                var blobId = await client.Blobs.UploadBlobFromFileAsync(transfer.FilePath, ct: cancellationToken);

                transfer.MarkCompleted(new UploadBlendResponse
                {
                    Uploaded = true,
                    BlobId = blobId,
                    FileName = transfer.FileName,
                    FileSize = transfer.TotalBytes,
                    Message = successMessage
                });

                Logger.LogInformation(
                    "Bridge uploaded local file {FileName} ({FileSize} bytes) to blob {BlobId}",
                    transfer.FileName,
                    transfer.TotalBytes,
                    blobId);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                transfer.MarkCancelled();
                Logger.LogInformation("Bridge upload cancelled for transfer {TransferId} ({FileName})", transfer.TransferId, transfer.FileName);
            }
            catch (Exception ex)
            {
                transfer.MarkFailed(ex.Message);
                Logger.LogError(ex, "Bridge upload failed for transfer {TransferId} ({FileName})", transfer.TransferId, transfer.FileName);
            }
        }

        #endregion

        #region Tools

        private async Task<UploadBlendResponse> UploadAndWaitAsync(string filePath, string successMessage, CancellationToken cancellationToken)
        {
            var transfer = StartTransfer(filePath, successMessage);

            // The token cancels only this caller's wait; the background transfer keeps running so a
            // concurrent status poller still gets its result.
            await transfer.Completion.WaitAsync(cancellationToken);

            var status = transfer.ToStatus();
            if (status.Status != UploadStatusResponse.STATUS_COMPLETED || status.Result == null)
                throw new InvalidOperationException(status.Error ?? "Upload did not complete.");

            return status.Result;
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
