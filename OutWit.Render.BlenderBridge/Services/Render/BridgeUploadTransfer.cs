using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// State of one background upload keyed by a bridge-generated transfer id. The worker task
    /// mutates it through the methods here; status snapshots are taken under the same lock. Byte
    /// progress is not tracked — the SDK reads the file internally with no progress hook — so the
    /// snapshot carries the lifecycle plus the file's name and total size.
    /// </summary>
    internal sealed class BridgeUploadTransfer
    {
        #region Fields

        private readonly object m_lock = new();

        private BridgeTransferStatus m_status = BridgeTransferStatus.InProgress;

        private UploadBlendResponse? m_result;

        private string? m_error;

        #endregion

        #region Constructors

        public BridgeUploadTransfer(string filePath, string fileName, long totalBytes)
        {
            FilePath = filePath;
            FileName = fileName;
            TotalBytes = totalBytes;
        }

        #endregion

        #region Functions

        public void MarkCompleted(UploadBlendResponse result)
        {
            lock (m_lock)
            {
                m_status = BridgeTransferStatus.Completed;
                m_result = result;
            }
        }

        public void MarkFailed(string error)
        {
            lock (m_lock)
            {
                m_status = BridgeTransferStatus.Failed;
                m_error = error;
            }
        }

        public void MarkCancelled()
        {
            lock (m_lock)
                m_status = BridgeTransferStatus.Cancelled;
        }

        public UploadStatusResponse ToStatus()
        {
            lock (m_lock)
            {
                return new UploadStatusResponse
                {
                    TransferId = TransferId,
                    Status = m_status switch
                    {
                        BridgeTransferStatus.Completed => UploadStatusResponse.STATUS_COMPLETED,
                        BridgeTransferStatus.Failed => UploadStatusResponse.STATUS_FAILED,
                        BridgeTransferStatus.Cancelled => UploadStatusResponse.STATUS_CANCELLED,
                        _ => UploadStatusResponse.STATUS_IN_PROGRESS
                    },
                    FileName = FileName,
                    TotalBytes = TotalBytes,
                    Result = m_result,
                    Error = m_error
                };
            }
        }

        #endregion

        #region Properties

        public Guid TransferId { get; } = Guid.NewGuid();

        public string FilePath { get; }

        public string FileName { get; }

        public long TotalBytes { get; }

        public CancellationTokenSource Cancellation { get; } = new();

        /// <summary>Worker task; always completes successfully — outcomes land in the transfer state.</summary>
        public Task Completion { get; set; } = Task.CompletedTask;

        public bool IsInProgress
        {
            get
            {
                lock (m_lock)
                    return m_status == BridgeTransferStatus.InProgress;
            }
        }

        #endregion
    }
}
