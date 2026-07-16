using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Status snapshot of one background upload. Large scene files and caches take minutes to push
    /// to the cloud, so the bridge uploads them in a background transfer the addon starts once and
    /// then polls — every REST round-trip stays fast instead of holding a single request open for
    /// the whole upload.
    /// </summary>
    public class UploadStatusResponse : ModelBase
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
            if (modelBase is not UploadStatusResponse other)
                return false;

            return TransferId.Is(other.TransferId)
                   && Status.Is(other.Status)
                   && FileName.Is(other.FileName)
                   && TotalBytes.Is(other.TotalBytes)
                   && (Result is null ? other.Result is null : other.Result is not null && Result.Is(other.Result))
                   && Error.Is(other.Error);
        }

        public override ModelBase Clone()
        {
            return new UploadStatusResponse
            {
                TransferId = TransferId,
                Status = Status,
                FileName = FileName,
                TotalBytes = TotalBytes,
                Result = (UploadBlendResponse?)Result?.Clone(),
                Error = Error
            };
        }

        #endregion

        #region Properties

        public Guid TransferId { get; set; }

        public string Status { get; set; } = null!;

        public string? FileName { get; set; }

        public long TotalBytes { get; set; }

        public UploadBlendResponse? Result { get; set; }

        public string? Error { get; set; }

        #endregion
    }
}
