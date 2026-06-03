using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of uploading a local Blender scene file into cloud blob storage.
    /// </summary>
    public class UploadBlendResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not UploadBlendResponse other)
                return false;

            return Uploaded.Is(other.Uploaded)
                   && BlobId.Is(other.BlobId)
                   && FileName.Is(other.FileName)
                   && FileSize.Is(other.FileSize)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new UploadBlendResponse
            {
                Uploaded = Uploaded,
                BlobId = BlobId,
                FileName = FileName,
                FileSize = FileSize,
                Message = Message
            };
        }

        #endregion

        #region Properties

        public bool Uploaded { get; set; }

        public Guid BlobId { get; set; }

        public string FileName { get; set; } = null!;

        public long FileSize { get; set; }

        public string? Message { get; set; }

        #endregion
    }
}
