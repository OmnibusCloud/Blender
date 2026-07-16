using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// State of one background result download keyed by job id. The worker task mutates it through
    /// the methods here; status snapshots are taken under the same lock, so the addon's polling
    /// never observes a half-updated transfer.
    /// </summary>
    internal sealed class BridgeDownloadTransfer
    {
        #region Fields

        private readonly object m_lock = new();

        private readonly List<BridgeDownloadTransferItem> m_items = [];

        private BridgeTransferStatus m_status = BridgeTransferStatus.InProgress;

        private BridgeDownloadTransferItem? m_currentItem;

        private DownloadResultResponse? m_result;

        private string? m_error;

        #endregion

        #region Constructors

        public BridgeDownloadTransfer(Guid jobId)
        {
            JobId = jobId;
        }

        #endregion

        #region Functions

        public void AddItem(BridgeDownloadTransferItem item)
        {
            lock (m_lock)
                m_items.Add(item);
        }

        public void SetCurrentItem(BridgeDownloadTransferItem item)
        {
            lock (m_lock)
                m_currentItem = item;
        }

        public void MarkItemCompleted(BridgeDownloadTransferItem item)
        {
            lock (m_lock)
            {
                item.IsCompleted = true;
                if (ReferenceEquals(m_currentItem, item))
                    m_currentItem = null;
            }
        }

        public void MarkCompleted(DownloadResultResponse result)
        {
            lock (m_lock)
            {
                m_status = BridgeTransferStatus.Completed;
                m_result = result;
                m_currentItem = null;
            }
        }

        public void MarkFailed(string error)
        {
            lock (m_lock)
            {
                m_status = BridgeTransferStatus.Failed;
                m_error = error;
                m_currentItem = null;
            }
        }

        public void MarkCancelled()
        {
            lock (m_lock)
            {
                m_status = BridgeTransferStatus.Cancelled;
                m_currentItem = null;
            }
        }

        public bool AllFilesExist()
        {
            lock (m_lock)
                return m_items.Count > 0 && m_items.All(me => File.Exists(me.LocalPath));
        }

        public IReadOnlyList<BridgeDownloadTransferItem> GetItems()
        {
            lock (m_lock)
                return m_items.ToList();
        }

        public DownloadStatusResponse ToStatus()
        {
            lock (m_lock)
            {
                long totalBytes = 0;
                long downloadedBytes = 0;
                var itemsCompleted = 0;

                foreach (var item in m_items)
                {
                    totalBytes += item.TotalBytes;

                    if (item.IsCompleted)
                    {
                        downloadedBytes += item.TotalBytes;
                        itemsCompleted++;
                    }
                    else if (ReferenceEquals(m_currentItem, item))
                    {
                        downloadedBytes += GetPartialLength(item);
                    }
                }

                return new DownloadStatusResponse
                {
                    JobId = JobId,
                    Status = m_status switch
                    {
                        BridgeTransferStatus.Completed => DownloadStatusResponse.STATUS_COMPLETED,
                        BridgeTransferStatus.Failed => DownloadStatusResponse.STATUS_FAILED,
                        BridgeTransferStatus.Cancelled => DownloadStatusResponse.STATUS_CANCELLED,
                        _ => DownloadStatusResponse.STATUS_IN_PROGRESS
                    },
                    TotalBytes = totalBytes,
                    DownloadedBytes = Math.Min(downloadedBytes, totalBytes),
                    Progress = totalBytes > 0 ? Math.Min(1.0, (double)downloadedBytes / totalBytes) : 0.0,
                    ItemCount = m_items.Count,
                    ItemsCompleted = itemsCompleted,
                    CurrentFileName = m_currentItem?.FileName,
                    Result = m_result,
                    Error = m_error
                };
            }
        }

        #endregion

        #region Tools

        private static long GetPartialLength(BridgeDownloadTransferItem item)
        {
            try
            {
                var info = new FileInfo(item.PartialPath);
                return info.Exists ? info.Length : 0;
            }
            catch
            {
                return 0;
            }
        }

        #endregion

        #region Properties

        public Guid JobId { get; }

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

        public bool IsCompleted
        {
            get
            {
                lock (m_lock)
                    return m_status == BridgeTransferStatus.Completed;
            }
        }

        #endregion
    }
}
