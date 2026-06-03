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
    /// Bridge-side final result download operations.
    /// </summary>
    [InjectableHost]
    public partial class BridgeDownloadService : IBridgeDownloadService
    {
        #region IBridgeDownloadService

        public async Task<DownloadResultResponse> DownloadResultAsync(Guid jobId, CancellationToken cancellationToken = default)
        {
            if (jobId == Guid.Empty)
                throw new InvalidOperationException("Job id is required.");

            Logger.LogInformation("Bridge result download requested for job {JobId}", jobId);

            var job = await JobQueryService.GetJobAsync(jobId, cancellationToken);
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
                throw new InvalidOperationException($"Job '{jobId}' does not have a downloadable result blob.");

            var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                         ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

            var downloadDirectory = GetDownloadDirectoryPath();
            Directory.CreateDirectory(downloadDirectory);
            Logger.LogInformation("Bridge result download directory resolved to {DownloadDirectory}", downloadDirectory);

            var items = new List<DownloadedResultItemResponse>();
            foreach (var blobId in blobIds)
            {
                Logger.LogInformation("Bridge downloading result blob {BlobId} for job {JobId}", blobId, jobId);

                var info = await client.Blobs.GetBlobInfoAsync(blobId, cancellationToken);
                Logger.LogInformation(
                    "Bridge blob info loaded for blob {BlobId}: FileName={FileName}, Size={Size}",
                    blobId,
                    info.FileName,
                    info.Size);

                var content = await client.Blobs.DownloadBlobAsync(blobId, cancellationToken);
                Logger.LogInformation(
                    "Bridge blob payload loaded for blob {BlobId}: {ByteCount} bytes",
                    blobId,
                    content.LongLength);

                var fileName = string.IsNullOrWhiteSpace(info.FileName)
                    ? $"{blobId}.bin"
                    : info.FileName;
                var localPath = Path.Combine(downloadDirectory, $"{jobId:N}_{blobId:N}_{fileName}");

                await File.WriteAllBytesAsync(localPath, content, cancellationToken);
                items.Add(new DownloadedResultItemResponse
                {
                    BlobId = blobId,
                    FileName = fileName,
                    LocalPath = localPath,
                    FileSize = content.LongLength
                });

                Logger.LogInformation(
                    "Bridge downloaded result blob {BlobId} to {LocalPath} ({FileSize} bytes)",
                    blobId,
                    localPath,
                    content.LongLength);
            }

            var first = items[0];

            Logger.LogInformation("Bridge result download completed for job {JobId} with {ItemCount} item(s)", jobId, items.Count);

            return new DownloadResultResponse
            {
                Downloaded = true,
                JobId = jobId,
                BlobId = first.BlobId,
                FileName = first.FileName,
                LocalPath = first.LocalPath,
                FileSize = first.FileSize,
                Items = items,
                Message = "Result downloaded successfully."
            };
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
