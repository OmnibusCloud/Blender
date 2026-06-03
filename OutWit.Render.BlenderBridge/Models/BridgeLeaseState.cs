namespace OutWit.Render.BlenderBridge.Models
{
    /// <summary>
    /// In-memory local lease state owned by the current Blender bridge process.
    /// </summary>
    public class BridgeLeaseState
    {
        #region Properties

        public string LeaseId { get; set; } = null!;

        public int OwnerProcessId { get; set; }

        public DateTime AcquiredUtc { get; set; }

        public DateTime LastHeartbeatUtc { get; set; }

        public DateTime? OrphanedUtc { get; set; }

        public string? AddonVersion { get; set; }

        #endregion
    }
}
