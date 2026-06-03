using OutWit.Common.Abstract;
using OutWit.Common.Collections;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of downloading one final render output blob to the local bridge cache.
    /// </summary>
    public class DownloadResultResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not DownloadResultResponse other)
                return false;

            return Downloaded.Is(other.Downloaded)
                   && JobId.Is(other.JobId)
                   && BlobId.Is(other.BlobId)
                   && FileName.Is(other.FileName)
                   && LocalPath.Is(other.LocalPath)
                   && FileSize.Is(other.FileSize)
                   && Items.Is(other.Items)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new DownloadResultResponse
            {
                Downloaded = Downloaded,
                JobId = JobId,
                BlobId = BlobId,
                FileName = FileName,
                LocalPath = LocalPath,
                FileSize = FileSize,
                Items = [.. Items.Select(me => (DownloadedResultItemResponse)me.Clone())],
                Message = Message
            };
        }

        #endregion

        #region Properties

        public bool Downloaded { get; set; }

        public Guid JobId { get; set; }

        public Guid BlobId { get; set; }

        public string FileName { get; set; } = null!;

        public string LocalPath { get; set; } = null!;

        public long FileSize { get; set; }

        public List<DownloadedResultItemResponse> Items { get; set; } = [];

        public string? Message { get; set; }

        #endregion
    }
}
