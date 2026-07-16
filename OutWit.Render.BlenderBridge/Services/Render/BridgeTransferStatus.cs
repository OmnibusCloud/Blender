namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Lifecycle of a background blob transfer (download or upload).
    /// </summary>
    internal enum BridgeTransferStatus
    {
        InProgress,
        Completed,
        Failed,
        Cancelled
    }
}
