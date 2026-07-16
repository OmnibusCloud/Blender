using Microsoft.Extensions.Logging;
using OutWit.Cloud.SDK;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Bridge-side final result download operations. Downloads run as background transfers keyed by
    /// job id: the addon starts one and polls its status, so no REST request ever blocks for the
    /// duration of a multi-hundred-MB pull from the cloud (the old synchronous shape timed out the
    /// addon's HTTP client on large videos). Blobs stream to disk in chunks via
    /// <c>DownloadBlobToFileAsync</c> instead of materializing in memory.
    /// </summary>
    [InjectableHost]
    public partial class BridgeDownloadService : IBridgeDownloadService
    {
        #region Fields

        private readonly object m_lock = new();

        private readonly Dictionary<Guid, BridgeDownloadTransfer> m_transfers = new();

        #endregion

        #region IBridgeDownloadService

        public async Task<DownloadResultResponse> DownloadResultAsync(Guid jobId, CancellationToken cancellationToken = default)
        {
            if (jobId == Guid.Empty)
                throw new InvalidOperationException("Job id is required.");

            var transfer = GetOrStartTransfer(jobId);

            // The token cancels only this caller's wait; the shared background transfer keeps
            // running so a concurrent poller still gets its result.
            await transfer.Completion.WaitAsync(cancellationToken);

            var status = transfer.ToStatus();
            if (status.Status != DownloadStatusResponse.STATUS_COMPLETED || status.Result == null)
                throw new InvalidOperationException(status.Error ?? "Result download did not complete.");

            return status.Result;
        }

        public Task<DownloadStatusResponse> StartDownloadResultAsync(Guid jobId)
        {
            if (jobId == Guid.Empty)
                throw new InvalidOperationException("Job id is required.");

            var transfer = GetOrStartTransfer(jobId);
            return Task.FromResult(transfer.ToStatus());
        }

        public Task<DownloadStatusResponse> GetDownloadResultStatusAsync(Guid jobId)
        {
            lock (m_lock)
            {
                if (m_transfers.TryGetValue(jobId, out var transfer))
                    return Task.FromResult(transfer.ToStatus());
            }

            return Task.FromResult(new DownloadStatusResponse
            {
                JobId = jobId,
                Status = DownloadStatusResponse.STATUS_NOT_FOUND,
                Error = "No download has been started for this job."
            });
        }

        public Task<bool> CancelDownloadResultAsync(Guid jobId)
        {
            BridgeDownloadTransfer? transfer;
            lock (m_lock)
                m_transfers.TryGetValue(jobId, out transfer);

            if (transfer == null || !transfer.IsInProgress)
                return Task.FromResult(false);

            Logger.LogInformation("Bridge result download cancellation requested for job {JobId}", jobId);
            transfer.Cancellation.Cancel();
            return Task.FromResult(true);
        }

        #endregion

        #region Functions

        private BridgeDownloadTransfer GetOrStartTransfer(Guid jobId)
        {
            lock (m_lock)
            {
                if (m_transfers.TryGetValue(jobId, out var existing))
                {
                    // Re-request while running joins the active transfer; a completed one whose
                    // files are still on disk is served as-is. Failed / cancelled / deleted-files
                    // transfers start over.
                    if (existing.IsInProgress || (existing.IsCompleted && existing.AllFilesExist()))
                        return existing;

                    m_transfers.Remove(jobId);
                }

                var transfer = new BridgeDownloadTransfer(jobId);
                m_transfers[jobId] = transfer;
                transfer.Completion = Task.Run(() => RunTransferAsync(transfer));

                Logger.LogInformation("Bridge result download started for job {JobId}", jobId);
                return transfer;
            }
        }

        private async Task RunTransferAsync(BridgeDownloadTransfer transfer)
        {
            var cancellationToken = transfer.Cancellation.Token;

            try
            {
                var job = await JobQueryService.GetJobAsync(transfer.JobId, cancellationToken);
                Logger.LogInformation(
                    "Bridge result download job summary: Status={Status}, IsCompleted={IsCompleted}, ResultBlobId={ResultBlobId}, ResultBlobIdsCount={ResultBlobIdsCount}",
                    job.Status,
                    job.IsCompleted,
                    job.ResultBlobId,
                    job.ResultBlobIds?.Count ?? 0);

                var blobIds = job.ResultBlobIds?.Where(me => me != null && me != Guid.Empty).Select(me => me!.Value).ToList() ?? [];
                if (blobIds.Count == 0 && job.ResultBlobId != null && job.ResultBlobId != Guid.Empty)
                    blobIds.Add(job.ResultBlobId.Value);

                if (blobIds.Count == 0)
                    throw new InvalidOperationException($"Job '{transfer.JobId}' does not have a downloadable result blob.");

                var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                             ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

                var downloadDirectory = GetDownloadDirectoryPath();
                Directory.CreateDirectory(downloadDirectory);
                Logger.LogInformation("Bridge result download directory resolved to {DownloadDirectory}", downloadDirectory);

                // Resolve every blob's metadata up front so TotalBytes is known before the first
                // chunk lands — the addon's progress bar is meaningful from the start.
                foreach (var blobId in blobIds)
                {
                    var info = await client.Blobs.GetBlobInfoAsync(blobId, cancellationToken);
                    var fileName = string.IsNullOrWhiteSpace(info.FileName)
                        ? $"{blobId}.bin"
                        : info.FileName;
                    var localPath = Path.Combine(downloadDirectory, $"{transfer.JobId:N}_{blobId:N}_{fileName}");

                    transfer.AddItem(new BridgeDownloadTransferItem
                    {
                        BlobId = blobId,
                        FileName = fileName,
                        LocalPath = localPath,
                        PartialPath = localPath + ".partial",
                        TotalBytes = info.Size
                    });
                }

                var items = new List<DownloadedResultItemResponse>();
                foreach (var item in transfer.GetItems())
                {
                    Logger.LogInformation(
                        "Bridge downloading result blob {BlobId} for job {JobId} ({TotalBytes} bytes)",
                        item.BlobId,
                        transfer.JobId,
                        item.TotalBytes);

                    transfer.SetCurrentItem(item);
                    await client.Blobs.DownloadBlobToFileAsync(item.BlobId, item.PartialPath, ct: cancellationToken);
                    File.Move(item.PartialPath, item.LocalPath, overwrite: true);
                    transfer.MarkItemCompleted(item);

                    var fileSize = new FileInfo(item.LocalPath).Length;
                    items.Add(new DownloadedResultItemResponse
                    {
                        BlobId = item.BlobId,
                        FileName = item.FileName,
                        LocalPath = item.LocalPath,
                        FileSize = fileSize
                    });

                    Logger.LogInformation(
                        "Bridge downloaded result blob {BlobId} to {LocalPath} ({FileSize} bytes)",
                        item.BlobId,
                        item.LocalPath,
                        fileSize);
                }

                var first = items[0];
                transfer.MarkCompleted(new DownloadResultResponse
                {
                    Downloaded = true,
                    JobId = transfer.JobId,
                    BlobId = first.BlobId,
                    FileName = first.FileName,
                    LocalPath = first.LocalPath,
                    FileSize = first.FileSize,
                    Items = items,
                    Message = "Result downloaded successfully."
                });

                Logger.LogInformation("Bridge result download completed for job {JobId} with {ItemCount} item(s)", transfer.JobId, items.Count);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                CleanupPartials(transfer);
                transfer.MarkCancelled();
                Logger.LogInformation("Bridge result download cancelled for job {JobId}", transfer.JobId);
            }
            catch (Exception ex)
            {
                CleanupPartials(transfer);
                transfer.MarkFailed(ex.Message);
                Logger.LogError(ex, "Bridge result download failed for job {JobId}", transfer.JobId);
            }
        }

        #endregion

        #region Tools

        private string GetDownloadDirectoryPath()
        {
            var configured = Settings.DownloadCachePath;
            if (Path.IsPathRooted(configured))
                return configured;

            return Path.Combine(AppContext.BaseDirectory, configured);
        }

        private void CleanupPartials(BridgeDownloadTransfer transfer)
        {
            foreach (var item in transfer.GetItems())
            {
                try
                {
                    if (File.Exists(item.PartialPath))
                        File.Delete(item.PartialPath);
                }
                catch (Exception ex)
                {
                    Logger.LogWarning(ex, "Failed to remove partial download file {PartialPath}", item.PartialPath);
                }
            }
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        [Inject]
        public IBridgeJobQueryService JobQueryService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeDownloadService> Logger { get; set; } = null!;

        #endregion
    }
}
