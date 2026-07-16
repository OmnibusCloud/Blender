using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Progress snapshot of one background result download. Large render outputs (video, frame
    /// archives) take minutes to pull from the cloud, so the bridge downloads them in a background
    /// transfer the addon starts once and then polls — every REST round-trip stays fast instead of
    /// holding a single request open for the whole download.
    /// </summary>
    public class DownloadStatusResponse : ModelBase
    {
        #region Constants

        public const string STATUS_IN_PROGRESS = "InProgress";
        public const string STATUS_COMPLETED = "Completed";
        public const string STATUS_FAILED = "Failed";
        public const string STATUS_CANCELLED = "Cancelled";
        public const string STATUS_NOT_FOUND = "NotFound";

        #endregion

        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not DownloadStatusResponse other)
                return false;

            return JobId.Is(other.JobId)
                   && Status.Is(other.Status)
                   && TotalBytes.Is(other.TotalBytes)
                   && DownloadedBytes.Is(other.DownloadedBytes)
                   && Progress.Is(other.Progress, tolerance)
                   && ItemCount.Is(other.ItemCount)
                   && ItemsCompleted.Is(other.ItemsCompleted)
                   && CurrentFileName.Is(other.CurrentFileName)
                   && (Result is null ? other.Result is null : other.Result is not null && Result.Is(other.Result))
                   && Error.Is(other.Error);
        }

        public override ModelBase Clone()
        {
            return new DownloadStatusResponse
            {
                JobId = JobId,
                Status = Status,
                TotalBytes = TotalBytes,
                DownloadedBytes = DownloadedBytes,
                Progress = Progress,
                ItemCount = ItemCount,
                ItemsCompleted = ItemsCompleted,
                CurrentFileName = CurrentFileName,
                Result = (DownloadResultResponse?)Result?.Clone(),
                Error = Error
            };
        }

        #endregion

        #region Properties

        public Guid JobId { get; set; }

        public string Status { get; set; } = null!;

        public long TotalBytes { get; set; }

        public long DownloadedBytes { get; set; }

        public double Progress { get; set; }

        public int ItemCount { get; set; }

        public int ItemsCompleted { get; set; }

        public string? CurrentFileName { get; set; }

        public DownloadResultResponse? Result { get; set; }

        public string? Error { get; set; }

        #endregion
    }
}
