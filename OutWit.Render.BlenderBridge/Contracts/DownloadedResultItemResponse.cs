using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// One downloaded render-output file saved by the bridge.
    /// </summary>
    public class DownloadedResultItemResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not DownloadedResultItemResponse other)
                return false;

            return BlobId.Is(other.BlobId)
                   && FileName.Is(other.FileName)
                   && LocalPath.Is(other.LocalPath)
                   && FileSize.Is(other.FileSize);
        }

        public override ModelBase Clone()
        {
            return new DownloadedResultItemResponse
            {
                BlobId = BlobId,
                FileName = FileName,
                LocalPath = LocalPath,
                FileSize = FileSize
            };
        }

        #endregion

        #region Properties

        public Guid BlobId { get; set; }

        public string FileName { get; set; } = null!;

        public string LocalPath { get; set; } = null!;

        public long FileSize { get; set; }

        #endregion
    }
}
