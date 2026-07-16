namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// One result blob inside a background download transfer. Mutated only by the transfer worker;
    /// read for progress snapshots under the owning transfer's lock.
    /// </summary>
    internal sealed class BridgeDownloadTransferItem
    {
        #region Properties

        public Guid BlobId { get; init; }

        public string FileName { get; init; } = null!;

        /// <summary>Final destination path; the file appears here only after a completed download.</summary>
        public string LocalPath { get; init; } = null!;

        /// <summary>In-flight path the SDK streams chunks into; moved to <see cref="LocalPath"/> on completion.</summary>
        public string PartialPath { get; init; } = null!;

        public long TotalBytes { get; init; }

        public bool IsCompleted { get; set; }

        #endregion
    }
}
