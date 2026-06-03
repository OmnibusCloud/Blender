using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Models;

namespace OutWit.Render.BlenderBridge.Services.Hosting.Interfaces
{
    /// <summary>
    /// Owns the current local addon lease for the bridge process.
    /// </summary>
    public interface IBridgeLeaseService
    {
        /// <summary>
        /// Acquires or refreshes the current addon lease.
        /// </summary>
        Task<AcquireLeaseResponse> AcquireLeaseAsync(int ownerProcessId, string leaseId, string? addonVersion = null, CancellationToken cancellationToken = default);

        /// <summary>
        /// Refreshes the heartbeat timestamp for the current lease.
        /// </summary>
        Task<bool> PingLeaseAsync(string leaseId, CancellationToken cancellationToken = default);

        /// <summary>
        /// Releases the current addon lease.
        /// </summary>
        Task<bool> ReleaseLeaseAsync(string leaseId, CancellationToken cancellationToken = default);

        /// <summary>
        /// Returns the current lease snapshot if one exists.
        /// </summary>
        BridgeLeaseState? GetCurrentLease();

        /// <summary>
        /// Marks the current lease as orphaned.
        /// </summary>
        void MarkOrphaned(DateTime orphanedUtc);

        /// <summary>
        /// Clears the current lease state.
        /// </summary>
        void ClearLease();
    }
}
